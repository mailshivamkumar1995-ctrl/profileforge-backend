"""
Unit tests for the resume match scoring engine (algorithm v2).

All functions are pure — no database, no network, no Django ORM.
SimpleNamespace stubs stand in for model instances.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.career_hub.services.match_scoring import (
    MATCH_ALGORITHM_VERSION,
    MATCH_WEIGHTS,
    MatchExplanation,
    _CERT_REQUIRED_KEYWORDS,
    _SOFT_SKILL_VOCAB,
    _TECH_VOCAB,
    _compute_years_of_experience,
    _extract_required_degree_level,
    _extract_required_years,
    _job_requires_certification,
    _normalize_degree_text,
    certification_score,
    compute_resume_match_score,
    education_score,
    experience_score,
    extract_skill_gaps,
    keyword_coverage_score,
    normalize_degree,
    salary_score,
    score_to_display,
    skills_score,
    title_score,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _skill(name: str, proficiency: str = "intermediate") -> SimpleNamespace:
    return SimpleNamespace(name=name, proficiency_level=proficiency)


def _we(
    job_title: str = "Software Engineer",
    start_date: date = date(2020, 1, 1),
    end_date: date | None = date(2023, 1, 1),
    is_current: bool = False,
    technologies: list[str] | None = None,
    description: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        job_title=job_title,
        start_date=start_date,
        end_date=end_date,
        is_current=is_current,
        technologies=technologies or [],
        description=description,
    )


def _edu(degree: str) -> SimpleNamespace:
    return SimpleNamespace(degree=degree)


def _cert(name: str, expiry_date: date | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, expiry_date=expiry_date)


def _proj(technologies: list[str] | None = None, description: str = "") -> SimpleNamespace:
    return SimpleNamespace(technologies=technologies or [], description=description)


def _job(**kwargs) -> SimpleNamespace:
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


_TODAY = date(2025, 6, 1)


# ─── score_to_display ─────────────────────────────────────────────────────────

class TestScoreToDisplay:
    def test_perfect_score(self):
        assert score_to_display(Decimal("1.000")) == 100

    def test_zero_score(self):
        assert score_to_display(Decimal("0.000")) == 0

    def test_typical_score(self):
        assert score_to_display(Decimal("0.847")) == 85

    def test_rounds_half_up(self):
        assert score_to_display(Decimal("0.855")) == 86

    def test_midpoint(self):
        assert score_to_display(Decimal("0.500")) == 50


# ─── _normalize_degree_text ───────────────────────────────────────────────────

class TestNormalizeDegreeText:
    def test_lowercases(self):
        assert _normalize_degree_text("Bachelor") == "bachelor"

    def test_strips_leading_trailing_whitespace(self):
        assert _normalize_degree_text("  B.Tech  ") == "b.tech"

    def test_collapses_internal_whitespace(self):
        assert _normalize_degree_text("Master  of  Science") == "master of science"

    def test_strips_possessive(self):
        assert _normalize_degree_text("Bachelor's") == "bachelor"

    def test_empty_string_returns_empty(self):
        assert _normalize_degree_text("") == ""

    def test_none_returns_empty(self):
        assert _normalize_degree_text(None) == ""

    def test_preserves_periods_in_abbreviations(self):
        assert _normalize_degree_text("B.Tech") == "b.tech"


# ─── normalize_degree ─────────────────────────────────────────────────────────

class TestNormalizeDegree:
    def test_none_input_returns_none(self):
        assert normalize_degree(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_degree("") is None

    def test_unknown_string_returns_none(self):
        assert normalize_degree("Klnfjdklsj") is None

    def test_phd_returns_5(self):
        assert normalize_degree("PhD") == 5

    def test_phd_dotted_returns_5(self):
        assert normalize_degree("Ph.D.") == 5

    def test_doctorate_returns_5(self):
        assert normalize_degree("Doctorate") == 5

    def test_mba_returns_4(self):
        assert normalize_degree("MBA") == 4

    def test_pgdm_returns_4_not_2(self):
        # PGDM contains "diploma" but exact alias "pgdm" is in MASTER_ALIASES
        assert normalize_degree("PGDM") == 4

    def test_master_returns_4(self):
        assert normalize_degree("Master") == 4

    def test_btech_returns_3(self):
        assert normalize_degree("B.Tech") == 3

    def test_be_returns_3(self):
        assert normalize_degree("BE") == 3

    def test_bsc_returns_3(self):
        assert normalize_degree("BSc") == 3

    def test_bachelor_returns_3(self):
        assert normalize_degree("Bachelor") == 3

    def test_diploma_returns_2(self):
        assert normalize_degree("Diploma") == 2

    def test_hsc_returns_1(self):
        assert normalize_degree("HSC") == 1

    def test_secondary_returns_1(self):
        assert normalize_degree("Secondary") == 1

    def test_substring_btech_in_field(self):
        assert normalize_degree("B.Tech in Computer Science") == 3

    def test_substring_master_of_science(self):
        assert normalize_degree("Master of Science in Data Science") == 4

    def test_post_graduate_diploma_returns_4(self):
        # "post graduate" (level 4) and "diploma" (level 2) both match; max wins
        assert normalize_degree("Post Graduate Diploma") == 4

    def test_bachelor_possessive_form(self):
        assert normalize_degree("Bachelor's") == 3

    def test_msc_returns_4(self):
        assert normalize_degree("MSc") == 4

    def test_case_insensitive(self):
        assert normalize_degree("BACHELOR OF ENGINEERING") == 3


# ─── _extract_required_degree_level ──────────────────────────────────────────

class TestExtractRequiredDegreeLevel:
    def test_bachelor_in_description(self):
        assert _extract_required_degree_level("Bachelor's degree required") == 3

    def test_mba_required(self):
        assert _extract_required_degree_level("MBA required") == 4

    def test_phd_preferred(self):
        assert _extract_required_degree_level("PhD preferred") == 5

    def test_no_degree_mentioned_returns_none(self):
        assert _extract_required_degree_level("Strong Python skills required") is None

    def test_minimum_when_multiple_degrees(self):
        # "Bachelor or Master" → min(3, 4) = 3
        result = _extract_required_degree_level("Bachelor's or Master's degree required")
        assert result == 3

    def test_empty_returns_none(self):
        assert _extract_required_degree_level("") is None

    def test_btech_in_text(self):
        assert _extract_required_degree_level("B.Tech in CS or equivalent") == 3


# ─── _compute_years_of_experience ────────────────────────────────────────────

class TestComputeYearsOfExperience:
    def test_single_we(self):
        we = _we(start_date=date(2020, 1, 1), end_date=date(2023, 1, 1))
        years = _compute_years_of_experience([we], _TODAY)
        assert abs(years - 3.0) < 0.1

    def test_multiple_we_summed(self):
        wes = [
            _we(start_date=date(2018, 1, 1), end_date=date(2020, 1, 1)),
            _we(start_date=date(2020, 6, 1), end_date=date(2023, 1, 1)),
        ]
        years = _compute_years_of_experience(wes, _TODAY)
        assert years > 4.0

    def test_current_we_uses_today(self):
        we = _we(start_date=date(2023, 6, 1), end_date=None)
        years = _compute_years_of_experience([we], date(2025, 6, 1))
        assert abs(years - 2.0) < 0.1

    def test_no_start_date_skipped(self):
        we = SimpleNamespace(start_date=None, end_date=date(2023, 1, 1))
        years = _compute_years_of_experience([we], _TODAY)
        assert years == 0.0

    def test_empty_list_returns_zero(self):
        assert _compute_years_of_experience([], _TODAY) == 0.0

    def test_end_before_start_excluded(self):
        we = _we(start_date=date(2023, 1, 1), end_date=date(2022, 1, 1))
        years = _compute_years_of_experience([we], _TODAY)
        assert years == 0.0

    def test_none_work_experiences_returns_zero(self):
        assert _compute_years_of_experience(None, _TODAY) == 0.0


# ─── _extract_required_years ──────────────────────────────────────────────────

class TestExtractRequiredYears:
    def test_x_plus_years(self):
        assert _extract_required_years("", "3+ years of Python experience") == 3

    def test_x_years_of_experience(self):
        assert _extract_required_years("", "5 years of experience required") == 5

    def test_range_returns_min(self):
        assert _extract_required_years("", "2-4 years experience") == 2

    def test_multiple_values_returns_min(self):
        assert _extract_required_years("", "3+ years required, 5 years preferred") == 3

    def test_no_pattern_returns_none(self):
        assert _extract_required_years("", "Strong Python skills needed") is None

    def test_empty_returns_none(self):
        assert _extract_required_years("", "") is None

    def test_title_also_checked(self):
        assert _extract_required_years("5 Years Senior Engineer", "") == 5

    def test_unrealistic_value_filtered(self):
        # 50 years > 30 cap → filtered out → None
        assert _extract_required_years("", "50 years experience") is None

    def test_zero_years_filtered(self):
        # 0 is below 1 → filtered
        assert _extract_required_years("", "0 years experience") is None


# ─── _job_requires_certification ──────────────────────────────────────────────

class TestJobRequiresCertification:
    def test_certified_token_triggers(self):
        assert _job_requires_certification({"certified"}) is True

    def test_pmp_triggers(self):
        assert _job_requires_certification({"pmp", "experience", "python"}) is True

    def test_no_cert_tokens_false(self):
        assert _job_requires_certification({"python", "django", "react"}) is False

    def test_empty_tokens_false(self):
        assert _job_requires_certification(set()) is False

    def test_cissp_triggers(self):
        assert _job_requires_certification({"cissp", "security"}) is True


# ─── skills_score ─────────────────────────────────────────────────────────────

class TestSkillsScore:
    def test_empty_skills_and_tech_returns_zero(self):
        assert skills_score([], [], [], "Python Django developer") == 0.0

    def test_all_skills_matched(self):
        s = [_skill("Python"), _skill("Django")]
        assert skills_score(s, [], [], "Python Django developer needed") == 1.0

    def test_no_skills_matched(self):
        s = [_skill("Java"), _skill("Spring")]
        assert skills_score(s, [], [], "Python Django developer needed") == 0.0

    def test_partial_match(self):
        s = [_skill("Python"), _skill("Java")]
        score = skills_score(s, [], [], "Python developer")
        assert 0.0 < score < 1.0

    def test_we_technologies_counted(self):
        score = skills_score([], ["Python"], [], "Python developer")
        assert score > 0.0

    def test_project_technologies_counted(self):
        score = skills_score([], [], ["React"], "React frontend developer")
        assert score > 0.0

    def test_deduplication_we_not_double_counted(self):
        s = [_skill("Python", "expert")]
        score_with_dup = skills_score(s, ["Python"], [], "Python developer")
        score_without_dup = skills_score(s, [], [], "Python developer")
        assert score_with_dup == score_without_dup

    def test_expert_weight_higher_contribution(self):
        # Expert on matched skill: found=1.0, total=1.0 → 1.0
        score_expert = skills_score([_skill("Python", "expert")], [], [], "Python developer")
        # Beginner on 2 skills, only 1 matches: found=0.2, total=0.4 → 0.5
        score_beginner = skills_score(
            [_skill("Python", "beginner"), _skill("Java", "beginner")], [], [], "Python developer"
        )
        assert score_expert > score_beginner

    def test_none_inputs_safe(self):
        assert skills_score(None, None, None, "Python developer") == 0.0


# ─── experience_score ─────────────────────────────────────────────────────────

class TestExperienceScore:
    def test_exceeds_requirement_returns_1(self):
        we = [_we(start_date=date(2018, 1, 1), end_date=date(2023, 1, 1))]
        score = experience_score(we, "Engineer", "3+ years required", _TODAY)
        assert score == 1.0

    def test_gap_one_year_returns_0_8(self):
        # ~2.5 years vs 3 required → gap ≈ 0.5 → ≤1 → 0.8
        we = [_we(start_date=date(2022, 1, 1), end_date=date(2024, 7, 1))]
        score = experience_score(we, "Engineer", "3+ years required", _TODAY)
        assert score == 0.8

    def test_gap_two_years_returns_0_6(self):
        # 1 year vs 3 → gap = 2
        we = [_we(start_date=date(2024, 1, 1), end_date=date(2025, 1, 1))]
        score = experience_score(we, "Engineer", "3+ years required", _TODAY)
        assert score == 0.6

    def test_gap_four_years_returns_0_4(self):
        # 1 year vs 5 → gap = 4
        we = [_we(start_date=date(2024, 1, 1), end_date=date(2025, 1, 1))]
        score = experience_score(we, "Engineer", "5+ years required", _TODAY)
        assert score == 0.4

    def test_large_gap_returns_0_2(self):
        # 0 years vs 5 → gap = 5 > 4
        score = experience_score([], "Engineer", "5+ years required", _TODAY)
        assert score == 0.2

    def test_no_requirement_signal_neutral(self):
        we = [_we()]
        score = experience_score(we, "Engineer", "Great opportunity!", _TODAY)
        assert score == 0.7

    def test_seniority_keyword_in_title(self):
        # Senior → 4 years required, user has 0 → gap=4, score=0.4
        score = experience_score([], "Senior Software Engineer", "Exciting role", _TODAY)
        assert score == 0.4

    def test_exact_years_met(self):
        we = [_we(start_date=date(2022, 6, 1), end_date=date(2025, 6, 1))]
        score = experience_score(we, "Engineer", "3 years of experience", _TODAY)
        assert score == 1.0

    def test_today_injectable(self):
        we = [_we(start_date=date(2022, 1, 1), end_date=None)]
        score = experience_score(we, "Engineer", "1+ years experience", date(2024, 1, 1))
        assert score == 1.0

    def test_intern_seniority_zero_years(self):
        # "intern" → 0 years required; user has 0 → meets requirement → 1.0
        score = experience_score([], "Intern Python Developer", "Great role", _TODAY)
        assert score == 1.0


# ─── keyword_coverage_score ───────────────────────────────────────────────────

class TestKeywordCoverageScore:
    def test_full_coverage(self):
        score = keyword_coverage_score("python django", [], [], [], [], "python django")
        assert score == 1.0

    def test_partial_coverage(self):
        score = keyword_coverage_score("python", [], [], [], [], "python django aws")
        assert 0.0 < score < 1.0

    def test_empty_profile_returns_zero(self):
        score = keyword_coverage_score("", [], [], [], [], "python developer")
        assert score == 0.0

    def test_empty_job_description_returns_zero(self):
        score = keyword_coverage_score("python developer", [], [], [], [], "")
        assert score == 0.0

    def test_we_texts_contribute(self):
        score = keyword_coverage_score("", [], ["python django"], [], [], "python django developer")
        assert score > 0.0

    def test_ats_keywords_contribute(self):
        score = keyword_coverage_score("", ["python", "django"], [], [], [], "python django developer")
        assert score > 0.0

    def test_project_texts_contribute(self):
        score = keyword_coverage_score("", [], [], ["built with react"], [], "react developer")
        assert score > 0.0

    def test_custom_sections_contribute(self):
        score = keyword_coverage_score("", [], [], [], ["kubernetes docker"], "kubernetes docker")
        assert score == 1.0

    def test_capped_at_one(self):
        score = keyword_coverage_score(
            "python django aws react node typescript",
            ["kubernetes docker postgresql redis"],
            [], [], [],
            "python",
        )
        assert score <= 1.0


# ─── title_score ──────────────────────────────────────────────────────────────

class TestTitleScore:
    def test_full_match(self):
        score = title_score("Python Developer", [], "", "Python Developer")
        assert score == 1.0

    def test_no_match(self):
        score = title_score("Java Engineer", [], "", "Python Developer")
        assert score == 0.0

    def test_partial_match(self):
        score = title_score("Python Architect", [], "", "Python Developer")
        assert 0.0 < score < 1.0

    def test_target_role_contributes(self):
        score = title_score("", [], "Senior Python Developer", "Python Developer")
        assert score > 0.0

    def test_current_titles_contribute(self):
        score = title_score("", ["Python Engineer"], "", "Python Developer")
        assert score > 0.0

    def test_empty_identity_returns_zero(self):
        score = title_score("", [], "", "Python Developer")
        assert score == 0.0

    def test_empty_job_title_returns_zero(self):
        score = title_score("Python Developer", [], "", "")
        assert score == 0.0

    def test_none_current_titles_safe(self):
        score = title_score("Python Developer", None, "", "Python Developer")
        assert score == 1.0


# ─── education_score ──────────────────────────────────────────────────────────

class TestEducationScore:
    def test_exact_match(self):
        edu = [_edu("B.Tech")]
        score = education_score(edu, "Engineer", "Bachelor's degree required")
        assert score == 1.0

    def test_exceeds_requirement(self):
        edu = [_edu("MBA")]
        score = education_score(edu, "Analyst", "Bachelor's degree required")
        assert score == 1.0

    def test_one_level_below(self):
        # Diploma (2) vs Bachelor required (3) → gap = 1
        edu = [_edu("Diploma")]
        score = education_score(edu, "Engineer", "Bachelor's required")
        assert score == 0.7

    def test_two_levels_below(self):
        # HSC (1) vs Bachelor required (3) → gap = 2
        edu = [_edu("HSC")]
        score = education_score(edu, "Engineer", "Bachelor's required")
        assert score == 0.4

    def test_three_levels_below(self):
        # HSC (1) vs PhD required (5) → gap = 4 → 0.1
        edu = [_edu("HSC")]
        score = education_score(edu, "Researcher", "PhD required")
        assert score == 0.1

    def test_no_educations_neutral(self):
        score = education_score([], "Engineer", "Bachelor's required")
        assert score == 0.7

    def test_no_requirement_neutral(self):
        edu = [_edu("B.Tech")]
        score = education_score(edu, "Developer", "Strong Python skills")
        assert score == 0.7

    def test_unrecognized_degree_neutral(self):
        edu = [_edu("Unknown Institute Degree XYZ")]
        score = education_score(edu, "Engineer", "Bachelor's required")
        assert score == 0.7

    def test_highest_degree_used_multiple_educations(self):
        # HSC (1) + MBA (4); max = 4; required = 3 → gap = -1 → 1.0
        edu = [_edu("HSC"), _edu("MBA")]
        score = education_score(edu, "Manager", "Bachelor's degree required")
        assert score == 1.0

    def test_masters_meets_masters_requirement(self):
        edu = [_edu("MSc")]
        score = education_score(edu, "Data Scientist", "Master's degree required")
        assert score == 1.0


# ─── certification_score ──────────────────────────────────────────────────────

class TestCertificationScore:
    def test_no_certs_no_requirement_neutral(self):
        score = certification_score([], "Python Django developer")
        assert score == 0.5

    def test_no_certs_required_low(self):
        score = certification_score([], "PMP certified project manager required")
        assert score == 0.2

    def test_matching_cert_required_high(self):
        certs = [_cert("PMP Certification")]
        score = certification_score(certs, "PMP project manager required")
        assert score == 1.0

    def test_non_matching_cert_required_mid(self):
        certs = [_cert("AWS Solutions Architect")]
        score = certification_score(certs, "PMP project manager required")
        assert score == 0.5

    def test_cert_no_requirement_no_token_overlap(self):
        certs = [_cert("AWS Solutions Architect")]
        score = certification_score(certs, "Python developer databases")
        assert score == 0.5

    def test_cert_with_token_overlap_no_requirement(self):
        certs = [_cert("AWS Solutions Architect")]
        score = certification_score(certs, "AWS cloud developer needed")
        assert score == 0.8

    def test_expired_cert_excluded(self):
        certs = [_cert("PMP Certification", expiry_date=date(2024, 1, 1))]
        score = certification_score(certs, "PMP certified required", today=date(2025, 1, 1))
        assert score == 0.2

    def test_unexpired_cert_valid(self):
        certs = [_cert("PMP Certification", expiry_date=date(2026, 1, 1))]
        score = certification_score(certs, "PMP certified required", today=date(2025, 1, 1))
        assert score == 1.0

    def test_mixed_expired_and_valid(self):
        certs = [
            _cert("Old AWS Cert", expiry_date=date(2023, 1, 1)),
            _cert("AWS Solutions Architect", expiry_date=date(2026, 1, 1)),
        ]
        score = certification_score(certs, "AWS certified cloud developer", today=date(2025, 1, 1))
        assert score == 1.0

    def test_cert_without_expiry_always_valid(self):
        certs = [_cert("PMP Certification", expiry_date=None)]
        score = certification_score(certs, "PMP certified required", today=date(2030, 1, 1))
        assert score == 1.0


# ─── salary_score ─────────────────────────────────────────────────────────────

class TestSalaryScore:
    def test_both_missing_neutral(self):
        assert salary_score(None, None, None, None) == 0.5

    def test_job_missing_neutral(self):
        assert salary_score(Decimal("500000"), Decimal("800000"), None, None) == 0.5

    def test_user_missing_neutral(self):
        assert salary_score(None, None, Decimal("500000"), Decimal("800000")) == 0.5

    def test_ranges_overlap_full(self):
        assert salary_score(
            Decimal("500000"), Decimal("900000"),
            Decimal("600000"), Decimal("1000000"),
        ) == 1.0

    def test_ranges_no_overlap(self):
        assert salary_score(
            Decimal("200000"), Decimal("400000"),
            Decimal("600000"), Decimal("900000"),
        ) == 0.0


# ─── extract_skill_gaps ───────────────────────────────────────────────────────

class TestExtractSkillGaps:
    def test_python_in_job_not_in_profile_is_critical(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="We need Python and Django developers",
        )
        assert "python" in gaps["critical"]

    def test_known_skill_not_in_any_gap(self):
        gaps = extract_skill_gaps(
            skills=[_skill("Python")],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="We need Python and Django developers",
        )
        all_gaps = set(gaps["critical"] + gaps["moderate"] + gaps["low"])
        assert "python" not in all_gaps

    def test_we_tech_not_in_gaps(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=["Django"],
            project_technologies=[],
            certifications=[],
            job_description="Django Python REST developer",
        )
        all_gaps = set(gaps["critical"] + gaps["moderate"] + gaps["low"])
        assert "django" not in all_gaps

    def test_project_tech_not_in_gaps(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=["React"],
            certifications=[],
            job_description="React frontend developer",
        )
        all_gaps = set(gaps["critical"] + gaps["moderate"] + gaps["low"])
        assert "react" not in all_gaps

    def test_empty_job_description_all_empty(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="",
        )
        assert gaps == {"critical": [], "moderate": [], "soft": [], "low": []}

    def test_result_always_has_four_keys(self):
        gaps = extract_skill_gaps(
            skills=[_skill("Python"), _skill("Django")],
            work_experience_technologies=["React"],
            project_technologies=[],
            certifications=[],
            job_description="Python Django React developer",
        )
        assert set(gaps.keys()) == {"critical", "moderate", "soft", "low"}

    def test_soft_skill_in_job_not_in_profile_is_soft(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="We need leadership and ownership",
        )
        assert "leadership" in gaps["soft"]
        assert "ownership" in gaps["soft"]

    def test_soft_skill_excluded_when_in_user_profile(self):
        gaps = extract_skill_gaps(
            skills=[_skill("Leadership"), _skill("Ownership")],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="Strong leadership and ownership required",
        )
        all_gaps = set(gaps["critical"] + gaps["moderate"] + gaps["soft"] + gaps["low"])
        assert "leadership" not in all_gaps
        assert "ownership" not in all_gaps

    def test_agile_goes_to_soft_not_moderate(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="agile agile scrum methodology",
        )
        # agile is 5+ chars and appears 2x — without soft vocab it would be moderate
        assert "agile" in gaps["soft"]
        assert "agile" not in gaps["moderate"]

    def test_tech_skill_not_in_soft_tier(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="Python Docker developer",
        )
        assert "python" not in gaps["soft"]
        assert "docker" not in gaps["soft"]
        assert "python" in gaps["critical"]
        assert "docker" in gaps["critical"]

    def test_communication_now_appears_in_soft_tier(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="Strong communication and collaboration skills needed",
        )
        assert "communication" in gaps["soft"]
        assert "collaboration" in gaps["soft"]

    def test_soft_tier_empty_when_no_soft_skills_in_jd(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="Python Django PostgreSQL developer",
        )
        assert gaps["soft"] == []

    def test_scrum_in_soft_not_moderate(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="agile scrum scrum kanban",
        )
        assert "scrum" in gaps["soft"]
        assert "scrum" not in gaps["moderate"]

    def test_all_four_tiers_mutually_exclusive(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="python leadership agile methodology methodology",
        )
        all_tokens = gaps["critical"] + gaps["moderate"] + gaps["soft"] + gaps["low"]
        assert len(all_tokens) == len(set(all_tokens)), "Tiers must be mutually exclusive"

    def test_repeated_non_tech_long_word_in_moderate(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="agile agile scrum scrum methodology methodology",
        )
        # "agile" and "scrum" are in _SOFT_SKILL_VOCAB → soft tier
        # "methodology" (11 chars, 2x, not in any vocab) → moderate
        assert "agile" in gaps["soft"]
        assert "scrum" in gaps["soft"]
        assert "methodology" in gaps["moderate"]

    def test_gap_exclusions_not_in_gaps(self):
        gaps = extract_skill_gaps(
            skills=[],
            work_experience_technologies=[],
            project_technologies=[],
            certifications=[],
            job_description="experience required skills ability",
        )
        all_gaps = set(gaps["critical"] + gaps["moderate"] + gaps["low"])
        assert "experience" not in all_gaps
        assert "required" not in all_gaps


# ─── MatchExplanation ─────────────────────────────────────────────────────────

class TestMatchExplanation:
    def test_to_dict_has_all_keys(self):
        expl = MatchExplanation(
            total=Decimal("0.750"),
            breakdown={"skill": 0.8, "experience": 0.7},
            skill_gaps={"critical": [], "moderate": [], "low": []},
        )
        d = expl.to_dict()
        assert set(d.keys()) == {"total", "breakdown", "skill_gaps", "algorithm_version"}

    def test_algorithm_version_default(self):
        expl = MatchExplanation(
            total=Decimal("0.500"),
            breakdown={},
            skill_gaps={"critical": [], "moderate": [], "low": []},
        )
        assert expl.algorithm_version == MATCH_ALGORITHM_VERSION

    def test_total_serialized_as_string(self):
        expl = MatchExplanation(
            total=Decimal("0.847"),
            breakdown={},
            skill_gaps={"critical": [], "moderate": [], "low": []},
        )
        d = expl.to_dict()
        assert d["total"] == "0.847"
        assert isinstance(d["total"], str)

    def test_breakdown_and_gaps_passed_through(self):
        breakdown = {"skill": 0.9, "title": 0.7}
        gaps = {"critical": ["python"], "moderate": [], "low": []}
        expl = MatchExplanation(total=Decimal("0.800"), breakdown=breakdown, skill_gaps=gaps)
        d = expl.to_dict()
        assert d["breakdown"] == breakdown
        assert d["skill_gaps"] == gaps


# ─── _SOFT_SKILL_VOCAB sanity ────────────────────────────────────────────────

class TestSoftSkillVocab:
    def test_is_frozenset(self):
        assert isinstance(_SOFT_SKILL_VOCAB, frozenset)

    def test_has_approximately_40_terms(self):
        assert 35 <= len(_SOFT_SKILL_VOCAB) <= 45

    def test_leadership_in_vocab(self):
        assert "leadership" in _SOFT_SKILL_VOCAB

    def test_agile_in_vocab(self):
        assert "agile" in _SOFT_SKILL_VOCAB

    def test_scrum_in_vocab(self):
        assert "scrum" in _SOFT_SKILL_VOCAB

    def test_collaboration_in_vocab(self):
        assert "collaboration" in _SOFT_SKILL_VOCAB

    def test_communication_in_vocab(self):
        assert "communication" in _SOFT_SKILL_VOCAB

    def test_ownership_in_vocab(self):
        assert "ownership" in _SOFT_SKILL_VOCAB

    def test_no_tech_terms_in_soft_vocab(self):
        overlap = _SOFT_SKILL_VOCAB & _TECH_VOCAB
        assert overlap == frozenset(), f"Tech/soft overlap: {overlap}"

    def test_all_terms_single_tokens_no_spaces(self):
        for term in _SOFT_SKILL_VOCAB:
            assert " " not in term, f"Multi-word term found: {term!r}"


# ─── MATCH_WEIGHTS sanity ─────────────────────────────────────────────────────

class TestMatchWeights:
    def test_weights_sum_to_one(self):
        total = sum(MATCH_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_all_eight_dimensions_present(self):
        expected = {"skill", "experience", "keyword", "title", "education", "certification", "location", "salary"}
        assert set(MATCH_WEIGHTS.keys()) == expected

    def test_all_weights_positive(self):
        assert all(w > 0 for w in MATCH_WEIGHTS.values())


# ─── compute_resume_match_score ───────────────────────────────────────────────

def _full_profile(**overrides):
    base = dict(
        skills=[_skill("Python"), _skill("Django")],
        work_experiences=[_we(
            job_title="Python Developer",
            start_date=date(2020, 1, 1),
            end_date=date(2023, 1, 1),
            is_current=False,
            technologies=["Python", "Django"],
            description="Built REST APIs with Python and Django",
        )],
        educations=[_edu("B.Tech")],
        certifications=[],
        projects=[_proj(technologies=["Python"], description="Django REST project")],
        headline="Python Developer",
        professional_summary="Experienced Python developer with Django expertise",
        ats_keywords=["Python", "REST API"],
        target_role="Senior Python Developer",
        custom_section_texts=[],
        user_city="Bangalore",
        expected_salary_min=None,
        expected_salary_max=None,
    )
    base.update(overrides)
    return base


class TestComputeResumeMatchScore:
    def test_returns_match_explanation_instance(self):
        job = _job(title="Python Developer", description="Python Django REST API developer")
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert isinstance(result, MatchExplanation)

    def test_breakdown_has_all_8_dimensions(self):
        job = _job()
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert set(result.breakdown.keys()) == {
            "skill", "experience", "keyword", "title",
            "education", "certification", "location", "salary"
        }

    def test_total_in_valid_range(self):
        job = _job(title="Python Developer", description="Python Django experience needed")
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert Decimal("0.000") <= result.total <= Decimal("1.000")

    def test_total_is_3dp_decimal(self):
        job = _job()
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert result.total == result.total.quantize(Decimal("0.001"))

    def test_remote_job_location_score_is_1(self):
        job = _job(work_type="remote")
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert result.breakdown["location"] == 1.0

    def test_salary_neutral_when_both_missing(self):
        job = _job(salary_min=None, salary_max=None)
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert result.breakdown["salary"] == 0.5

    def test_skill_gaps_keys_always_present(self):
        job = _job(description="Python Django React AWS developer needed")
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert set(result.skill_gaps.keys()) == {"critical", "moderate", "soft", "low"}

    def test_today_injectable_no_error(self):
        job = _job()
        result = compute_resume_match_score(**_full_profile(), job=job, today=date(2025, 6, 15))
        assert result.total >= Decimal("0.000")

    def test_empty_profile_returns_lower_score_than_full(self):
        job = _job(
            title="Python Developer",
            description="Python Django REST expert needed, 3+ years experience",
        )
        full_result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        empty_result = compute_resume_match_score(
            skills=[],
            work_experiences=[],
            educations=[],
            certifications=[],
            projects=[],
            headline="",
            professional_summary="",
            ats_keywords=[],
            target_role="",
            custom_section_texts=[],
            user_city="",
            expected_salary_min=None,
            expected_salary_max=None,
            job=job,
            today=_TODAY,
        )
        assert full_result.total > empty_result.total

    def test_algorithm_version_is_v2(self):
        job = _job()
        result = compute_resume_match_score(**_full_profile(), job=job, today=_TODAY)
        assert result.algorithm_version == "v2"

    def test_current_we_title_in_title_score(self):
        profile = _full_profile(
            work_experiences=[_we(
                job_title="Python Developer",
                start_date=date(2022, 1, 1),
                end_date=None,
                is_current=True,
                technologies=["Python"],
                description="Python work",
            )]
        )
        job = _job(title="Python Developer")
        result = compute_resume_match_score(**profile, job=job, today=_TODAY)
        assert result.breakdown["title"] > 0.0

    def test_salary_overlap_reflected_in_breakdown(self):
        profile = _full_profile(
            expected_salary_min=Decimal("500000"),
            expected_salary_max=Decimal("800000"),
        )
        job = _job(salary_min=Decimal("600000"), salary_max=Decimal("900000"))
        result = compute_resume_match_score(**profile, job=job, today=_TODAY)
        assert result.breakdown["salary"] == 1.0
