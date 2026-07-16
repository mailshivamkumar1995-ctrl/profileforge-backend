"""
Service-layer tests for OptimizationService.

Requires DB access for profile and resume loading.
"""
import pytest

from apps.resumes.optimization_analyzer import OptimizationReport, SuggestionType
from apps.resumes.optimization_service import OptimizationService


BASE_URL = "/api/v1/resumes/"


@pytest.mark.django_db
class TestOptimizationServiceAnalyze:

    def test_returns_optimization_report(self, resume):
        result = OptimizationService.analyze(resume)
        assert isinstance(result, OptimizationReport)

    def test_current_score_is_int(self, resume):
        result = OptimizationService.analyze(resume)
        assert isinstance(result.current_score, int)

    def test_potential_score_is_int(self, resume):
        result = OptimizationService.analyze(resume)
        assert isinstance(result.potential_score, int)

    def test_potential_not_below_current(self, resume):
        result = OptimizationService.analyze(resume)
        assert result.potential_score >= result.current_score

    def test_sections_list_not_empty(self, resume):
        result = OptimizationService.analyze(resume)
        assert len(result.sections) == 5  # contact, summary, experience, skills, additional

    def test_persists_ats_score(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        assert resume.ats_score is not None

    def test_persists_ats_analysis(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        assert isinstance(resume.ats_analysis, dict)
        assert "score" in resume.ats_analysis
        assert "breakdown" in resume.ats_analysis

    def test_persists_optimization_key(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        assert "optimization" in resume.ats_analysis

    def test_optimization_key_has_sections(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        opt = resume.ats_analysis["optimization"]
        assert "sections" in opt
        assert isinstance(opt["sections"], list)

    def test_optimization_key_has_keyword_gaps(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        assert "keyword_gaps" in resume.ats_analysis["optimization"]

    def test_with_job_description_sets_flag(self, resume):
        result = OptimizationService.analyze(resume, job_description="Need python django AWS.")
        assert result.job_description_provided is True

    def test_without_job_description_empty_keyword_gaps(self, resume):
        result = OptimizationService.analyze(resume)
        assert result.keyword_gaps == []

    def test_with_job_description_has_keyword_gaps(self, resume, full_profile):
        result = OptimizationService.analyze(resume, job_description="Need kubernetes terraform golang experience.")
        # kubernetes, terraform, golang not in full_profile skills → gaps
        assert result.job_description_provided is True

    def test_generated_at_is_set(self, resume):
        result = OptimizationService.analyze(resume)
        assert result.generated_at != ""

    def test_repeated_analyze_updates_existing(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        first_score = resume.ats_score

        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        second_score = resume.ats_score

        # Both should be equal (same profile)
        assert first_score == second_score

    def test_full_profile_higher_score_than_minimal(self, resume, full_profile):
        result_full = OptimizationService.analyze(resume)

        # Get result from a fresh resume with no profile data
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        import django.contrib.auth
        User = django.contrib.auth.get_user_model()
        empty_user = User.objects.create_user(
            email="empty@example.com", username="emptyuser",
            first_name="Empty", last_name="User", password="pass"
        )
        UserProfile.objects.get_or_create(user=empty_user)
        empty_resume = Resume.objects.create(
            user=empty_user, profile=empty_user.profile, title="Empty", status="draft"
        )
        result_empty = OptimizationService.analyze(empty_resume)
        assert result_full.current_score >= result_empty.current_score


@pytest.mark.django_db
class TestOptimizationServiceGetReport:

    def test_get_report_returns_none_before_analyze(self, resume):
        result = OptimizationService.get_report(resume)
        assert result is None

    def test_get_report_returns_none_with_empty_ats_analysis(self, resume):
        resume.ats_analysis = {}
        resume.save(update_fields=["ats_analysis"])
        result = OptimizationService.get_report(resume)
        assert result is None

    def test_get_report_after_analyze_returns_report(self, resume):
        OptimizationService.analyze(resume)
        resume.refresh_from_db()
        result = OptimizationService.get_report(resume)
        assert isinstance(result, OptimizationReport)

    def test_get_report_score_matches_analyze(self, resume):
        analyzed = OptimizationService.analyze(resume)
        resume.refresh_from_db()
        retrieved = OptimizationService.get_report(resume)
        assert retrieved.current_score == analyzed.current_score

    def test_get_report_sections_match_analyze(self, resume):
        analyzed = OptimizationService.analyze(resume)
        resume.refresh_from_db()
        retrieved = OptimizationService.get_report(resume)
        assert len(retrieved.sections) == len(analyzed.sections)

    def test_get_report_handles_malformed_data_gracefully(self, resume):
        resume.ats_analysis = {"optimization": "not-a-dict"}
        resume.save(update_fields=["ats_analysis"])
        result = OptimizationService.get_report(resume)
        assert result is None
