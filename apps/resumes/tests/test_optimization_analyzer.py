"""
Unit tests for OptimizationAnalyzer and its dataclasses.

No DB access required — all functions are pure Python.
"""
import pytest

from apps.resumes.optimization_analyzer import (
    KeywordGap,
    OptimizationAnalyzer,
    OptimizationReport,
    SectionReport,
    Suggestion,
    SuggestionType,
)
from apps.resumes.services import ATSScorer


# ── Fixtures ───────────────────────────────────────────────────────────────────

MINIMAL_PROFILE = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "",
    "location": None,
    "headline": "",
    "professional_summary": "",
    "work_experiences": [],
    "educations": [],
    "skills": [],
    "projects": [],
    "certifications": [],
    "achievements": [],
    "publications": [],
}

FULL_PROFILE = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+1-555-000-0000",
    "location": {"city": "San Francisco"},
    "headline": "Senior Software Engineer",
    "professional_summary": (
        "Experienced software engineer with 6 years building Python/Django backends "
        "and cloud infrastructure. Delivered APIs serving 1M+ daily users."
    ),
    "work_experiences": [
        {
            "company_name": "Acme Corp",
            "job_title": "Senior Software Engineer",
            "is_current": True,
            "description": "Backend development",
            "achievements": [
                "Designed and built REST APIs serving 1M+ daily users using Python and Django.",
                "Reduced database query time by 40% through indexing and query optimization.",
                "Led team of 5 engineers to migrate monolith to microservices architecture.",
            ],
            "technologies": ["Python", "Django", "PostgreSQL", "AWS"],
        },
        {
            "company_name": "Beta Inc",
            "job_title": "Software Engineer",
            "is_current": False,
            "description": "Frontend and backend work",
            "achievements": [
                "Built React dashboard used by 200+ internal customers.",
                "Increased test coverage from 45% to 92% over 3 months.",
            ],
            "technologies": ["JavaScript", "React"],
        },
    ],
    "educations": [
        {
            "institution": "State University",
            "degree": "Bachelor of Science",
            "field_of_study": "Computer Science",
            "gpa": "3.8",
        }
    ],
    "skills": [
        {"name": "Python", "proficiency_level": "expert"},
        {"name": "Django", "proficiency_level": "expert"},
        {"name": "PostgreSQL", "proficiency_level": "advanced"},
        {"name": "AWS", "proficiency_level": "intermediate"},
        {"name": "Docker", "proficiency_level": "intermediate"},
        {"name": "React", "proficiency_level": "beginner"},
        {"name": "Redis", "proficiency_level": "intermediate"},
        {"name": "Git", "proficiency_level": "expert"},
    ],
    "projects": [
        {
            "title": "CLI Tool",
            "description": "Open source data processing CLI",
            "technologies": ["Python", "Click"],
            "highlights": ["5000 stars"],
        }
    ],
    "certifications": [
        {"name": "AWS Solutions Architect", "issuing_organization": "AWS"}
    ],
    "achievements": [],
    "publications": [],
}

MINIMAL_ATS = ATSScorer.score(MINIMAL_PROFILE, "")
FULL_ATS = ATSScorer.score(FULL_PROFILE, "")


# ── SuggestionType ─────────────────────────────────────────────────────────────

class TestSuggestionType:
    def test_constants_are_strings(self):
        assert isinstance(SuggestionType.STRENGTHEN_BULLET, str)
        assert isinstance(SuggestionType.EXPAND_SUMMARY, str)
        assert isinstance(SuggestionType.ADD_ACHIEVEMENTS, str)
        assert isinstance(SuggestionType.ADD_SKILLS, str)
        assert isinstance(SuggestionType.COMPLETE_CONTACT, str)
        assert isinstance(SuggestionType.ADD_SECTION, str)

    def test_constants_are_distinct(self):
        values = [
            SuggestionType.STRENGTHEN_BULLET,
            SuggestionType.EXPAND_SUMMARY,
            SuggestionType.ADD_ACHIEVEMENTS,
            SuggestionType.ADD_SKILLS,
            SuggestionType.COMPLETE_CONTACT,
            SuggestionType.ADD_SECTION,
        ]
        assert len(set(values)) == 6


# ── Suggestion ─────────────────────────────────────────────────────────────────

class TestSuggestion:
    def test_to_dict_all_fields(self):
        sug = Suggestion(
            id="abc",
            type=SuggestionType.ADD_SKILLS,
            priority=1,
            guidance="Add skills",
            target={"section": "skills"},
            original="",
            rewrite=None,
        )
        d = sug.to_dict()
        assert d["id"] == "abc"
        assert d["type"] == SuggestionType.ADD_SKILLS
        assert d["priority"] == 1
        assert d["guidance"] == "Add skills"
        assert d["target"] == {"section": "skills"}
        assert d["original"] == ""
        assert d["rewrite"] is None

    def test_to_dict_with_rewrite(self):
        sug = Suggestion(id="x", type=SuggestionType.STRENGTHEN_BULLET, priority=2,
                         guidance="g", target={}, original="old", rewrite="new")
        assert sug.to_dict()["rewrite"] == "new"
        assert sug.to_dict()["original"] == "old"


# ── KeywordGap ─────────────────────────────────────────────────────────────────

class TestKeywordGap:
    def test_to_dict(self):
        kg = KeywordGap(token="kubernetes", tier="critical", priority_score=0.82, suggested_section="skills")
        d = kg.to_dict()
        assert d == {"token": "kubernetes", "tier": "critical",
                     "priority_score": 0.82, "suggested_section": "skills"}


# ── SectionReport ──────────────────────────────────────────────────────────────

class TestSectionReport:
    def test_to_dict_no_suggestions(self):
        sr = SectionReport(name="skills", current_pts=10, max_pts=15, opportunity=5)
        d = sr.to_dict()
        assert d["name"] == "skills"
        assert d["current_pts"] == 10
        assert d["max_pts"] == 15
        assert d["opportunity"] == 5
        assert d["suggestions"] == []

    def test_to_dict_with_suggestions(self):
        sug = Suggestion(id="s1", type=SuggestionType.ADD_SKILLS, priority=1,
                         guidance="g", target={})
        sr = SectionReport(name="skills", current_pts=5, max_pts=15, opportunity=10,
                           suggestions=[sug])
        d = sr.to_dict()
        assert len(d["suggestions"]) == 1
        assert d["suggestions"][0]["id"] == "s1"


# ── OptimizationReport ─────────────────────────────────────────────────────────

class TestOptimizationReport:
    def _make_report(self):
        sug = Suggestion(id="s1", type=SuggestionType.ADD_SKILLS, priority=1,
                         guidance="g", target={"section": "skills"}, original="", rewrite=None)
        sr = SectionReport(name="skills", current_pts=5, max_pts=15, opportunity=10,
                           suggestions=[sug])
        kg = KeywordGap(token="python", tier="critical", priority_score=0.9, suggested_section="skills")
        return OptimizationReport(
            current_score=60,
            potential_score=85,
            sections=[sr],
            keyword_gaps=[kg],
            generated_at="2026-06-24T10:00:00",
            job_description_provided=True,
        )

    def test_to_dict_structure(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["current_score"] == 60
        assert d["potential_score"] == 85
        assert len(d["sections"]) == 1
        assert len(d["keyword_gaps"]) == 1
        assert d["generated_at"] == "2026-06-24T10:00:00"
        assert d["job_description_provided"] is True

    def test_from_dict_roundtrip(self):
        report = self._make_report()
        restored = OptimizationReport.from_dict(report.to_dict())
        assert restored.current_score == 60
        assert restored.potential_score == 85
        assert len(restored.sections) == 1
        assert restored.sections[0].name == "skills"
        assert len(restored.sections[0].suggestions) == 1
        assert restored.sections[0].suggestions[0].id == "s1"
        assert len(restored.keyword_gaps) == 1
        assert restored.keyword_gaps[0].token == "python"
        assert restored.job_description_provided is True

    def test_from_dict_empty_sections(self):
        d = {
            "current_score": 50,
            "potential_score": 80,
            "sections": [],
            "keyword_gaps": [],
            "generated_at": "ts",
            "job_description_provided": False,
        }
        r = OptimizationReport.from_dict(d)
        assert r.sections == []
        assert r.keyword_gaps == []

    def test_from_dict_missing_optional_keys(self):
        d = {
            "current_score": 50,
            "potential_score": 80,
            "sections": [],
            "keyword_gaps": [],
        }
        r = OptimizationReport.from_dict(d)
        assert r.generated_at == ""
        assert r.job_description_provided is False


# ── _bullet_impact_score ──────────────────────────────────────────────────────

class TestBulletImpactScore:
    def test_strong_bullet_full_score(self):
        bullet = "Reduced API latency by 40% by optimizing database queries and caching."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 1.0

    def test_empty_string_is_zero(self):
        assert OptimizationAnalyzer._bullet_impact_score("") == 0.0

    def test_whitespace_only_is_zero(self):
        assert OptimizationAnalyzer._bullet_impact_score("   ") == 0.0

    def test_action_verb_only(self):
        # verb only, no metric, but length < 40
        bullet = "Developed REST APIs"
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 0.35  # verb only, no metric, too short

    def test_metric_only_no_verb(self):
        bullet = "Responsible for reducing latency by 40% through caching and query tuning."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        # "Responsible" not in _ACTION_VERBS → no verb score
        # has 40% → metric score
        # length ok → length score
        assert score == pytest.approx(0.65, abs=0.01)

    def test_verb_and_metric_but_short(self):
        bullet = "Reduced latency by 40%."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == pytest.approx(0.70, abs=0.01)  # verb + metric, too short

    def test_percentage_quantification(self):
        bullet = "Increased revenue by 25% over the course of the fiscal year through optimization."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 1.0  # verb, metric (25%), length ok

    def test_dollar_quantification(self):
        bullet = "Generated $500k in new annual recurring revenue by closing enterprise deals."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 1.0

    def test_user_count_quantification(self):
        bullet = "Built a recommendation engine that serves 50000 users daily with sub-50ms latency."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 1.0

    def test_time_quantification(self):
        bullet = "Accelerated deployment pipeline from 45 minutes to under 8 minutes using Docker."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 1.0

    def test_multiplier_quantification(self):
        bullet = "Scaled search throughput 10x by migrating from relational to Elasticsearch backend."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == 1.0

    def test_too_long_over_200_chars(self):
        long_bullet = "Developed " + "a " * 100 + "system."
        score = OptimizationAnalyzer._bullet_impact_score(long_bullet)
        assert score == pytest.approx(0.35, abs=0.01)  # verb, no metric, too long

    def test_exactly_40_chars_is_adequate_length(self):
        # 40 chars, starts with action verb, has metric shorthand
        bullet = "Led 5 engineers rebuilding core platform."
        assert len(bullet.strip()) == 41
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_short_under_40_no_length_score(self):
        bullet = "Led 5k users onboarding"  # short, has verb, has metric
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        assert score == pytest.approx(0.70, abs=0.01)  # verb + metric, no length

    def test_passive_phrasing_no_verb_score(self):
        bullet = "Responsible for backend development serving 100k users daily in production env."
        score = OptimizationAnalyzer._bullet_impact_score(bullet)
        # "Responsible" not in _ACTION_VERBS → 0 verb
        # "100k" matches metric → 0.35
        # length ok → 0.30
        assert score == pytest.approx(0.65, abs=0.01)


# ── _keyword_suggested_section ────────────────────────────────────────────────

class TestKeywordSuggestedSection:
    def test_critical_maps_to_skills(self):
        assert OptimizationAnalyzer._keyword_suggested_section("kubernetes", "critical") == "skills"

    def test_soft_maps_to_summary(self):
        assert OptimizationAnalyzer._keyword_suggested_section("leadership", "soft") == "summary"

    def test_moderate_maps_to_experience(self):
        assert OptimizationAnalyzer._keyword_suggested_section("microservices", "moderate") == "experience"

    def test_low_maps_to_experience(self):
        assert OptimizationAnalyzer._keyword_suggested_section("workflow", "low") == "experience"


# ── _compute_potential ────────────────────────────────────────────────────────

class TestComputePotential:
    def test_full_profile_returns_same_or_higher(self):
        # All sections at max → no gain → potential == current
        breakdown = {"contact": 15, "summary": 10, "experience": 30,
                     "education": 20, "skills": 15, "additional": 10}
        result = OptimizationAnalyzer._compute_potential(100, breakdown)
        assert result == 100  # max(100, min(95, 100+0)) = max(100, 95) = 100

    def test_minimal_profile_computes_gain(self):
        breakdown = {"contact": 8, "summary": 0, "experience": 0,
                     "education": 0, "skills": 0, "additional": 0}
        result = OptimizationAnalyzer._compute_potential(8, breakdown)
        assert result > 8
        assert result <= 95

    def test_cap_at_95(self):
        # Force a very low score with high gain
        breakdown = {"contact": 0, "summary": 0, "experience": 0,
                     "education": 0, "skills": 0, "additional": 0}
        result = OptimizationAnalyzer._compute_potential(0, breakdown)
        assert result <= 95

    def test_education_does_not_contribute_to_gain(self):
        # education opportunity = 20, actionability = 0 → gain += 0
        breakdown_with_edu = {"contact": 15, "summary": 10, "experience": 30,
                              "education": 0, "skills": 15, "additional": 10}
        breakdown_without_edu = {"contact": 15, "summary": 10, "experience": 30,
                                 "education": 20, "skills": 15, "additional": 10}
        result_with = OptimizationAnalyzer._compute_potential(80, breakdown_with_edu)
        result_without = OptimizationAnalyzer._compute_potential(80, breakdown_without_edu)
        # Education opportunity does not contribute → same result
        assert result_with == result_without

    def test_potential_never_below_current(self):
        # Even if gain = 0, potential >= current
        breakdown = {"contact": 15, "summary": 10, "experience": 30,
                     "education": 20, "skills": 15, "additional": 10}
        result = OptimizationAnalyzer._compute_potential(72, breakdown)
        assert result >= 72


# ── _contact_suggestions ──────────────────────────────────────────────────────

class TestContactSuggestions:
    def _run(self, profile_data):
        from itertools import count
        return OptimizationAnalyzer._contact_suggestions(profile_data, 8, count(1))

    def test_complete_contact_returns_no_suggestions(self):
        profile = {**MINIMAL_PROFILE, "phone": "555-0000", "location": {"city": "SF"}}
        suggestions = OptimizationAnalyzer._contact_suggestions(profile, 15, iter(range(1, 100)))
        assert suggestions == []

    def test_full_pts_returns_no_suggestions(self):
        suggestions = OptimizationAnalyzer._contact_suggestions(MINIMAL_PROFILE, 15, iter(range(1, 100)))
        assert suggestions == []

    def test_missing_phone_generates_suggestion(self):
        profile = {**MINIMAL_PROFILE, "location": {"city": "SF"}}
        from itertools import count
        suggestions = OptimizationAnalyzer._contact_suggestions(profile, 8, count(1))
        assert len(suggestions) == 1
        assert suggestions[0].type == SuggestionType.COMPLETE_CONTACT
        assert "phone number" in suggestions[0].guidance
        assert "phone" in suggestions[0].target["missing_fields"]

    def test_missing_location_generates_suggestion(self):
        profile = {**MINIMAL_PROFILE, "phone": "555-0000"}
        from itertools import count
        suggestions = OptimizationAnalyzer._contact_suggestions(profile, 8, count(1))
        assert len(suggestions) == 1
        assert "location" in suggestions[0].target["missing_fields"]

    def test_missing_both_phone_and_location(self):
        from itertools import count
        suggestions = OptimizationAnalyzer._contact_suggestions(MINIMAL_PROFILE, 8, count(1))
        assert len(suggestions) == 1  # single suggestion mentioning both
        assert "phone number" in suggestions[0].guidance
        assert "location" in suggestions[0].guidance


# ── _summary_suggestions ──────────────────────────────────────────────────────

class TestSummarySuggestions:
    def test_long_summary_no_suggestions(self):
        from itertools import count
        profile = {**MINIMAL_PROFILE, "professional_summary": "x" * 100}
        suggestions = OptimizationAnalyzer._summary_suggestions(profile, 10, count(1))
        assert suggestions == []

    def test_full_pts_returns_no_suggestions(self):
        from itertools import count
        suggestions = OptimizationAnalyzer._summary_suggestions(MINIMAL_PROFILE, 10, count(1))
        assert suggestions == []

    def test_empty_summary_generates_write_suggestion(self):
        from itertools import count
        suggestions = OptimizationAnalyzer._summary_suggestions(MINIMAL_PROFILE, 0, count(1))
        assert len(suggestions) == 1
        assert suggestions[0].type == SuggestionType.EXPAND_SUMMARY
        assert "3-4 sentences" in suggestions[0].guidance
        assert suggestions[0].original == ""

    def test_short_summary_generates_expand_suggestion(self):
        from itertools import count
        profile = {**MINIMAL_PROFILE, "professional_summary": "I am a developer."}
        suggestions = OptimizationAnalyzer._summary_suggestions(profile, 5, count(1))
        assert len(suggestions) == 1
        assert "characters" in suggestions[0].guidance
        assert suggestions[0].original == "I am a developer."

    def test_exactly_100_chars_summary_at_full_pts(self):
        from itertools import count
        profile = {**MINIMAL_PROFILE, "professional_summary": "a" * 100}
        suggestions = OptimizationAnalyzer._summary_suggestions(profile, 10, count(1))
        assert suggestions == []


# ── _experience_suggestions ───────────────────────────────────────────────────

class TestExperienceSuggestions:
    def _run(self, profile_data, current_pts=20):
        from itertools import count
        return OptimizationAnalyzer._experience_suggestions(profile_data, current_pts, count(1))

    def test_no_experiences_returns_empty(self):
        assert self._run(MINIMAL_PROFILE) == []

    def test_experience_with_zero_bullets_suggests_add(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "Acme", "job_title": "Eng", "achievements": [], "technologies": []}
        ]}
        suggestions = self._run(profile)
        assert len(suggestions) == 1
        assert suggestions[0].type == SuggestionType.ADD_ACHIEVEMENTS
        assert "2" in suggestions[0].guidance  # need 2 bullets

    def test_experience_with_one_bullet_suggests_add_one_more(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "Acme", "job_title": "Eng",
             "achievements": ["Did something good."], "technologies": []}
        ]}
        suggestions = self._run(profile)
        assert len(suggestions) == 1
        assert suggestions[0].type == SuggestionType.ADD_ACHIEVEMENTS
        assert suggestions[0].original == "Did something good."

    def test_experience_with_two_strong_bullets_no_suggestions(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "Acme", "job_title": "Eng",
             "achievements": [
                 "Reduced database query time by 40% through indexing and optimization.",
                 "Led team of 5 engineers to deliver project 2 weeks ahead of schedule.",
             ],
             "technologies": []}
        ]}
        suggestions = self._run(profile)
        assert suggestions == []

    def test_experience_with_two_weak_bullets_suggests_strengthen(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "Acme", "job_title": "Eng",
             "achievements": ["Worked on stuff.", "Did backend."],
             "technologies": []}
        ]}
        suggestions = self._run(profile)
        assert len(suggestions) == 2
        for s in suggestions:
            assert s.type == SuggestionType.STRENGTHEN_BULLET

    def test_multiple_experiences_scanned(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "A", "job_title": "Eng", "achievements": [], "technologies": []},
            {"company_name": "B", "job_title": "Dev", "achievements": [], "technologies": []},
        ]}
        suggestions = self._run(profile)
        assert len(suggestions) == 2
        companies = {s.target["company"] for s in suggestions}
        assert "A" in companies and "B" in companies

    def test_suggestion_target_includes_experience_index(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "Acme", "job_title": "Eng", "achievements": [], "technologies": []}
        ]}
        suggestions = self._run(profile)
        assert suggestions[0].target["experience_index"] == 0

    def test_strengthen_bullet_target_includes_bullet_index(self):
        profile = {**MINIMAL_PROFILE, "work_experiences": [
            {"company_name": "X", "job_title": "Eng",
             "achievements": ["Did stuff.", "More stuff."],
             "technologies": []}
        ]}
        suggestions = self._run(profile)
        assert any(s.target.get("bullet_index") == 0 for s in suggestions)
        assert any(s.target.get("bullet_index") == 1 for s in suggestions)


# ── _skills_suggestions ───────────────────────────────────────────────────────

class TestSkillsSuggestions:
    def _run(self, skills, current_pts):
        from itertools import count
        profile = {**MINIMAL_PROFILE, "skills": skills}
        return OptimizationAnalyzer._skills_suggestions(profile, current_pts, count(1))

    def test_eight_or_more_skills_no_suggestions(self):
        skills = [{"name": f"Skill{i}", "proficiency_level": "expert"} for i in range(8)]
        assert self._run(skills, 15) == []

    def test_full_pts_no_suggestions(self):
        assert self._run([], 15) == []

    def test_zero_skills_generates_add_skills(self):
        suggestions = self._run([], 0)
        assert len(suggestions) == 1
        assert suggestions[0].type == SuggestionType.ADD_SKILLS
        assert "8" in suggestions[0].guidance

    def test_four_skills_generates_add_skills(self):
        skills = [{"name": f"S{i}", "proficiency_level": "expert"} for i in range(4)]
        suggestions = self._run(skills, 10)
        assert len(suggestions) == 1
        assert "4" in suggestions[0].guidance  # need 4 more

    def test_seven_skills_generates_singular_suggestion(self):
        skills = [{"name": f"S{i}", "proficiency_level": "expert"} for i in range(7)]
        suggestions = self._run(skills, 10)
        assert len(suggestions) == 1
        assert "1 more skill" in suggestions[0].guidance

    def test_target_includes_counts(self):
        skills = [{"name": "Python", "proficiency_level": "expert"}]
        suggestions = self._run(skills, 5)
        assert suggestions[0].target["current_count"] == 1
        assert suggestions[0].target["target_count"] == 8


# ── _additional_suggestions ───────────────────────────────────────────────────

class TestAdditionalSuggestions:
    def _run(self, certs, projects, current_pts):
        from itertools import count
        profile = {**MINIMAL_PROFILE, "certifications": certs, "projects": projects}
        return OptimizationAnalyzer._additional_suggestions(profile, current_pts, count(1))

    def test_both_sections_present_at_max(self):
        certs = [{"name": "AWS"}]
        projects = [{"title": "Tool", "technologies": []}]
        assert self._run(certs, projects, 10) == []

    def test_full_pts_no_suggestions(self):
        assert self._run([], [], 10) == []

    def test_no_certs_no_projects_two_suggestions(self):
        suggestions = self._run([], [], 0)
        types = {s.type for s in suggestions}
        assert types == {SuggestionType.ADD_SECTION}
        assert len(suggestions) == 2

    def test_has_certs_no_projects_one_suggestion(self):
        certs = [{"name": "AWS"}]
        suggestions = self._run(certs, [], 5)
        assert len(suggestions) == 1
        assert "projects" in suggestions[0].target["section"]

    def test_has_projects_no_certs_one_suggestion(self):
        projects = [{"title": "Tool", "technologies": []}]
        suggestions = self._run([], projects, 5)
        assert len(suggestions) == 1
        assert "certifications" in suggestions[0].target["section"]


# ── _analyze_keywords ─────────────────────────────────────────────────────────

class TestKeywordAnalysis:
    def test_empty_job_description_returns_empty(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS, "")
        assert report.keyword_gaps == []
        assert report.job_description_provided is False

    def test_critical_tier_tokens_appear(self):
        jd = "We need python kubernetes and docker experience."
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS, jd)
        tiers = {kg.tier for kg in report.keyword_gaps}
        assert "critical" in tiers

    def test_soft_tier_tokens_appear(self):
        jd = "Strong leadership mentoring teamwork required for this role position."
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS, jd)
        tiers = {kg.tier for kg in report.keyword_gaps}
        assert "soft" in tiers

    def test_keyword_gaps_sorted_by_priority(self):
        jd = (
            "python python python python python tensorflow tensorflow "
            "leadership mentoring kubernetes docker aws"
        )
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS, jd)
        if len(report.keyword_gaps) >= 2:
            for i in range(len(report.keyword_gaps) - 1):
                assert report.keyword_gaps[i].priority_score >= report.keyword_gaps[i + 1].priority_score

    def test_keyword_gaps_capped_at_15(self):
        # JD with many unique tokens to force many gaps
        words = " ".join(f"uniquetoken{i}" * 3 for i in range(30))
        # also add many critical tokens
        jd = "python tensorflow kubernetes docker redis mongodb elasticsearch " + words
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS, jd)
        assert len(report.keyword_gaps) <= 15

    def test_keyword_suggested_section_in_each_gap(self):
        jd = "python kubernetes leadership strong analytical skills required."
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS, jd)
        for kg in report.keyword_gaps:
            assert kg.suggested_section in ("skills", "summary", "experience")


# ── OptimizationAnalyzer.analyze (integration) ───────────────────────────────

class TestAnalyze:
    def test_minimal_profile_has_many_suggestions(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        all_suggestions = [s for sec in report.sections for s in sec.suggestions]
        assert len(all_suggestions) > 0

    def test_full_profile_has_no_structural_gaps(self):
        report = OptimizationAnalyzer.analyze(FULL_PROFILE, FULL_ATS)
        structural_types = {SuggestionType.COMPLETE_CONTACT, SuggestionType.EXPAND_SUMMARY,
                            SuggestionType.ADD_ACHIEVEMENTS, SuggestionType.ADD_SKILLS,
                            SuggestionType.ADD_SECTION}
        structural_suggestions = [
            s for sec in report.sections
            for s in sec.suggestions
            if s.type in structural_types
        ]
        assert structural_suggestions == []

    def test_sections_sorted_by_opportunity_descending(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        opportunities = [s.opportunity for s in report.sections]
        assert opportunities == sorted(opportunities, reverse=True)

    def test_report_has_five_sections(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        assert len(report.sections) == 5  # contact, summary, experience, skills, additional

    def test_potential_score_in_report(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        assert report.potential_score > report.current_score

    def test_generated_at_is_set(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        assert report.generated_at != ""
        assert "T" in report.generated_at  # ISO format contains 'T'

    def test_with_job_description_sets_flag(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS,
                                               job_description="Need python django experience.")
        assert report.job_description_provided is True

    def test_current_score_matches_ats(self):
        report = OptimizationAnalyzer.analyze(FULL_PROFILE, FULL_ATS)
        assert report.current_score == FULL_ATS["score"]

    def test_suggestion_ids_are_unique(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        ids = [s.id for sec in report.sections for s in sec.suggestions]
        assert len(ids) == len(set(ids))

    def test_suggestion_priorities_are_sequential(self):
        report = OptimizationAnalyzer.analyze(MINIMAL_PROFILE, MINIMAL_ATS)
        all_priorities = sorted(s.priority for sec in report.sections for s in sec.suggestions)
        assert all_priorities == list(range(1, len(all_priorities) + 1))
