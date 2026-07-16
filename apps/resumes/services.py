import logging
from django.db import transaction
from django.utils import timezone
from apps.resumes.models import Resume, ResumeVersion, ResumeStatus
from apps.profiles.models import UserProfile
from apps.profiles.profile_utils import ProfileSerializer  # ACA-003: canonical location
from apps.templates_engine.models import Template, TemplateType

logger = logging.getLogger(__name__)


class ATSScorer:
    """Rule-based ATS scorer. No external API required. Used as primary or AI fallback."""

    _CONTACT_FIELDS = ["full_name", "email", "phone", "location"]

    @classmethod
    def score(cls, profile_data: dict, job_description: str = "") -> dict:
        breakdown: dict[str, int] = {}

        # Contact — 15 pts
        filled = sum(1 for f in cls._CONTACT_FIELDS if profile_data.get(f))
        breakdown["contact"] = round(15 * filled / len(cls._CONTACT_FIELDS))

        # Summary — 10 pts
        summary = profile_data.get("professional_summary") or ""
        if len(summary) >= 100:
            breakdown["summary"] = 10
        elif len(summary) >= 30:
            breakdown["summary"] = 5
        else:
            breakdown["summary"] = 0

        # Experience — 30 pts
        exps = profile_data.get("work_experiences") or []
        exp_pts = 0
        if exps:
            exp_pts += 15
            if len(exps) >= 2:
                exp_pts += 5
            has_bullets = any(
                exp.get("achievements") and len(exp["achievements"]) >= 2 for exp in exps
            )
            if has_bullets:
                exp_pts += 10
        breakdown["experience"] = exp_pts

        # Education — 20 pts
        breakdown["education"] = 20 if profile_data.get("educations") else 0

        # Skills — 15 pts
        skill_count = len(profile_data.get("skills") or [])
        if skill_count >= 8:
            breakdown["skills"] = 15
        elif skill_count >= 4:
            breakdown["skills"] = 10
        elif skill_count > 0:
            breakdown["skills"] = 5
        else:
            breakdown["skills"] = 0

        # Additional sections — 10 pts
        has_certs = bool(profile_data.get("certifications"))
        has_projects = bool(profile_data.get("projects"))
        if has_certs and has_projects:
            breakdown["additional"] = 10
        elif has_certs or has_projects:
            breakdown["additional"] = 5
        else:
            breakdown["additional"] = 0

        total = min(sum(breakdown.values()), 100)

        # Keyword matching (best-effort, no NLP)
        present_keywords: list[str] = []
        missing_keywords: list[str] = []
        if job_description:
            jd_tokens = set(job_description.lower().split())
            skill_names = {s["name"].lower() for s in (profile_data.get("skills") or [])}
            exp_words: set[str] = set()
            for exp in exps:
                exp_words.update((exp.get("description") or "").lower().split())
            resume_tokens = skill_names | exp_words

            candidates = [w for w in jd_tokens if len(w) > 3 and w.isalpha()][:30]
            present_keywords = [k for k in candidates if k in resume_tokens]
            missing_keywords = [k for k in candidates if k not in resume_tokens][:10]

        return {
            "score": total,
            "breakdown": breakdown,
            "present_keywords": present_keywords,
            "missing_keywords": missing_keywords,
            "suggestions": cls._suggestions(breakdown, profile_data),
        }

    @staticmethod
    def _suggestions(breakdown: dict, profile_data: dict) -> list[str]:
        out: list[str] = []
        if breakdown.get("contact", 0) < 15:
            out.append("Complete all contact fields: name, email, phone, and location.")
        if breakdown.get("summary", 0) < 10:
            out.append("Write a professional summary of at least 2-3 sentences.")
        if breakdown.get("experience", 0) < 20:
            out.append("Add achievement bullet points (2+) to each work experience.")
        if breakdown.get("education", 0) == 0:
            out.append("Add your educational background.")
        if breakdown.get("skills", 0) < 15:
            out.append("Add at least 8 relevant skills.")
        if breakdown.get("additional", 0) < 10:
            out.append("Add certifications and projects to strengthen your profile.")
        return out


class ResumeService:

    # ── CRUD ──────────────────────────────────────────────────────────────────

    @staticmethod
    def list_for_user(user) -> list:
        return Resume.objects.filter(user=user).select_related("template").order_by("-updated_at")

    @staticmethod
    def get_for_user(resume_id: str, user) -> Resume:
        return Resume.objects.select_related("template", "profile").get(id=resume_id, user=user)

    @staticmethod
    @transaction.atomic
    def create(user, data: dict) -> Resume:
        profile = UserProfile.objects.get(user=user)
        template = None
        template_slug = data.pop("template_slug", None)
        if template_slug:
            try:
                template = Template.objects.get(slug=template_slug, type=TemplateType.RESUME)
            except Template.DoesNotExist:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"template_slug": f"Template '{template_slug}' not found."})

        resume = Resume.objects.create(
            user=user,
            profile=profile,
            template=template,
            **data,
        )
        ResumeService._save_version(resume, user, "Initial draft")
        return resume

    @staticmethod
    @transaction.atomic
    def update(resume: Resume, data: dict, user) -> Resume:
        template_slug = data.pop("template_slug", None)
        if template_slug is not None:
            if template_slug:
                try:
                    resume.template = Template.objects.get(slug=template_slug, type=TemplateType.RESUME)
                except Template.DoesNotExist:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({"template_slug": f"Template '{template_slug}' not found."})
            else:
                resume.template = None

        for field, value in data.items():
            setattr(resume, field, value)
        resume.save()
        ResumeService._save_version(resume, user, "Updated")
        return resume

    @staticmethod
    def delete(resume: Resume) -> None:
        resume.delete()

    @staticmethod
    @transaction.atomic
    def duplicate(resume: Resume, user) -> Resume:
        """Clone a resume with title "(Copy)". Creates initial version snapshot."""
        copy = Resume.objects.create(
            user=user,
            profile=resume.profile,
            title=f"{resume.title} (Copy)",
            template=resume.template,
            template_settings=dict(resume.template_settings),
            custom_sections=list(resume.custom_sections),
            target_role=resume.target_role,
            target_company=resume.target_company,
            status=ResumeStatus.DRAFT,
            is_primary=False,
        )
        ResumeService._save_version(copy, user, "Duplicated")
        return copy

    @staticmethod
    def set_primary(resume: Resume, user) -> Resume:
        Resume.objects.filter(user=user, is_primary=True).update(is_primary=False)
        resume.is_primary = True
        resume.save(update_fields=["is_primary", "updated_at"])
        return resume

    # ── Versioning ────────────────────────────────────────────────────────────

    @staticmethod
    def _save_version(resume: Resume, user, change_summary: str = "") -> ResumeVersion:
        """Snapshot current state and render HTML."""
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=resume.user)
        profile_data = ProfileSerializer.to_dict(profile)

        rendered_html = ""
        if resume.template:
            try:
                from apps.templates_engine.services import TemplateRenderer
                rendered_html = TemplateRenderer.render_resume(
                    resume.template, profile_data, resume.template_settings
                )
            except Exception:
                logger.warning("Failed to render resume HTML for versioning", exc_info=True)

        next_version = resume.current_version
        version = ResumeVersion.objects.create(
            resume=resume,
            version_number=next_version,
            snapshot=profile_data,
            change_summary=change_summary,
            rendered_html=rendered_html,
            created_by=user,
        )
        resume.current_version = next_version + 1
        resume.save(update_fields=["current_version"])
        return version

    @staticmethod
    def list_versions(resume: Resume) -> list:
        return resume.versions.order_by("-version_number")

    # ── Preview ───────────────────────────────────────────────────────────────

    @staticmethod
    def rebuild_preview(resume: Resume, template_slug: str | None = None) -> str:
        """
        Render HTML from the current profile state and return it.

        ACA-002 fix: version records are immutable audit snapshots. This method
        no longer writes to any ResumeVersion row. Callers that need to persist
        a fresh render should call ResumeService.create() or update() which
        each create a new version via _save_version().

        template_slug: when provided, overrides resume.template so callers can
        preview a pending template selection before saving it to the resume.
        """
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).select_related("user").get(user=resume.user)
        profile_data = ProfileSerializer.to_dict(profile)

        if template_slug:
            template = Template.objects.filter(
                slug=template_slug, type=TemplateType.RESUME, is_active=True
            ).first() or resume.template
        else:
            template = resume.template

        if not template:
            template = Template.objects.filter(type=TemplateType.RESUME, is_active=True).first()

        if not template:
            return "<p>No template selected.</p>"

        from apps.templates_engine.services import TemplateRenderer
        return TemplateRenderer.render_resume(template, profile_data, resume.template_settings)

    # ── ATS Scoring ───────────────────────────────────────────────────────────

    @staticmethod
    def analyze_ats(resume: Resume, job_description: str = "") -> dict:
        """ATS analysis: tries AI first, falls back to rule-based ATSScorer."""
        from apps.profiles.models import UserProfile

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
        ).get(user=resume.user)
        profile_data = ProfileSerializer.to_dict(profile)

        result: dict = {}
        try:
            from apps.ai_engine.services import AIService
            resume_text_parts: list[str] = []
            if profile_data.get("professional_summary"):
                resume_text_parts.append(profile_data["professional_summary"])
            for exp in profile_data.get("work_experiences", []):
                resume_text_parts.append(f"{exp['job_title']} at {exp['company_name']}")
                resume_text_parts.extend(exp.get("achievements", []))
            for skill in profile_data.get("skills", []):
                resume_text_parts.append(skill["name"])
            resume_text = "\n".join(resume_text_parts)

            ai = AIService(user=resume.user)
            result = ai.analyze_ats(resume_text, job_description)
            if not result.get("score"):
                raise ValueError("AI returned empty score")
        except Exception:
            logger.info("AI ATS unavailable; using rule-based ATSScorer", exc_info=True)
            result = ATSScorer.score(profile_data, job_description)

        resume.ats_score = result.get("score", 0)
        resume.ats_analysis = result
        resume.save(update_fields=["ats_score", "ats_analysis", "updated_at"])
        return result
