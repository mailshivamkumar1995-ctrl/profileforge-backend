"""
Unit tests for the recommendation scoring engine.

All functions are pure — no database, no network, no mocks required.
SimpleNamespace stubs stand in for Django model instances.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.career_hub.services.scoring import (
    ALGORITHM_VERSION,
    MIN_SAVED_FOR_SIMILARITY,
    SCORE_WEIGHTS,
    compute_score,
    location_score,
    normalize_skill,
    salary_overlap_score,
    saved_similarity_score,
    skill_score,
    title_score,
    tokenize,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _skill(name, proficiency="intermediate"):
    return SimpleNamespace(name=name, proficiency_level=proficiency)


def _job(**kwargs):
    defaults = dict(
        title="Python Developer",
        description="We need a skilled Python developer.",
        city="Bangalore",
        work_type="hybrid",
        salary_min=None,
        salary_max=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ─── normalize_skill ──────────────────────────────────────────────────────────

class TestNormalizeSkill:
    def test_lowercases_name(self):
        assert normalize_skill("Python") == "python"

    def test_strips_trailing_version_number(self):
        assert normalize_skill("Python 3") == "python"

    def test_strips_multi_part_version(self):
        assert normalize_skill("Django 4.2") == "django"

    def test_strips_deep_version(self):
        assert normalize_skill("Node.js 18.0.1") == "node.js"

    def test_preserves_multi_word_skill(self):
        assert normalize_skill("Machine Learning") == "machine learning"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_skill("  React.js  ") == "react.js"

    def test_preserves_tech_with_suffix(self):
        # "react.js" — the trailing ".js" is NOT a version number
        assert normalize_skill("React.js") == "react.js"

    def test_preserves_special_symbols(self):
        assert normalize_skill("C++") == "c++"

    def test_embedded_version_not_stripped(self):
        # "python3" — no space before digit, so not a version suffix
        assert normalize_skill("Python3") == "python3"


# ─── tokenize ─────────────────────────────────────────────────────────────────

class TestTokenize:
    def test_basic_split(self):
        assert "python" in tokenize("Python Developer")
        assert "developer" in tokenize("Python Developer")

    def test_empty_string_returns_empty_set(self):
        assert tokenize("") == set()

    def test_none_equivalent_empty(self):
        # Function signature expects str but defensively returns set()
        assert tokenize("") == set()

    def test_filters_stopwords(self):
        assert "the" not in tokenize("the python developer")
        assert "and" not in tokenize("python and django")

    def test_filters_single_char(self):
        tokens = tokenize("a b c python")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "python" in tokens

    def test_lowercases_tokens(self):
        assert "senior" in tokenize("Senior Engineer")

    def test_tech_token_with_dot(self):
        assert "node.js" in tokenize("Node.js developer")

    def test_tech_token_with_plus(self):
        assert "c++" in tokenize("C++ engineer")

    def test_returns_set_not_list(self):
        assert isinstance(tokenize("Python Python Python"), set)


# ─── skill_score ──────────────────────────────────────────────────────────────

class TestSkillScore:
    def test_empty_skills_returns_zero(self):
        assert skill_score([], "Python developer role") == 0.0

    def test_single_skill_found_returns_nonzero(self):
        skills = [_skill("Python")]
        assert skill_score(skills, "Looking for a Python developer") > 0.0

    def test_single_skill_not_found_returns_zero(self):
        skills = [_skill("Kubernetes")]
        assert skill_score(skills, "Looking for a Python developer") == 0.0

    def test_all_skills_found_returns_one(self):
        skills = [_skill("Python"), _skill("Django")]
        score = skill_score(skills, "Python Django developer role")
        assert score == 1.0

    def test_expert_skill_weights_more_than_beginner(self):
        # Expert Python found, beginner Kubernetes not found
        skills_expert = [_skill("Python", "expert"), _skill("Kubernetes", "beginner")]
        # Beginner Python found, expert Kubernetes not found
        skills_beginner = [_skill("Python", "beginner"), _skill("Kubernetes", "expert")]
        job_text = "Python developer role"
        score_expert_found = skill_score(skills_expert, job_text)
        score_beginner_found = skill_score(skills_beginner, job_text)
        assert score_expert_found > score_beginner_found

    def test_multi_word_skill_matched(self):
        skills = [_skill("Machine Learning")]
        score = skill_score(skills, "We need a Machine Learning engineer")
        assert score > 0.0

    def test_multi_word_skill_no_partial_match(self):
        # "Machine" appears in text but not as "Machine Learning"
        skills = [_skill("Machine Learning")]
        score = skill_score(skills, "We need a machine to do this")
        assert score == 0.0

    def test_case_insensitive_match(self):
        skills = [_skill("python")]
        assert skill_score(skills, "PYTHON DEVELOPER") > 0.0

    def test_java_does_not_match_javascript(self):
        skills = [_skill("java")]
        score = skill_score(skills, "JavaScript developer role")
        assert score == 0.0

    def test_returns_float_bounded(self):
        skills = [_skill("Python", "expert")]
        score = skill_score(skills, "Python Python Python Python developer")
        assert 0.0 <= score <= 1.0


# ─── title_score ──────────────────────────────────────────────────────────────

class TestTitleScore:
    def test_no_headline_no_titles_returns_zero(self):
        assert title_score("", [], "Python Developer") == 0.0

    def test_exact_match_returns_one(self):
        assert title_score("Python Developer", [], "Python Developer") == 1.0

    def test_partial_match_returns_fraction(self):
        score = title_score("Python Developer", [], "Senior Python Developer")
        # job_tokens = {senior, python, developer} — candidate tokens = {python, developer}
        # overlap = 2, len(job_tokens) = 3 → score = 2/3
        assert 0.0 < score < 1.0

    def test_no_overlap_returns_zero(self):
        assert title_score("Marketing Manager", [], "Python Developer") == 0.0

    def test_uses_current_titles(self):
        score = title_score("", ["Senior Python Developer"], "Python Developer")
        assert score > 0.0

    def test_headline_and_titles_combined(self):
        score_both = title_score("Python", ["Django Developer"], "Python Django Engineer")
        score_headline_only = title_score("Python", [], "Python Django Engineer")
        assert score_both >= score_headline_only

    def test_empty_job_title_returns_zero(self):
        assert title_score("Python Developer", [], "") == 0.0

    def test_returns_float_bounded(self):
        score = title_score("Senior Python Backend Developer Engineer", [], "Python")
        assert 0.0 <= score <= 1.0


# ─── location_score ───────────────────────────────────────────────────────────

class TestLocationScore:
    def test_remote_job_always_returns_one(self):
        assert location_score("Mumbai", "Delhi", "remote") == 1.0

    def test_remote_job_ignores_user_city(self):
        assert location_score("", "Delhi", "remote") == 1.0

    def test_city_match_returns_one(self):
        assert location_score("Bangalore", "Bangalore", "hybrid") == 1.0

    def test_city_substring_match_returns_one(self):
        # "Bangalore" is a substring of "Bangalore, Karnataka"
        assert location_score("Bangalore", "Bangalore, Karnataka", "hybrid") == 1.0

    def test_city_mismatch_returns_zero(self):
        assert location_score("Bangalore", "Mumbai", "hybrid") == 0.0

    def test_empty_user_city_returns_neutral(self):
        assert location_score("", "Bangalore", "hybrid") == 0.5

    def test_empty_job_city_returns_neutral(self):
        assert location_score("Bangalore", "", "hybrid") == 0.5

    def test_both_cities_empty_returns_neutral(self):
        assert location_score("", "", "onsite") == 0.5

    def test_case_insensitive_match(self):
        assert location_score("bangalore", "Bangalore", "hybrid") == 1.0


# ─── saved_similarity_score ───────────────────────────────────────────────────

class TestSavedSimilarityScore:
    def test_below_minimum_threshold_returns_zero(self):
        titles = ["Python Developer", "Django Engineer"]  # only 2
        assert saved_similarity_score(titles, "Python Developer") == 0.0

    def test_exactly_at_minimum_threshold_scores(self):
        titles = ["Python Developer", "Django Engineer", "Backend Python"]
        score = saved_similarity_score(titles, "Python Developer")
        assert score > 0.0

    def test_empty_saved_returns_zero(self):
        assert saved_similarity_score([], "Python Developer") == 0.0

    def test_matching_titles_return_nonzero(self):
        titles = ["Python Developer", "Python Engineer", "Backend Python Developer"]
        score = saved_similarity_score(titles, "Python Developer")
        assert score > 0.0

    def test_no_overlap_returns_zero(self):
        titles = ["Data Scientist", "ML Engineer", "Research Scientist"]
        score = saved_similarity_score(titles, "Frontend React Developer")
        assert score == 0.0

    def test_returns_float_bounded(self):
        titles = ["Python", "Python", "Python"]
        score = saved_similarity_score(titles, "Python")
        assert 0.0 <= score <= 1.0

    def test_min_saved_constant_is_three(self):
        assert MIN_SAVED_FOR_SIMILARITY == 3


# ─── salary_overlap_score ─────────────────────────────────────────────────────

class TestSalaryOverlapScore:
    def test_no_job_salary_returns_neutral(self):
        assert salary_overlap_score(Decimal("1000000"), Decimal("2000000"), None, None) == 0.5

    def test_no_user_expectation_returns_neutral(self):
        assert salary_overlap_score(None, None, Decimal("1000000"), Decimal("2000000")) == 0.5

    def test_both_null_returns_neutral(self):
        assert salary_overlap_score(None, None, None, None) == 0.5

    def test_overlapping_ranges_returns_one(self):
        assert salary_overlap_score(
            Decimal("1000000"), Decimal("2000000"),
            Decimal("1500000"), Decimal("2500000"),
        ) == 1.0

    def test_adjacent_ranges_returns_one(self):
        # lo == hi is still an overlap (single-point intersection)
        assert salary_overlap_score(
            Decimal("1000000"), Decimal("1500000"),
            Decimal("1500000"), Decimal("2000000"),
        ) == 1.0

    def test_non_overlapping_ranges_returns_zero(self):
        assert salary_overlap_score(
            Decimal("3000000"), Decimal("4000000"),
            Decimal("1000000"), Decimal("2000000"),
        ) == 0.0

    def test_user_range_fully_inside_job_range(self):
        assert salary_overlap_score(
            Decimal("1200000"), Decimal("1800000"),
            Decimal("1000000"), Decimal("2000000"),
        ) == 1.0


# ─── compute_score ────────────────────────────────────────────────────────────

class TestComputeScore:
    def _default_kwargs(self, **overrides):
        kwargs = dict(
            skills=[],
            headline="",
            current_titles=[],
            user_city="",
            saved_job_titles=[],
            expected_salary_min=None,
            expected_salary_max=None,
            job=_job(),
        )
        kwargs.update(overrides)
        return kwargs

    def test_returns_total_decimal(self):
        result = compute_score(**self._default_kwargs())
        assert isinstance(result["total"], Decimal)

    def test_returns_breakdown_dict(self):
        result = compute_score(**self._default_kwargs())
        bd = result["breakdown"]
        assert set(bd.keys()) == {"skill", "title", "location", "saved", "salary"}

    def test_total_has_three_decimal_places(self):
        result = compute_score(**self._default_kwargs())
        # quantize to 0.001 — check the string representation has 3dp
        assert str(result["total"]).count(".") == 1
        _, decimals = str(result["total"]).split(".")
        assert len(decimals) == 3

    def test_total_bounded_between_zero_and_one(self):
        result = compute_score(**self._default_kwargs())
        assert Decimal("0") <= result["total"] <= Decimal("1")

    def test_no_signals_gives_minimum_nonzero_from_neutral_salary_location(self):
        # Empty profile, non-remote job with no salary → location=0.5, salary=0.5
        result = compute_score(**self._default_kwargs())
        expected_floor = Decimal(str(
            SCORE_WEIGHTS["location"] * 0.5 + SCORE_WEIGHTS["salary"] * 0.5
        )).quantize(Decimal("0.001"))
        assert result["total"] == expected_floor

    def test_strong_signals_produce_high_score(self):
        job = _job(title="Senior Python Developer", city="Bangalore", work_type="hybrid")
        skills = [_skill("python", "expert"), _skill("django", "advanced")]
        saved = ["Python Developer", "Backend Python Engineer", "Django API Developer"]
        result = compute_score(
            skills=skills,
            headline="Senior Python Developer",
            current_titles=["Senior Python Developer"],
            user_city="Bangalore",
            saved_job_titles=saved,
            expected_salary_min=None,
            expected_salary_max=None,
            job=job,
        )
        assert result["total"] >= Decimal("0.600")

    def test_algorithm_version_constant(self):
        assert ALGORITHM_VERSION == "v1"

    def test_score_weights_sum_to_one(self):
        total = sum(SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_breakdown_values_are_floats(self):
        result = compute_score(**self._default_kwargs())
        for v in result["breakdown"].values():
            assert isinstance(v, float)
