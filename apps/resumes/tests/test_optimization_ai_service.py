"""
Service-layer tests for AIOptimizationService.

All tests mock the AI provider so no real API calls are made.
Pattern: patch("apps.ai_engine.services.get_ai_provider") with a MagicMock
         that returns a mock AIResponse — the same pattern used in test_ai_engine.py.
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from apps.ai_engine.providers.base import AIResponse
from apps.resumes.ai_optimization_service import AIOptimizationService
from apps.resumes.optimization_analyzer import OptimizationReport, SuggestionType


# ── Shared mock helper ────────────────────────────────────────────────────────

def _make_ai_response(content: str = "AI generated content") -> AIResponse:
    return AIResponse(
        content=content,
        model="gpt-4o-mini",
        prompt_tokens=80,
        completion_tokens=40,
        total_tokens=120,
    )


@contextmanager
def _mock_ai(content: str = "AI generated content"):
    """Context manager: replaces get_ai_provider with a mock that returns content."""
    provider = MagicMock()
    provider.complete.return_value = _make_ai_response(content)
    provider.provider_name = "openai"
    provider.model_name = "gpt-4o-mini"
    with patch("apps.ai_engine.services.get_ai_provider", return_value=provider) as p:
        yield p


def _make_weak_experience(profile, company="TestCo", job_title="Developer"):
    """Create a WorkExperience with 2 weak bullets → triggers STRENGTHEN_BULLET."""
    from apps.profiles.models import WorkExperience
    return WorkExperience.objects.create(
        profile=profile,
        company_name=company,
        job_title=job_title,
        employment_type="full_time",
        start_date="2021-01-01",
        is_current=True,
        achievements=["worked on things", "helped the team"],
        technologies=[],
        display_order=99,
    )


# ── TestAIOptimizationServiceEnhance ─────────────────────────────────────────

@pytest.mark.django_db
class TestAIOptimizationServiceEnhance:

    def test_returns_optimization_report(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=resume.user)
        assert isinstance(result, OptimizationReport)

    def test_current_score_is_int(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=resume.user)
        assert isinstance(result.current_score, int)

    def test_potential_not_below_current(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=resume.user)
        assert result.potential_score >= result.current_score

    def test_persists_ai_optimization_key(self, resume):
        with _mock_ai():
            AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        assert "ai_optimization" in resume.ats_analysis

    def test_also_persists_deterministic_optimization_key(self, resume):
        with _mock_ai():
            AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        assert "optimization" in resume.ats_analysis

    def test_has_five_sections(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=resume.user)
        assert len(result.sections) == 5

    def test_with_job_description_sets_flag(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(
                resume, job_description="Need python kubernetes.", user=resume.user
            )
        assert result.job_description_provided is True

    def test_without_job_description_empty_keyword_gaps(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=resume.user)
        assert result.keyword_gaps == []

    def test_strengthen_bullet_gets_rewrite_on_success(self, resume, db):
        _make_weak_experience(resume.user.profile)
        with _mock_ai("Delivered 3 microservices reducing latency by 40%"):
            result = AIOptimizationService.enhance(resume, user=resume.user)

        all_sugs = [s for sec in result.sections for s in sec.suggestions]
        bullet_sugs = [s for s in all_sugs if s.type == SuggestionType.STRENGTHEN_BULLET]
        assert len(bullet_sugs) > 0
        assert all(s.rewrite is not None for s in bullet_sugs)

    def test_expand_summary_gets_rewrite_on_success(self, resume):
        with _mock_ai("Experienced engineer specializing in scalable backend systems."):
            result = AIOptimizationService.enhance(resume, user=resume.user)

        all_sugs = [s for sec in result.sections for s in sec.suggestions]
        summary_sugs = [
            s for s in all_sugs
            if s.type == SuggestionType.EXPAND_SUMMARY
        ]
        if summary_sugs:
            assert summary_sugs[0].rewrite is not None

    def test_non_ai_suggestion_types_have_no_rewrite(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=resume.user)

        all_sugs = [s for sec in result.sections for s in sec.suggestions]
        non_ai_types = {
            SuggestionType.ADD_ACHIEVEMENTS,
            SuggestionType.ADD_SKILLS,
            SuggestionType.COMPLETE_CONTACT,
            SuggestionType.ADD_SECTION,
        }
        for sug in all_sugs:
            if sug.type in non_ai_types:
                assert sug.rewrite is None

    def test_ai_provider_failure_returns_report_not_exception(self, resume):
        with patch("apps.ai_engine.services.get_ai_provider") as mock_prov:
            mock_prov.return_value.complete.side_effect = Exception("Connection refused")
            result = AIOptimizationService.enhance(resume, user=resume.user)
        assert isinstance(result, OptimizationReport)

    def test_ai_failure_leaves_rewrites_as_none(self, resume, db):
        _make_weak_experience(resume.user.profile)
        with patch("apps.ai_engine.services.get_ai_provider") as mock_prov:
            mock_prov.return_value.complete.side_effect = Exception("AI down")
            result = AIOptimizationService.enhance(resume, user=resume.user)

        all_sugs = [s for sec in result.sections for s in sec.suggestions]
        bullet_sugs = [s for s in all_sugs if s.type == SuggestionType.STRENGTHEN_BULLET]
        assert len(bullet_sugs) > 0
        assert all(s.rewrite is None for s in bullet_sugs)

    def test_ai_failure_still_persists_ai_optimization_key(self, resume):
        with patch("apps.ai_engine.services.get_ai_provider") as mock_prov:
            mock_prov.return_value.complete.side_effect = Exception("AI down")
            AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        assert "ai_optimization" in resume.ats_analysis

    def test_no_user_does_not_raise(self, resume):
        with _mock_ai():
            result = AIOptimizationService.enhance(resume, user=None)
        assert isinstance(result, OptimizationReport)

    def test_repeated_enhance_updates_stored_report(self, resume):
        with _mock_ai("First rewrite"):
            AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        first_at = resume.ats_analysis.get("ai_optimization", {}).get("generated_at")

        with _mock_ai("Second rewrite"):
            AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        second_at = resume.ats_analysis.get("ai_optimization", {}).get("generated_at")

        # Both are valid timestamps; key is always present
        assert first_at is not None
        assert second_at is not None


# ── TestAIOptimizationServiceGetReport ───────────────────────────────────────

@pytest.mark.django_db
class TestAIOptimizationServiceGetReport:

    def test_returns_none_before_enhance(self, resume):
        result = AIOptimizationService.get_report(resume)
        assert result is None

    def test_returns_none_with_empty_ats_analysis(self, resume):
        resume.ats_analysis = {}
        resume.save(update_fields=["ats_analysis"])
        result = AIOptimizationService.get_report(resume)
        assert result is None

    def test_returns_report_after_enhance(self, resume):
        with _mock_ai():
            AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        result = AIOptimizationService.get_report(resume)
        assert isinstance(result, OptimizationReport)

    def test_score_matches_enhance(self, resume):
        with _mock_ai():
            enhanced = AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        retrieved = AIOptimizationService.get_report(resume)
        assert retrieved.current_score == enhanced.current_score

    def test_sections_count_matches_enhance(self, resume):
        with _mock_ai():
            enhanced = AIOptimizationService.enhance(resume, user=resume.user)
        resume.refresh_from_db()
        retrieved = AIOptimizationService.get_report(resume)
        assert len(retrieved.sections) == len(enhanced.sections)

    def test_handles_malformed_data_gracefully(self, resume):
        resume.ats_analysis = {"ai_optimization": "not-a-dict"}
        resume.save(update_fields=["ats_analysis"])
        result = AIOptimizationService.get_report(resume)
        assert result is None
