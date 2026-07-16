"""
AI-powered resume optimization service layer.

Runs the deterministic P8-1A optimizer first, then calls AIService to populate
`rewrite` fields on STRENGTHEN_BULLET and EXPAND_SUMMARY suggestions.

Fallback contract:
  - If the AI provider is unavailable, each suggestion retains rewrite=None.
  - The endpoint always returns 200; AI failures are logged and absorbed here.
  - Persists the AI-enhanced report to Resume.ats_analysis["ai_optimization"]
    so GET /ai-optimization/ can return the last result without re-running.
"""
from __future__ import annotations

import logging

from apps.resumes.models import Resume
from apps.resumes.optimization_analyzer import (
    OptimizationReport, SectionReport, Suggestion, SuggestionType,
)

logger = logging.getLogger(__name__)


class AIOptimizationService:

    @staticmethod
    def enhance(resume: Resume, job_description: str = "", user=None) -> OptimizationReport:
        """
        1. Run deterministic optimization (persists to ats_analysis["optimization"]).
        2. AI-enhance STRENGTHEN_BULLET and EXPAND_SUMMARY suggestions.
        3. Persist AI-enhanced report to ats_analysis["ai_optimization"].
        4. Return the AI-enhanced OptimizationReport.

        Individual AI call failures are caught per-suggestion; the report is
        returned regardless of AI availability.
        """
        from apps.profiles.models import UserProfile
        from apps.profiles.profile_utils import ProfileSerializer
        from apps.resumes.optimization_service import OptimizationService
        from apps.ai_engine.services import AIService

        base_report = OptimizationService.analyze(resume, job_description)
        resume.refresh_from_db()

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "skills",
        ).get(user=resume.user)
        profile_data = ProfileSerializer.to_dict(profile)

        ai = AIService(user=user)
        enhanced_sections = [
            AIOptimizationService._enhance_section(ai, section, profile_data, resume)
            for section in base_report.sections
        ]

        enhanced_report = OptimizationReport(
            current_score=base_report.current_score,
            potential_score=base_report.potential_score,
            sections=enhanced_sections,
            keyword_gaps=base_report.keyword_gaps,
            generated_at=base_report.generated_at,
            job_description_provided=base_report.job_description_provided,
        )

        ats_analysis = dict(resume.ats_analysis or {})
        ats_analysis["ai_optimization"] = enhanced_report.to_dict()
        resume.ats_analysis = ats_analysis
        resume.save(update_fields=["ats_analysis", "updated_at"])

        return enhanced_report

    @staticmethod
    def get_report(resume: Resume) -> OptimizationReport | None:
        ai_optimization = (resume.ats_analysis or {}).get("ai_optimization")
        if not ai_optimization:
            return None
        try:
            return OptimizationReport.from_dict(ai_optimization)
        except (KeyError, TypeError):
            logger.warning("Malformed AI optimization data in resume %s", resume.pk)
            return None

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _enhance_section(ai, section: SectionReport, profile_data: dict, resume: Resume) -> SectionReport:
        return SectionReport(
            name=section.name,
            current_pts=section.current_pts,
            max_pts=section.max_pts,
            opportunity=section.opportunity,
            suggestions=[
                AIOptimizationService._enhance_suggestion(ai, sug, profile_data, resume)
                for sug in section.suggestions
            ],
        )

    @staticmethod
    def _enhance_suggestion(
        ai, suggestion: Suggestion, profile_data: dict, resume: Resume
    ) -> Suggestion:
        if suggestion.type == SuggestionType.STRENGTHEN_BULLET and suggestion.original:
            return AIOptimizationService._rewrite_bullet(ai, suggestion, profile_data)
        if suggestion.type == SuggestionType.EXPAND_SUMMARY:
            return AIOptimizationService._rewrite_summary(ai, suggestion, profile_data, resume)
        return suggestion

    @staticmethod
    def _rewrite_bullet(ai, suggestion: Suggestion, profile_data: dict) -> Suggestion:
        target = suggestion.target
        exp_index = target.get("experience_index", 0)
        exps = profile_data.get("work_experiences") or []
        context: dict = {}
        if exp_index < len(exps):
            exp = exps[exp_index]
            context = {
                "role": exp.get("job_title", ""),
                "company": exp.get("company_name", ""),
            }
        try:
            rewrite = ai.rewrite_resume_bullet(suggestion.original, context)
            return Suggestion(
                id=suggestion.id,
                type=suggestion.type,
                priority=suggestion.priority,
                guidance=suggestion.guidance,
                target=suggestion.target,
                original=suggestion.original,
                rewrite=rewrite,
            )
        except Exception:
            logger.warning(
                "AI bullet rewrite failed for suggestion %s", suggestion.id, exc_info=True
            )
            return suggestion

    @staticmethod
    def _rewrite_summary(
        ai, suggestion: Suggestion, profile_data: dict, resume: Resume
    ) -> Suggestion:
        try:
            rewrite = ai.optimize_resume_summary(
                current_summary=suggestion.original,
                profile_data=profile_data,
                target_role=resume.target_role or "",
            )
            return Suggestion(
                id=suggestion.id,
                type=suggestion.type,
                priority=suggestion.priority,
                guidance=suggestion.guidance,
                target=suggestion.target,
                original=suggestion.original,
                rewrite=rewrite,
            )
        except Exception:
            logger.warning("AI summary optimization failed", exc_info=True)
            return suggestion
