"""
Resume optimization service layer.

Orchestrates profile loading, ATS scoring, and optimization analysis.
Persists the result to Resume.ats_analysis so GET /optimization/ can
return the last report without re-running the analysis.
"""
from __future__ import annotations

import logging

from apps.resumes.models import Resume
from apps.resumes.optimization_analyzer import OptimizationAnalyzer, OptimizationReport
from apps.resumes.services import ATSScorer

logger = logging.getLogger(__name__)


class OptimizationService:

    @staticmethod
    def analyze(resume: Resume, job_description: str = "") -> OptimizationReport:
        from apps.profiles.models import UserProfile
        from apps.profiles.profile_utils import ProfileSerializer

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=resume.user)
        profile_data = ProfileSerializer.to_dict(profile)

        ats_result = ATSScorer.score(profile_data, job_description)
        report = OptimizationAnalyzer.analyze(profile_data, ats_result, job_description)

        resume.ats_score = ats_result["score"]
        resume.ats_analysis = {
            "score": ats_result["score"],
            "breakdown": ats_result["breakdown"],
            "present_keywords": ats_result["present_keywords"],
            "missing_keywords": ats_result["missing_keywords"],
            "suggestions": ats_result["suggestions"],
            "optimization": report.to_dict(),
        }
        resume.save(update_fields=["ats_score", "ats_analysis", "updated_at"])

        return report

    @staticmethod
    def get_report(resume: Resume) -> OptimizationReport | None:
        optimization = (resume.ats_analysis or {}).get("optimization")
        if not optimization:
            return None
        try:
            return OptimizationReport.from_dict(optimization)
        except (KeyError, TypeError):
            logger.warning("Malformed optimization data in resume %s", resume.pk)
            return None
