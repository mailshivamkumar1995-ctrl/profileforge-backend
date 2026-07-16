import logging
from django.db import transaction
from django.core.cache import cache
from apps.profiles.models import (
    UserProfile, WorkExperience, Education, Skill,
    Project, Certification, Achievement, Publication,
)

logger = logging.getLogger(__name__)

SECTION_MODEL_MAP = {
    "experience": WorkExperience,
    "education": Education,
    "skills": Skill,
    "projects": Project,
    "certifications": Certification,
    "achievements": Achievement,
    "publications": Publication,
}

PROFILE_CACHE_KEY = "profile:{user_id}"
PROFILE_CACHE_TTL = 900  # 15 minutes


class ProfileService:

    @staticmethod
    def get_basic_profile(user) -> UserProfile:
        from core.exceptions import NotFoundException
        try:
            return UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            raise NotFoundException("Profile not found.")

    @staticmethod
    def get_profile(user) -> UserProfile:
        from core.exceptions import NotFoundException
        try:
            return UserProfile.objects.select_related("user").prefetch_related(
                "work_experiences", "educations", "skills", "projects",
                "certifications", "achievements", "publications",
            ).get(user=user)
        except UserProfile.DoesNotExist:
            raise NotFoundException("Profile not found.")

    @staticmethod
    def update_profile(user, validated_data: dict) -> UserProfile:
        profile = UserProfile.objects.get(user=user)
        for field, value in validated_data.items():
            setattr(profile, field, value)
        profile.save()
        ProfileService._invalidate_cache(user)
        ProfileService._trigger_sync(user)
        return profile

    @staticmethod
    def reorder_section(user, section: str, item_ids: list) -> None:
        profile = UserProfile.objects.get(user=user)
        model = SECTION_MODEL_MAP[section]

        with transaction.atomic():
            for order, item_id in enumerate(item_ids):
                model.objects.filter(
                    id=item_id, profile=profile
                ).update(display_order=order)

        ProfileService._invalidate_cache(user)
        ProfileService._trigger_sync(user)

    @staticmethod
    def bulk_upsert_skills(user, skills_data: list) -> list:
        profile = ProfileService.get_basic_profile(user)
        created_skills = []
        with transaction.atomic():
            for skill_data in skills_data:
                skill, _ = Skill.objects.update_or_create(
                    profile=profile,
                    name=skill_data.get("name"),
                    defaults={
                        "category": skill_data.get("category", "other"),
                        "proficiency_level": skill_data.get("proficiency_level", "intermediate"),
                    },
                )
                created_skills.append(skill)
        ProfileService._invalidate_cache(user)
        ProfileService._trigger_sync(user)
        return created_skills

    @staticmethod
    def _invalidate_cache(user) -> None:
        key = PROFILE_CACHE_KEY.format(user_id=str(user.id))
        cache.delete(key)

    @staticmethod
    def _trigger_sync(user) -> None:
        """Emit domain events to trigger async rebuild of all generated artifacts."""
        from celery_app.tasks.resume_tasks import rebuild_resume_previews
        from celery_app.tasks.portfolio_tasks import rebuild_portfolio

        # Fire and forget — no need to wait for these
        try:
            rebuild_resume_previews.apply_async(args=[str(user.id)], queue="resume")
            rebuild_portfolio.apply_async(args=[str(user.id)], queue="portfolio")
        except Exception:
            logger.warning(
                "Failed to trigger post-profile-update sync tasks",
                extra={"user_id": str(user.id)},
                exc_info=True,
            )
