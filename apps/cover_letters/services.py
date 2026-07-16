import logging
import re
from django.db import transaction
from django.utils import timezone
from apps.cover_letters.models import CoverLetter, CoverLetterVersion, CoverLetterStatus
from apps.profiles.models import UserProfile
from apps.templates_engine.models import Template, TemplateType
from core.exceptions import AIProviderException

logger = logging.getLogger(__name__)


class CoverLetterService:
    MIN_AI_BODY_WORDS = 25
    INCOMPLETE_ENDING_WORDS = {
        "a", "an", "and", "as", "at", "because", "between", "for", "from", "in",
        "including", "into", "of", "on", "or", "particularly", "that", "the",
        "to", "with",
    }
    COMPLETE_ENDING_PUNCTUATION = (".", "!", "?")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    @staticmethod
    def list_for_user(user) -> list:
        return (
            CoverLetter.objects
            .filter(user=user)
            .select_related("template")
            .order_by("-updated_at")
        )

    @staticmethod
    def get_for_user(cover_letter_id: str, user) -> CoverLetter:
        return CoverLetter.objects.select_related("template", "profile", "resume").get(
            id=cover_letter_id, user=user
        )

    @staticmethod
    @transaction.atomic
    def create(user, data: dict) -> CoverLetter:
        profile = UserProfile.objects.get(user=user)
        template = CoverLetterService._resolve_template(data.pop("template_slug", None))
        resume = CoverLetterService._resolve_resume(data.pop("resume_id", None), user)

        cover_letter = CoverLetter.objects.create(
            user=user,
            profile=profile,
            template=template,
            resume=resume,
            **data,
        )
        CoverLetterService._save_version(cover_letter, user, "Initial draft")
        return cover_letter

    @staticmethod
    @transaction.atomic
    def update(cover_letter: CoverLetter, data: dict, user) -> CoverLetter:
        template_slug = data.pop("template_slug", None)
        resume_id = data.pop("resume_id", None)

        if template_slug is not None:
            cover_letter.template = CoverLetterService._resolve_template(template_slug)

        if resume_id is not None:
            cover_letter.resume = CoverLetterService._resolve_resume(resume_id, user)

        for field, value in data.items():
            setattr(cover_letter, field, value)
        cover_letter.save()
        CoverLetterService._save_version(cover_letter, user, "Updated")
        return cover_letter

    @staticmethod
    def delete(cover_letter: CoverLetter) -> None:
        cover_letter.delete()

    @staticmethod
    @transaction.atomic
    def duplicate(cover_letter: CoverLetter, user) -> CoverLetter:
        copy = CoverLetter.objects.create(
            user=user,
            profile=cover_letter.profile,
            resume=cover_letter.resume,
            title=f"{cover_letter.title} (Copy)",
            template=cover_letter.template,
            company_name=cover_letter.company_name,
            job_title=cover_letter.job_title,
            hiring_manager_name=cover_letter.hiring_manager_name,
            hiring_manager_title=cover_letter.hiring_manager_title,
            company_address=dict(cover_letter.company_address),
            tone=cover_letter.tone,
            body_content=cover_letter.body_content,
            job_description=cover_letter.job_description,
            ai_generated=cover_letter.ai_generated,
            status=CoverLetterStatus.DRAFT,
        )
        CoverLetterService._save_version(copy, user, "Duplicated")
        return copy

    @staticmethod
    def archive(cover_letter: CoverLetter) -> CoverLetter:
        cover_letter.status = CoverLetterStatus.ARCHIVED
        cover_letter.save(update_fields=["status", "updated_at"])
        return cover_letter

    # ── Versioning ────────────────────────────────────────────────────────────

    @staticmethod
    def _save_version(cover_letter: CoverLetter, user, change_summary: str = "") -> CoverLetterVersion:
        rendered_html = ""
        if cover_letter.template:
            try:
                from apps.profiles.models import UserProfile as UP
                profile = UP.objects.prefetch_related(
                    "work_experiences", "educations", "skills",
                    "projects", "certifications", "achievements", "publications",
                ).get(user=cover_letter.user)
                from apps.profiles.profile_utils import ProfileSerializer
                profile_data = ProfileSerializer.to_dict(profile)
                rendered_html = CoverLetterService._render_html(cover_letter, profile_data)
            except Exception:
                logger.warning("Failed to render cover letter HTML for versioning", exc_info=True)

        next_version = cover_letter.current_version
        version = CoverLetterVersion.objects.create(
            cover_letter=cover_letter,
            version_number=next_version,
            content_snapshot=cover_letter.body_content,
            rendered_html=rendered_html,
            change_summary=change_summary,
            created_by=user,
        )
        cover_letter.current_version = next_version + 1
        cover_letter.save(update_fields=["current_version"])
        return version

    @staticmethod
    def list_versions(cover_letter: CoverLetter) -> list:
        return cover_letter.versions.order_by("-version_number")

    # ── Preview ───────────────────────────────────────────────────────────────

    @staticmethod
    def rebuild_preview(cover_letter: CoverLetter) -> str:
        from apps.profiles.models import UserProfile as UP
        from apps.profiles.profile_utils import ProfileSerializer

        profile = UP.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=cover_letter.user)
        profile_data = ProfileSerializer.to_dict(profile)

        if not cover_letter.template:
            template = Template.objects.filter(
                type=TemplateType.COVER_LETTER, is_active=True
            ).first()
        else:
            template = cover_letter.template

        if not template:
            return "<p>No template selected.</p>"

        rendered = CoverLetterService._render_html_with_template(cover_letter, profile_data, template)

        return rendered

    @staticmethod
    def _render_html(cover_letter: CoverLetter, profile_data: dict) -> str:
        template = cover_letter.template
        if not template:
            return ""
        return CoverLetterService._render_html_with_template(cover_letter, profile_data, template)

    @staticmethod
    def _render_html_with_template(cover_letter: CoverLetter, profile_data: dict, template: Template) -> str:
        from apps.templates_engine.services import TemplateRenderer
        from django.utils import timezone as tz

        letter_data = {
            "title": cover_letter.title,
            "company_name": cover_letter.company_name,
            "job_title": cover_letter.job_title,
            "hiring_manager_name": cover_letter.hiring_manager_name,
            "hiring_manager_title": cover_letter.hiring_manager_title,
            "company_address": cover_letter.company_address,
            "tone": cover_letter.tone,
            "body_content": cover_letter.body_content,
            "date": tz.now().strftime("%B %d, %Y"),
        }
        return TemplateRenderer.render_cover_letter(template, profile_data, letter_data)

    # ── AI Generation ─────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def generate_from_profile(cover_letter: CoverLetter, user, tone: str = "", job_description: str = "") -> CoverLetter:
        from apps.profiles.models import UserProfile as UP
        from apps.profiles.profile_utils import ProfileSerializer
        from apps.ai_engine.services import AIService

        profile = UP.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements",
        ).get(user=user)
        profile_data = ProfileSerializer.to_dict(profile)

        effective_tone = tone or cover_letter.tone
        effective_jd = job_description or cover_letter.job_description

        ai = AIService(user=user)
        body = ai.generate_cover_letter(
            profile_data=profile_data,
            company_name=cover_letter.company_name,
            job_title=cover_letter.job_title,
            job_description=effective_jd,
            tone=effective_tone,
        )
        body = CoverLetterService._validate_ai_body(body, source_body=cover_letter.body_content)

        cover_letter.body_content = body
        cover_letter.tone = effective_tone
        if job_description:
            cover_letter.job_description = job_description
        cover_letter.ai_generated = True
        cover_letter.save(update_fields=["body_content", "tone", "job_description", "ai_generated", "updated_at"])
        CoverLetterService._save_version(cover_letter, user, "AI generated")
        return cover_letter

    @staticmethod
    @transaction.atomic
    def rewrite(cover_letter: CoverLetter, user, instruction: str = "") -> CoverLetter:
        from apps.ai_engine.services import AIService

        ai = AIService(user=user)
        body = ai.rewrite_cover_letter(
            body_content=cover_letter.body_content,
            company_name=cover_letter.company_name,
            job_title=cover_letter.job_title,
            tone=cover_letter.tone,
            instruction=instruction,
        )
        body = CoverLetterService._validate_ai_body(body, source_body=cover_letter.body_content)

        cover_letter.body_content = body
        cover_letter.ai_generated = True
        cover_letter.save(update_fields=["body_content", "ai_generated", "updated_at"])
        CoverLetterService._save_version(cover_letter, user, "AI rewritten")
        return cover_letter

    @staticmethod
    @transaction.atomic
    def improve_tone(cover_letter: CoverLetter, user, tone: str) -> CoverLetter:
        from apps.ai_engine.services import AIService

        ai = AIService(user=user)
        body = ai.improve_cover_letter_tone(
            body_content=cover_letter.body_content,
            target_tone=tone,
        )
        body = CoverLetterService._validate_ai_body(body, source_body=cover_letter.body_content)

        cover_letter.body_content = body
        cover_letter.tone = tone
        cover_letter.ai_generated = True
        cover_letter.save(update_fields=["body_content", "tone", "ai_generated", "updated_at"])
        CoverLetterService._save_version(cover_letter, user, f"Tone adjusted to {tone}")
        return cover_letter

    @staticmethod
    @transaction.atomic
    def improve_ats(cover_letter: CoverLetter, user) -> CoverLetter:
        from apps.ai_engine.services import AIService

        ai = AIService(user=user)
        try:
            body = ai.improve_cover_letter_ats(
                body_content=cover_letter.body_content,
                job_description=cover_letter.job_description,
                job_title=cover_letter.job_title,
            )
            body = CoverLetterService._validate_ai_body(
                body, source_body=cover_letter.body_content
            )
        except AIProviderException:
            logger.warning("AI ATS improvement returned invalid content; using fallback", exc_info=True)
            body = CoverLetterService._build_ats_fallback_body(
                body_content=cover_letter.body_content,
                job_description=cover_letter.job_description,
                job_title=cover_letter.job_title,
            )
            body = CoverLetterService._validate_ai_body(
                body, source_body=cover_letter.body_content
            )

        cover_letter.body_content = body
        cover_letter.ai_generated = True
        cover_letter.save(update_fields=["body_content", "ai_generated", "updated_at"])
        CoverLetterService._save_version(cover_letter, user, "ATS alignment improved")
        return cover_letter

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_template(template_slug: str | None) -> Template | None:
        if not template_slug:
            return None
        try:
            return Template.objects.get(slug=template_slug, type=TemplateType.COVER_LETTER)
        except Template.DoesNotExist:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"template_slug": f"Template '{template_slug}' not found."})

    @staticmethod
    def _resolve_resume(resume_id, user) -> object | None:
        if not resume_id:
            return None
        from apps.resumes.models import Resume
        try:
            return Resume.objects.get(id=resume_id, user=user)
        except Resume.DoesNotExist:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"resume_id": "Resume not found."})

    @staticmethod
    def _validate_ai_body(body: str, source_body: str = "") -> str:
        cleaned = CoverLetterService._clean_ai_body(body)
        words = re.findall(r"\b[\w'-]+\b", cleaned)

        if len(words) < CoverLetterService.MIN_AI_BODY_WORDS:
            raise AIProviderException(
                "AI returned an incomplete cover letter. Please retry.",
                details={"reason": "too_short"},
            )

        if cleaned.startswith(("...", "\u2026")):
            raise AIProviderException(
                "AI returned an incomplete cover letter. Please retry.",
                details={"reason": "leading_ellipsis"},
            )

        if not cleaned.endswith(CoverLetterService.COMPLETE_ENDING_PUNCTUATION):
            raise AIProviderException(
                "AI returned an incomplete cover letter. Please retry.",
                details={"reason": "missing_terminal_punctuation"},
            )

        last_word = words[-1].lower().strip("'-.") if words else ""
        if last_word in CoverLetterService.INCOMPLETE_ENDING_WORDS:
            raise AIProviderException(
                "AI returned an incomplete cover letter. Please retry.",
                details={"reason": "unfinished_sentence"},
            )

        if source_body:
            source_words = re.findall(r"\b[\w'-]+\b", source_body)
            if len(source_words) >= 50 and len(words) < max(25, int(len(source_words) * 0.3)):
                raise AIProviderException(
                    "AI returned an incomplete cover letter. Please retry.",
                    details={"reason": "unexpectedly_short"},
                )

        return cleaned

    @staticmethod
    def _clean_ai_body(body: str) -> str:
        cleaned = (body or "").strip()
        cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", cleaned)
        cleaned = re.sub(r"(?m)^\s*[-*+]\s+", "", cleaned)
        cleaned = re.sub(r"(?m)^\s*\d+\.\s+", "", cleaned)
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
        cleaned = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", r"\1", cleaned)
        cleaned = re.sub(r"(?<!_)_(?!_)(.*?)_(?!_)", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _build_ats_fallback_body(
        body_content: str, job_description: str = "", job_title: str = ""
    ) -> str:
        base_body = CoverLetterService._clean_ai_body(body_content)
        keywords = CoverLetterService._extract_ats_keywords(
            job_description=job_description,
            job_title=job_title,
            existing_body=base_body,
        )

        if not base_body:
            role = job_title or "this role"
            base_body = (
                f"I am excited to apply for {role} because my experience aligns with "
                "the team's reliability, automation, and operational goals."
            )

        if keywords:
            keyword_text = CoverLetterService._join_keywords(keywords)
            return (
                f"{base_body}\n\n"
                f"This background also supports the role's emphasis on {keyword_text}, "
                "with practical experience applying these capabilities in reliable "
                "delivery environments."
            )

        return (
            f"{base_body}\n\n"
            "These strengths support reliable delivery, production discipline, "
            "observability, automation, and measurable engineering quality."
        )

    @staticmethod
    def _extract_ats_keywords(
        job_description: str = "", job_title: str = "", existing_body: str = ""
    ) -> list[str]:
        catalog = [
            "Kubernetes", "Docker", "CI/CD", "monitoring", "cloud infrastructure",
            "automation", "observability", "DevOps", "GCP", "AWS", "Azure",
            "Terraform", "Helm", "Prometheus", "Grafana", "robust infrastructure",
            "seamless development", "efficient operations", "reliability",
        ]
        haystack = f"{job_description} {job_title}".lower()
        existing = existing_body.lower()
        keywords = []
        for keyword in catalog:
            key = keyword.lower()
            if key in haystack and key not in existing:
                keywords.append(keyword)
        return keywords[:6]

    @staticmethod
    def _join_keywords(keywords: list[str]) -> str:
        if len(keywords) == 1:
            return keywords[0]
        if len(keywords) == 2:
            return f"{keywords[0]} and {keywords[1]}"
        return f"{', '.join(keywords[:-1])}, and {keywords[-1]}"
