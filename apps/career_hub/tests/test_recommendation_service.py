"""
Tests for RecommendationService.

All ORM calls are mocked — no database required.
Tests validate cold-start paths, scoring delegation, top-N limiting,
persistence (upsert), stale removal, and user isolation.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from apps.career_hub.services.recommendations import (
    CATALOG_CAP,
    EXPIRES_HOURS,
    TOP_N,
    RecommendationResult,
    RecommendationService,
    _infer_salary_expectation,
)
from apps.profiles.models import UserProfile


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user_id():
    return str(uuid.uuid4())


def _make_profile(
    *,
    onboarding_complete=True,
    headline="Senior Python Developer",
    location=None,
    skills=None,
    work_experiences=None,
):
    profile = MagicMock()
    profile.onboarding_complete = onboarding_complete
    profile.headline = headline
    profile.location = location if location is not None else {"city": "Bangalore"}
    profile.user = MagicMock()
    profile.user.id = uuid.uuid4()

    mock_skills_qs = MagicMock()
    mock_skills_qs.all.return_value = skills or []
    profile.skills = mock_skills_qs

    mock_exp_qs = MagicMock()
    mock_exp_qs.all.return_value = work_experiences or []
    profile.work_experiences = mock_exp_qs

    return profile


def _make_skill(name="Python", proficiency="intermediate"):
    return SimpleNamespace(name=name, proficiency_level=proficiency)


def _make_work_exp(job_title="Python Developer", is_current=True, start_date=None):
    from datetime import date
    return SimpleNamespace(
        job_title=job_title,
        is_current=is_current,
        start_date=start_date or date(2023, 1, 1),
    )


def _make_job(title="Python Developer", city="Bangalore", work_type="hybrid"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        title=title,
        description="A Python developer role.",
        city=city,
        work_type=work_type,
        salary_min=None,
        salary_max=None,
        posted_at=None,
    )


def _make_user_job(job_title=None):
    job = _make_job(title=job_title or "Python Developer")
    uj = MagicMock()
    uj.job = job
    return uj


def _patch_profile_get(profile):
    """Return a patch that makes UserProfile.objects....get() return the given profile."""
    return patch(
        "apps.career_hub.services.recommendations.UserProfile.objects",
        **{
            "select_related.return_value.prefetch_related.return_value.get.return_value": profile,
        },
    )


# ─── Cold-start paths ─────────────────────────────────────────────────────────

class TestColdStartNoProfile:
    def test_returns_skipped_result(self):
        with patch("apps.career_hub.services.recommendations.UserProfile.objects") as mock_objs:
            mock_objs.select_related.return_value.prefetch_related.return_value.get.side_effect = (
                UserProfile.DoesNotExist()
            )
            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.skipped is True
        assert result.skip_reason == "no_profile"
        assert result.jobs_scored == 0
        assert result.recommendations_persisted == 0


class TestColdStartOnboardingIncomplete:
    def test_returns_skipped_result(self):
        profile = _make_profile(onboarding_complete=False)
        with _patch_profile_get(profile):
            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.skipped is True
        assert result.skip_reason == "onboarding_incomplete"


class TestColdStartNoProfileData:
    def test_no_skills_and_no_work_exp_returns_skipped(self):
        profile = _make_profile(skills=[], work_experiences=[])
        with _patch_profile_get(profile):
            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.skipped is True
        assert result.skip_reason == "no_profile_data"

    def test_skills_only_is_not_cold_start(self):
        profile = _make_profile(
            skills=[_make_skill()],
            work_experiences=[],
        )
        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
            patch("apps.career_hub.services.recommendations.JobRecommendation.objects"),
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = []
            mock_jobs.filter.return_value.__getitem__.return_value = []
            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.skipped is False

    def test_work_exp_only_is_not_cold_start(self):
        profile = _make_profile(
            skills=[],
            work_experiences=[_make_work_exp()],
        )
        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
            patch("apps.career_hub.services.recommendations.JobRecommendation.objects"),
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = []
            mock_jobs.filter.return_value.__getitem__.return_value = []
            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.skipped is False


# ─── Empty catalog ────────────────────────────────────────────────────────────

class TestEmptyCatalog:
    def test_returns_zero_scored_when_no_active_jobs(self):
        profile = _make_profile(
            skills=[_make_skill()],
            work_experiences=[_make_work_exp()],
        )
        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = []
            mock_jobs.filter.return_value.__getitem__.return_value = []

            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.skipped is False
        assert result.jobs_scored == 0
        assert result.recommendations_persisted == 0


# ─── Scoring and persistence ──────────────────────────────────────────────────

class TestScoringAndPersistence:
    def _run_with_jobs(self, jobs, saved_user_jobs=None):
        profile = _make_profile(
            skills=[_make_skill("Python", "expert")],
            work_experiences=[_make_work_exp("Python Developer", is_current=True)],
        )
        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
            patch("apps.career_hub.services.recommendations.JobRecommendation.objects") as mock_rec,
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = (
                saved_user_jobs or []
            )
            mock_jobs.filter.return_value.__getitem__.return_value = jobs
            mock_rec.update_or_create.return_value = (MagicMock(), True)
            mock_rec.filter.return_value.exclude.return_value.delete.return_value = (0, {})
            mock_rec.filter.return_value.filter.return_value.delete.return_value = (0, {})

            result = RecommendationService().generate_for_user(_make_user_id())

        return result, mock_rec

    def test_scores_all_catalog_jobs(self):
        jobs = [_make_job(f"Job {i}") for i in range(5)]
        result, _ = self._run_with_jobs(jobs)
        assert result.jobs_scored == 5

    def test_persists_top_n_when_catalog_larger_than_top_n(self):
        # TOP_N = 50; provide more than 50 jobs
        jobs = [_make_job(f"Job {i}") for i in range(TOP_N + 10)]
        result, mock_rec = self._run_with_jobs(jobs)
        assert result.recommendations_persisted == TOP_N
        assert mock_rec.update_or_create.call_count == TOP_N

    def test_persists_all_when_catalog_smaller_than_top_n(self):
        jobs = [_make_job(f"Job {i}") for i in range(3)]
        result, mock_rec = self._run_with_jobs(jobs)
        assert result.recommendations_persisted == 3
        assert mock_rec.update_or_create.call_count == 3

    def test_upsert_called_with_correct_kwargs(self):
        jobs = [_make_job("Python Developer", city="Bangalore")]
        _, mock_rec = self._run_with_jobs(jobs)

        call_kwargs = mock_rec.update_or_create.call_args
        assert "defaults" in call_kwargs.kwargs
        defaults = call_kwargs.kwargs["defaults"]
        assert "score" in defaults
        assert "score_breakdown" in defaults
        assert "algorithm_version" in defaults
        assert defaults["algorithm_version"] == "v1"
        assert "expires_at" in defaults

    def test_upsert_lookup_uses_user_and_job(self):
        jobs = [_make_job()]
        _, mock_rec = self._run_with_jobs(jobs)

        call_kwargs = mock_rec.update_or_create.call_args
        assert "user" in call_kwargs.kwargs
        assert "job" in call_kwargs.kwargs

    def test_result_is_not_skipped_on_success(self):
        jobs = [_make_job()]
        result, _ = self._run_with_jobs(jobs)
        assert result.skipped is False

    def test_elapsed_ms_is_populated(self):
        jobs = [_make_job()]
        result, _ = self._run_with_jobs(jobs)
        assert result.elapsed_ms > 0.0


# ─── Stale removal ────────────────────────────────────────────────────────────

class TestStaleRemoval:
    def test_stale_non_dismissed_recs_excluded_from_top_n_are_deleted(self):
        profile = _make_profile(
            skills=[_make_skill()],
            work_experiences=[_make_work_exp()],
        )
        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
            patch("apps.career_hub.services.recommendations.JobRecommendation.objects") as mock_rec,
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = []
            mock_jobs.filter.return_value.__getitem__.return_value = [_make_job()]
            mock_rec.update_or_create.return_value = (MagicMock(), True)

            stale_qs = MagicMock()
            stale_qs.delete.return_value = (3, {"career_hub_job_recommendation": 3})
            mock_rec.filter.return_value.exclude.return_value = stale_qs

            inactive_qs = MagicMock()
            inactive_qs.delete.return_value = (0, {})
            mock_rec.filter.return_value.filter.return_value = inactive_qs

            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.stale_removed == 3

    def test_stale_count_includes_inactive_job_recs(self):
        profile = _make_profile(
            skills=[_make_skill()],
            work_experiences=[_make_work_exp()],
        )
        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
            patch("apps.career_hub.services.recommendations.JobRecommendation.objects") as mock_rec,
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = []
            mock_jobs.filter.return_value.__getitem__.return_value = [_make_job()]
            mock_rec.update_or_create.return_value = (MagicMock(), True)

            stale_qs = MagicMock()
            stale_qs.delete.return_value = (2, {})
            mock_rec.filter.return_value.exclude.return_value = stale_qs

            inactive_qs = MagicMock()
            inactive_qs.delete.return_value = (1, {})
            mock_rec.filter.return_value.filter.return_value = inactive_qs

            result = RecommendationService().generate_for_user(_make_user_id())

        assert result.stale_removed == 3  # 2 stale + 1 inactive


# ─── Current title fallback ───────────────────────────────────────────────────

class TestCurrentTitleFallback:
    def test_uses_most_recent_when_no_current_role(self):
        from datetime import date
        older_exp = _make_work_exp("Junior Python Dev", is_current=False, start_date=date(2020, 1, 1))
        newer_exp = _make_work_exp("Senior Python Dev", is_current=False, start_date=date(2023, 1, 1))

        profile = _make_profile(
            skills=[_make_skill("Python", "expert")],
            work_experiences=[older_exp, newer_exp],
        )

        captured_call_kwargs: list[dict] = []

        def fake_compute_score(**kwargs):
            captured_call_kwargs.append(kwargs)
            from decimal import Decimal
            return {"total": Decimal("0.500"), "breakdown": {
                "skill": 0.5, "title": 0.5, "location": 0.5, "saved": 0.0, "salary": 0.5
            }}

        with (
            _patch_profile_get(profile),
            patch("apps.career_hub.services.recommendations.UserJob.objects") as mock_uj,
            patch("apps.career_hub.services.recommendations.Job.objects") as mock_jobs,
            patch("apps.career_hub.services.recommendations.JobRecommendation.objects") as mock_rec,
            patch("apps.career_hub.services.recommendations.compute_score", fake_compute_score),
        ):
            mock_uj.filter.return_value.exclude.return_value.select_related.return_value = []
            mock_jobs.filter.return_value.__getitem__.return_value = [_make_job()]
            mock_rec.update_or_create.return_value = (MagicMock(), True)
            mock_rec.filter.return_value.exclude.return_value.delete.return_value = (0, {})
            mock_rec.filter.return_value.filter.return_value.delete.return_value = (0, {})

            RecommendationService().generate_for_user(_make_user_id())

        assert len(captured_call_kwargs) == 1
        assert "Senior Python Dev" in captured_call_kwargs[0]["current_titles"]


# ─── _infer_salary_expectation ────────────────────────────────────────────────

class TestInferSalaryExpectation:
    def test_no_saved_jobs_returns_none_none(self):
        assert _infer_salary_expectation([]) == (None, None)

    def test_no_salary_data_in_saved_jobs_returns_none_none(self):
        job = SimpleNamespace(salary_min=None, salary_max=None)
        assert _infer_salary_expectation([job]) == (None, None)

    def test_returns_median_of_salary_mins(self):
        jobs = [
            SimpleNamespace(salary_min=Decimal("1000000"), salary_max=None),
            SimpleNamespace(salary_min=Decimal("1500000"), salary_max=None),
            SimpleNamespace(salary_min=Decimal("2000000"), salary_max=None),
        ]
        expected_min, expected_max = _infer_salary_expectation(jobs)
        assert expected_min == Decimal("1500000.00")
        assert expected_max is None

    def test_returns_median_of_salary_maxs(self):
        jobs = [
            SimpleNamespace(salary_min=None, salary_max=Decimal("2000000")),
            SimpleNamespace(salary_min=None, salary_max=Decimal("3000000")),
            SimpleNamespace(salary_min=None, salary_max=Decimal("4000000")),
        ]
        expected_min, expected_max = _infer_salary_expectation(jobs)
        assert expected_min is None
        assert expected_max == Decimal("3000000.00")

    def test_returns_both_when_full_data(self):
        jobs = [
            SimpleNamespace(salary_min=Decimal("1000000"), salary_max=Decimal("2000000")),
            SimpleNamespace(salary_min=Decimal("1200000"), salary_max=Decimal("2200000")),
            SimpleNamespace(salary_min=Decimal("1400000"), salary_max=Decimal("2400000")),
        ]
        expected_min, expected_max = _infer_salary_expectation(jobs)
        assert expected_min == Decimal("1200000.00")
        assert expected_max == Decimal("2200000.00")

    def test_ignores_nulls_in_mix(self):
        jobs = [
            SimpleNamespace(salary_min=Decimal("1000000"), salary_max=None),
            SimpleNamespace(salary_min=None, salary_max=Decimal("2000000")),
            SimpleNamespace(salary_min=Decimal("1500000"), salary_max=Decimal("2500000")),
        ]
        expected_min, expected_max = _infer_salary_expectation(jobs)
        assert expected_min == Decimal("1250000.00")  # median of [1000000, 1500000]
        assert expected_max == Decimal("2250000.00")  # median of [2000000, 2500000]


# ─── RecommendationResult dataclass ───────────────────────────────────────────

class TestRecommendationResult:
    def test_defaults(self):
        r = RecommendationResult(user_id="test-id")
        assert r.skipped is False
        assert r.skip_reason == ""
        assert r.jobs_scored == 0
        assert r.recommendations_persisted == 0
        assert r.stale_removed == 0
        assert r.elapsed_ms == 0.0

    def test_constants(self):
        assert TOP_N == 50
        assert EXPIRES_HOURS == 24
        assert CATALOG_CAP == 5_000
