import uuid
from dataclasses import field as dc_field
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.career_hub.models import ResumeMatchScore
from apps.career_hub.services.skill_gap_service import (
    VALID_RECOMMENDATION_TIERS,
    JobSkillGap,
    SkillGapEntry,
    SkillGapSummary,
    _cache_key_summary,
    _compute_summary,
    _enrich_entry,
    _normalize_resource_dict,
    get_job_skill_gap,
    get_skill_gap_recommendations,
    get_skill_gap_summary,
)

_MODULE = "apps.career_hub.services.skill_gap_service"
_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_JOB_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_user(user_id=_USER_ID):
    user = MagicMock()
    user.id = user_id
    return user


def _make_row(overall_score: float, gaps: dict | None = None) -> dict:
    return {
        "overall_score": Decimal(str(overall_score)),
        "skill_gaps": gaps or {},
    }


def _make_empty_summary() -> SkillGapSummary:
    return SkillGapSummary(
        career_readiness_score=None,
        total_jobs_scored=0,
        top_critical_gaps=[],
        top_moderate_gaps=[],
        top_soft_gaps=[],
        gap_counts={"critical": 0, "moderate": 0, "soft": 0, "low": 0},
    )


def _patch_qs(rows: list[dict]):
    """Return a context manager that patches ResumeMatchScore ORM to yield rows."""
    patcher = patch(f"{_MODULE}.ResumeMatchScore")

    class _Ctx:
        def __enter__(self):
            self.mock = patcher.__enter__()
            (
                self.mock.objects
                .filter.return_value
                .order_by.return_value
                .values.return_value
            ) = rows
            return self.mock

        def __exit__(self, *args):
            patcher.__exit__(*args)

    return _Ctx()


# ─── _cache_key_summary ────────────────────────────────────────────────────────

class TestCacheKeyFormat:
    def test_contains_user_id(self):
        key = _cache_key_summary(_USER_ID)
        assert str(_USER_ID) in key

    def test_different_users_produce_different_keys(self):
        other = uuid.uuid4()
        assert _cache_key_summary(_USER_ID) != _cache_key_summary(other)

    def test_key_is_string(self):
        assert isinstance(_cache_key_summary(_USER_ID), str)

    def test_key_has_namespace_prefix(self):
        key = _cache_key_summary(_USER_ID)
        assert key.startswith("skill_gap:")


# ─── _enrich_entry ─────────────────────────────────────────────────────────────

class TestEnrichEntry:
    def test_known_token_returns_display_name(self):
        entry = _enrich_entry("python", 3)
        assert entry.display_name == "Python"

    def test_known_token_has_category(self):
        entry = _enrich_entry("python", 3)
        assert entry.category is not None

    def test_known_token_has_url(self):
        entry = _enrich_entry("python", 3)
        assert entry.url is not None and entry.url != ""

    def test_known_token_job_count_preserved(self):
        entry = _enrich_entry("python", 7)
        assert entry.job_count == 7

    def test_known_token_prerequisites_is_list(self):
        entry = _enrich_entry("kubernetes", 2)
        assert isinstance(entry.prerequisites, list)

    def test_unknown_token_display_name_is_none(self):
        entry = _enrich_entry("nonexistentskill123", 1)
        assert entry.display_name is None

    def test_unknown_token_token_preserved(self):
        entry = _enrich_entry("nonexistentskill123", 4)
        assert entry.token == "nonexistentskill123"

    def test_unknown_token_prerequisites_is_empty_list(self):
        entry = _enrich_entry("nonexistentskill123", 1)
        assert entry.prerequisites == []


# ─── _normalize_resource_dict ──────────────────────────────────────────────────

class TestNormalizeResourceDict:
    def test_bare_dict_fills_missing_fields_with_none(self):
        result = _normalize_resource_dict({"token": "xyz"})
        assert result["display_name"] is None
        assert result["category"] is None
        assert result["description"] is None
        assert result["resource_type"] is None
        assert result["url"] is None

    def test_bare_dict_prerequisites_defaults_to_empty_list(self):
        result = _normalize_resource_dict({"token": "xyz"})
        assert result["prerequisites"] == []

    def test_full_dict_passes_through(self):
        item = {
            "token": "docker",
            "display_name": "Docker",
            "category": "devops",
            "description": "desc",
            "resource_type": "docs",
            "url": "https://example.com",
            "prerequisites": ["linux"],
        }
        result = _normalize_resource_dict(item)
        assert result["display_name"] == "Docker"
        assert result["prerequisites"] == ["linux"]

    def test_token_always_present(self):
        result = _normalize_resource_dict({"token": "abc"})
        assert result["token"] == "abc"

    def test_partial_dict_fills_missing_with_none(self):
        result = _normalize_resource_dict({"token": "go", "display_name": "Go"})
        assert result["display_name"] == "Go"
        assert result["category"] is None


# ─── _compute_summary ──────────────────────────────────────────────────────────

class TestComputeSummaryEmptyState:
    def test_returns_none_crs(self):
        user = _make_user()
        with _patch_qs([]):
            result = _compute_summary(user)
        assert result.career_readiness_score is None

    def test_returns_zero_total(self):
        user = _make_user()
        with _patch_qs([]):
            result = _compute_summary(user)
        assert result.total_jobs_scored == 0

    def test_all_gap_lists_are_empty(self):
        user = _make_user()
        with _patch_qs([]):
            result = _compute_summary(user)
        assert result.top_critical_gaps == []
        assert result.top_moderate_gaps == []
        assert result.top_soft_gaps == []

    def test_gap_counts_all_zero(self):
        user = _make_user()
        with _patch_qs([]):
            result = _compute_summary(user)
        assert result.gap_counts == {"critical": 0, "moderate": 0, "soft": 0, "low": 0}

    def test_returns_skill_gap_summary_type(self):
        user = _make_user()
        with _patch_qs([]):
            result = _compute_summary(user)
        assert isinstance(result, SkillGapSummary)


class TestComputeSummaryCRS:
    def test_single_score_becomes_crs(self):
        user = _make_user()
        with _patch_qs([_make_row(0.850)]):
            result = _compute_summary(user)
        assert result.career_readiness_score == 85

    def test_perfect_score_gives_100(self):
        user = _make_user()
        with _patch_qs([_make_row(1.000)]):
            result = _compute_summary(user)
        assert result.career_readiness_score == 100

    def test_zero_score_gives_0(self):
        user = _make_user()
        with _patch_qs([_make_row(0.000)]):
            result = _compute_summary(user)
        assert result.career_readiness_score == 0

    def test_averages_multiple_scores(self):
        rows = [_make_row(0.800), _make_row(0.900)]
        user = _make_user()
        with _patch_qs(rows):
            result = _compute_summary(user)
        assert result.career_readiness_score == 85

    def test_more_than_10_scores_uses_top_10(self):
        rows = [_make_row(0.900)] * 10 + [_make_row(0.100)] * 5
        user = _make_user()
        with _patch_qs(rows):
            result = _compute_summary(user)
        assert result.career_readiness_score == 90

    def test_crs_is_integer(self):
        user = _make_user()
        with _patch_qs([_make_row(0.856)]):
            result = _compute_summary(user)
        assert isinstance(result.career_readiness_score, int)

    def test_total_jobs_scored_includes_all_rows(self):
        rows = [_make_row(0.7), _make_row(0.8), _make_row(0.9)]
        user = _make_user()
        with _patch_qs(rows):
            result = _compute_summary(user)
        assert result.total_jobs_scored == 3


class TestComputeSummaryGapAggregation:
    def test_aggregates_critical_across_jobs(self):
        rows = [
            _make_row(0.8, {"critical": ["python"], "moderate": [], "soft": [], "low": []}),
            _make_row(0.7, {"critical": ["python"], "moderate": [], "soft": [], "low": []}),
        ]
        user = _make_user()
        with _patch_qs(rows):
            result = _compute_summary(user)
        assert result.top_critical_gaps[0].token == "python"
        assert result.top_critical_gaps[0].job_count == 2

    def test_most_frequent_gap_comes_first(self):
        rows = [
            _make_row(0.9, {"critical": ["docker", "python"], "moderate": [], "soft": [], "low": []}),
            _make_row(0.8, {"critical": ["docker"], "moderate": [], "soft": [], "low": []}),
        ]
        user = _make_user()
        with _patch_qs(rows):
            result = _compute_summary(user)
        assert result.top_critical_gaps[0].token == "docker"

    def test_top_critical_limited_to_10(self):
        tokens = [f"skill{i}" for i in range(15)]
        gaps = {"critical": tokens, "moderate": [], "soft": [], "low": []}
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        assert len(result.top_critical_gaps) <= 10

    def test_top_moderate_limited_to_5(self):
        tokens = [f"skill{i}" for i in range(10)]
        gaps = {"critical": [], "moderate": tokens, "soft": [], "low": []}
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        assert len(result.top_moderate_gaps) <= 5

    def test_top_soft_limited_to_5(self):
        tokens = [f"leadership{i}" for i in range(10)]
        gaps = {"critical": [], "moderate": [], "soft": tokens, "low": []}
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        assert len(result.top_soft_gaps) <= 5

    def test_gap_counts_reflect_unique_tokens(self):
        gaps = {
            "critical": ["python", "docker"],
            "moderate": ["microservices"],
            "soft": ["leadership", "agile"],
            "low": ["xyz"],
        }
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        assert result.gap_counts["critical"] == 2
        assert result.gap_counts["moderate"] == 1
        assert result.gap_counts["soft"] == 2
        assert result.gap_counts["low"] == 1

    def test_legacy_three_tier_gaps_handled_gracefully(self):
        gaps = {"critical": ["python"], "moderate": ["microservices"], "low": ["xyz"]}
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        assert result.top_soft_gaps == []
        assert result.gap_counts["soft"] == 0

    def test_none_gaps_field_handled(self):
        rows = [_make_row(0.8, None)]
        rows[0]["skill_gaps"] = None
        user = _make_user()
        with _patch_qs(rows):
            result = _compute_summary(user)
        assert result.top_critical_gaps == []

    def test_entries_are_skill_gap_entry_instances(self):
        gaps = {"critical": ["python"], "moderate": [], "soft": [], "low": []}
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        assert isinstance(result.top_critical_gaps[0], SkillGapEntry)

    def test_known_token_gets_enriched(self):
        gaps = {"critical": ["python"], "moderate": [], "soft": [], "low": []}
        user = _make_user()
        with _patch_qs([_make_row(0.8, gaps)]):
            result = _compute_summary(user)
        entry = result.top_critical_gaps[0]
        assert entry.display_name == "Python"


# ─── get_skill_gap_summary (cache layer) ───────────────────────────────────────

class TestGetSkillGapSummaryCache:
    def test_result_is_returned(self):
        user = _make_user()
        with patch(f"{_MODULE}.cache") as mock_cache, \
             patch(f"{_MODULE}._compute_summary") as mock_compute:
            mock_cache.get.return_value = None
            mock_compute.return_value = _make_empty_summary()
            result = get_skill_gap_summary(user)
        assert isinstance(result, SkillGapSummary)

    def test_cache_set_called_on_miss(self):
        user = _make_user()
        with patch(f"{_MODULE}.cache") as mock_cache, \
             patch(f"{_MODULE}._compute_summary") as mock_compute:
            mock_cache.get.return_value = None
            mock_compute.return_value = _make_empty_summary()
            get_skill_gap_summary(user)
        mock_cache.set.assert_called_once()

    def test_cache_ttl_is_900(self):
        user = _make_user()
        with patch(f"{_MODULE}.cache") as mock_cache, \
             patch(f"{_MODULE}._compute_summary") as mock_compute:
            mock_cache.get.return_value = None
            mock_compute.return_value = _make_empty_summary()
            get_skill_gap_summary(user)
        _, __, ttl = mock_cache.set.call_args[0]
        assert ttl == 900

    def test_cache_key_includes_user_id(self):
        user = _make_user()
        with patch(f"{_MODULE}.cache") as mock_cache, \
             patch(f"{_MODULE}._compute_summary") as mock_compute:
            mock_cache.get.return_value = None
            mock_compute.return_value = _make_empty_summary()
            get_skill_gap_summary(user)
        key = mock_cache.set.call_args[0][0]
        assert str(_USER_ID) in key

    def test_cache_hit_skips_compute(self):
        user = _make_user()
        cached = _make_empty_summary()
        with patch(f"{_MODULE}.cache") as mock_cache, \
             patch(f"{_MODULE}._compute_summary") as mock_compute:
            mock_cache.get.return_value = cached
            result = get_skill_gap_summary(user)
        mock_compute.assert_not_called()
        assert result is cached

    def test_cache_hit_skips_set(self):
        user = _make_user()
        with patch(f"{_MODULE}.cache") as mock_cache:
            mock_cache.get.return_value = _make_empty_summary()
            get_skill_gap_summary(user)
        mock_cache.set.assert_not_called()

    def test_different_users_use_different_keys(self):
        user1 = _make_user(uuid.uuid4())
        user2 = _make_user(uuid.uuid4())
        keys = []
        summary = _make_empty_summary()

        def track_set(key, *args):
            keys.append(key)

        with patch(f"{_MODULE}.cache") as mock_cache, \
             patch(f"{_MODULE}._compute_summary", return_value=summary):
            mock_cache.get.return_value = None
            mock_cache.set.side_effect = track_set
            get_skill_gap_summary(user1)
            get_skill_gap_summary(user2)
        assert keys[0] != keys[1]


# ─── get_skill_gap_recommendations ─────────────────────────────────────────────

class TestGetSkillGapRecommendations:
    def _make_summary_with(
        self,
        critical: list | None = None,
        moderate: list | None = None,
        soft: list | None = None,
    ) -> SkillGapSummary:
        return SkillGapSummary(
            career_readiness_score=80,
            total_jobs_scored=5,
            top_critical_gaps=critical or [],
            top_moderate_gaps=moderate or [],
            top_soft_gaps=soft or [],
            gap_counts={"critical": 0, "moderate": 0, "soft": 0, "low": 0},
        )

    def test_default_tier_returns_critical(self):
        entry = SkillGapEntry("python", 3, display_name="Python")
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[entry])
            result = get_skill_gap_recommendations(user)
        assert len(result) == 1
        assert result[0]["tier"] == "critical"

    def test_tier_moderate_returns_moderate(self):
        entry = SkillGapEntry("microservices", 2)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(moderate=[entry])
            result = get_skill_gap_recommendations(user, tier="moderate")
        assert len(result) == 1
        assert result[0]["tier"] == "moderate"

    def test_tier_soft_returns_soft(self):
        entry = SkillGapEntry("leadership", 4, display_name="Leadership")
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(soft=[entry])
            result = get_skill_gap_recommendations(user, tier="soft")
        assert len(result) == 1
        assert result[0]["tier"] == "soft"

    def test_tier_all_combines_all_tiers(self):
        c = SkillGapEntry("python", 5)
        m = SkillGapEntry("microservices", 3)
        s = SkillGapEntry("leadership", 4)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[c], moderate=[m], soft=[s])
            result = get_skill_gap_recommendations(user, tier="all")
        assert len(result) == 3

    def test_tier_all_sorted_by_job_count_descending(self):
        c = SkillGapEntry("python", 5)
        m = SkillGapEntry("microservices", 3)
        s = SkillGapEntry("leadership", 7)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[c], moderate=[m], soft=[s])
            result = get_skill_gap_recommendations(user, tier="all")
        job_counts = [r["job_count"] for r in result]
        assert job_counts == sorted(job_counts, reverse=True)

    def test_empty_summary_returns_empty_list(self):
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with()
            result = get_skill_gap_recommendations(user)
        assert result == []

    def test_result_items_are_dicts(self):
        entry = SkillGapEntry("python", 3, display_name="Python")
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[entry])
            result = get_skill_gap_recommendations(user)
        assert isinstance(result[0], dict)

    def test_result_has_token_field(self):
        entry = SkillGapEntry("python", 3)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[entry])
            result = get_skill_gap_recommendations(user)
        assert result[0]["token"] == "python"

    def test_result_has_job_count_field(self):
        entry = SkillGapEntry("python", 6)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[entry])
            result = get_skill_gap_recommendations(user)
        assert result[0]["job_count"] == 6

    def test_enriched_entry_exposes_display_name(self):
        entry = SkillGapEntry("python", 3, display_name="Python", url="https://python.org")
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[entry])
            result = get_skill_gap_recommendations(user)
        assert result[0]["display_name"] == "Python"

    def test_unknown_entry_null_display_name(self):
        entry = SkillGapEntry("unknownxyz", 2)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[entry])
            result = get_skill_gap_recommendations(user)
        assert result[0]["display_name"] is None

    def test_tier_all_tier_field_set_correctly(self):
        c = SkillGapEntry("python", 5)
        s = SkillGapEntry("leadership", 3)
        user = _make_user()
        with patch(f"{_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = self._make_summary_with(critical=[c], soft=[s])
            result = get_skill_gap_recommendations(user, tier="all")
        tiers = {r["token"]: r["tier"] for r in result}
        assert tiers["python"] == "critical"
        assert tiers["leadership"] == "soft"


# ─── get_job_skill_gap ─────────────────────────────────────────────────────────

class TestGetJobSkillGap:
    def _make_score_mock(self, gaps=None, score=Decimal("0.850")):
        mock_score = MagicMock()
        mock_score.job_id = _JOB_ID
        mock_score.job.title = "Senior Engineer"
        mock_score.job.company = "Acme Corp"
        mock_score.overall_score = score
        mock_score.skill_gaps = gaps or {
            "critical": ["python", "docker"],
            "moderate": [],
            "soft": [],
            "low": [],
        }
        return mock_score

    def _patch_get(self, mock_score):
        patcher = patch(f"{_MODULE}.ResumeMatchScore")

        class _Ctx:
            def __enter__(self):
                self.mock = patcher.__enter__()
                self.mock.objects.select_related.return_value.get.return_value = mock_score
                self.mock.DoesNotExist = ResumeMatchScore.DoesNotExist
                return self.mock

            def __exit__(self, *args):
                patcher.__exit__(*args)

        return _Ctx()

    def _patch_not_found(self):
        patcher = patch(f"{_MODULE}.ResumeMatchScore")

        class _Ctx:
            def __enter__(self):
                self.mock = patcher.__enter__()
                self.mock.DoesNotExist = ResumeMatchScore.DoesNotExist
                self.mock.objects.select_related.return_value.get.side_effect = (
                    ResumeMatchScore.DoesNotExist()
                )
                return self.mock

            def __exit__(self, *args):
                patcher.__exit__(*args)

        return _Ctx()

    def test_raises_does_not_exist_for_wrong_user(self):
        user = _make_user()
        with self._patch_not_found():
            with pytest.raises(ResumeMatchScore.DoesNotExist):
                get_job_skill_gap(user, _JOB_ID)

    def test_returns_job_skill_gap_instance(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        assert isinstance(result, JobSkillGap)

    def test_job_id_is_str(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        assert isinstance(result.job_id, str)

    def test_job_id_matches(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        assert result.job_id == str(_JOB_ID)

    def test_job_title_matches(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        assert result.job_title == "Senior Engineer"

    def test_job_company_matches(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        assert result.job_company == "Acme Corp"

    def test_score_display_calculated_from_overall_score(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock(score=Decimal("0.850"))):
            result = get_job_skill_gap(user, _JOB_ID)
        assert result.score_display == 85

    def test_critical_gaps_are_normalized_dicts(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        assert all(isinstance(g, dict) for g in result.critical_gaps)

    def test_critical_gaps_have_token_key(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        for gap in result.critical_gaps:
            assert "token" in gap

    def test_all_four_tiers_present(self):
        user = _make_user()
        gaps = {"critical": ["python"], "moderate": ["microservices"], "soft": ["leadership"], "low": ["xyz"]}
        with self._patch_get(self._make_score_mock(gaps=gaps)):
            result = get_job_skill_gap(user, _JOB_ID)
        assert len(result.critical_gaps) == 1
        assert len(result.moderate_gaps) == 1
        assert len(result.soft_gaps) == 1
        assert len(result.low_gaps) == 1

    def test_legacy_three_tier_backward_compat(self):
        user = _make_user()
        gaps = {"critical": ["python"], "moderate": ["microservices"], "low": ["xyz"]}
        with self._patch_get(self._make_score_mock(gaps=gaps)):
            result = get_job_skill_gap(user, _JOB_ID)
        assert result.soft_gaps == []

    def test_normalized_dicts_have_display_name_key(self):
        user = _make_user()
        with self._patch_get(self._make_score_mock()):
            result = get_job_skill_gap(user, _JOB_ID)
        for gap in result.critical_gaps:
            assert "display_name" in gap


# ─── VALID_RECOMMENDATION_TIERS ────────────────────────────────────────────────

class TestValidRecommendationTiers:
    def test_contains_critical(self):
        assert "critical" in VALID_RECOMMENDATION_TIERS

    def test_contains_moderate(self):
        assert "moderate" in VALID_RECOMMENDATION_TIERS

    def test_contains_soft(self):
        assert "soft" in VALID_RECOMMENDATION_TIERS

    def test_contains_all(self):
        assert "all" in VALID_RECOMMENDATION_TIERS

    def test_is_frozenset(self):
        assert isinstance(VALID_RECOMMENDATION_TIERS, frozenset)
