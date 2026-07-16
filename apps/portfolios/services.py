import logging
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from apps.portfolios.models import Portfolio, PortfolioVersion, SECTION_DEFAULTS
from apps.profiles.models import UserProfile
from apps.templates_engine.models import Template, TemplateType

logger = logging.getLogger(__name__)


class SEOGenerator:
    """Generates SEO metadata from profile data. No external calls."""

    @staticmethod
    def generate(profile_data: dict, portfolio: Portfolio) -> dict:
        name = profile_data.get("full_name", "")
        headline = profile_data.get("headline", "")
        summary = profile_data.get("professional_summary", "")
        skills = [s["name"] for s in (profile_data.get("skills") or [])[:10]]

        title = portfolio.seo_title or (f"{name} — {headline}" if headline else name)
        description = portfolio.seo_description or (
            summary[:155] + "…" if len(summary) > 155 else summary
        ) or f"{name}'s professional portfolio"

        keywords = portfolio.seo_keywords or ", ".join(skills[:8])

        return {
            "title": title,
            "description": description,
            "keywords": keywords,
            "og_title": title,
            "og_description": description[:200],
            "og_image": portfolio.og_image_path or "",
            "canonical_url": portfolio.public_url,
            "twitter_card": "summary_large_image",
            "json_ld": SEOGenerator._json_ld(profile_data, title, description),
        }

    @staticmethod
    def _json_ld(profile_data: dict, title: str, description: str) -> dict:
        name = profile_data.get("full_name", "")
        email = profile_data.get("email", "")
        url = profile_data.get("website_url", "")
        return {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": name,
            "description": description,
            "email": email,
            "url": url,
            "jobTitle": profile_data.get("headline", ""),
            "sameAs": [
                v for v in [
                    profile_data.get("linkedin_url"),
                    profile_data.get("github_url"),
                    profile_data.get("twitter_url"),
                ] if v
            ],
        }


class PortfolioService:

    # ── CRUD ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_or_create_for_user(user) -> tuple[Portfolio, bool]:
        """Returns the user's portfolio (creating it if first-time)."""
        profile = UserProfile.objects.get(user=user)
        portfolio, created = Portfolio.objects.get_or_create(
            user=user,
            defaults={
                "profile": profile,
                "slug": PortfolioService._unique_slug(user.username),
                "section_settings": dict(SECTION_DEFAULTS),
            },
        )
        if created:
            PortfolioService._save_version(portfolio, user, "Initial portfolio")
        return portfolio, created

    @staticmethod
    def get_for_user(user) -> Portfolio:
        return Portfolio.objects.select_related("theme", "profile").get(user=user)

    @staticmethod
    def get_by_slug(slug: str) -> Portfolio:
        return Portfolio.objects.select_related("theme", "profile", "user").get(
            slug=slug, is_published=True, is_public=True
        )

    @staticmethod
    def get_by_username(username: str) -> Portfolio:
        return Portfolio.objects.select_related("theme", "profile", "user").get(
            user__username=username, is_published=True, is_public=True
        )

    @staticmethod
    @transaction.atomic
    def update(portfolio: Portfolio, data: dict, user) -> Portfolio:
        theme_slug = data.pop("theme_slug", None)
        if theme_slug is not None:
            portfolio.theme = PortfolioService._resolve_theme(theme_slug)

        for field, value in data.items():
            setattr(portfolio, field, value)
        portfolio.save()
        PortfolioService._save_version(portfolio, user, "Settings updated")
        return portfolio

    @staticmethod
    def delete(portfolio: Portfolio) -> None:
        portfolio.delete()

    # ── Publishing ────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def publish(portfolio: Portfolio, user) -> Portfolio:
        portfolio.publish()
        portfolio.last_generated_at = timezone.now()
        portfolio.save(update_fields=["last_generated_at"])
        PortfolioService._save_version(portfolio, user, "Published")
        return portfolio

    @staticmethod
    def unpublish(portfolio: Portfolio) -> Portfolio:
        portfolio.unpublish()
        return portfolio

    # ── Preview ───────────────────────────────────────────────────────────────

    @staticmethod
    def rebuild_preview(portfolio: Portfolio) -> str:
        from apps.profiles.profile_utils import ProfileSerializer
        from apps.portfolios.analytics import get_analytics_script
        from apps.templates_engine.services import TemplateRenderer

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=portfolio.user)
        profile_data = ProfileSerializer.to_dict(profile)
        seo_data = SEOGenerator.generate(profile_data, portfolio)
        section_settings = portfolio.get_section_settings()
        analytics_script = get_analytics_script(portfolio.analytics_provider, portfolio.analytics_id)

        if not portfolio.theme:
            theme = Template.objects.filter(type=TemplateType.PORTFOLIO, is_active=True).first()
        else:
            theme = portfolio.theme

        if not theme:
            return "<p>No portfolio theme selected.</p>"

        portfolio_data = {
            "slug": portfolio.slug,
            "seo": seo_data,
            "is_published": portfolio.is_published,
            "public_url": portfolio.public_url,
            "custom_domain": portfolio.custom_domain,
        }

        rendered = TemplateRenderer.render_portfolio(
            theme, profile_data, portfolio_data, section_settings,
            portfolio.theme_settings, analytics_script
        )

        portfolio.last_generated_at = timezone.now()
        portfolio.save(update_fields=["last_generated_at"])

        return rendered

    # ── Versioning ────────────────────────────────────────────────────────────

    @staticmethod
    def _save_version(portfolio: Portfolio, user, change_summary: str = "") -> PortfolioVersion:
        from apps.profiles.profile_utils import ProfileSerializer

        rendered_html = ""
        snapshot: dict = {}
        try:
            profile = UserProfile.objects.prefetch_related(
                "work_experiences", "educations", "skills",
                "projects", "certifications", "achievements", "publications",
            ).get(user=portfolio.user)
            snapshot = ProfileSerializer.to_dict(profile)
            rendered_html = PortfolioService.rebuild_preview(portfolio)
        except Exception:
            logger.warning("Failed to render portfolio for versioning", exc_info=True)

        next_version = portfolio.current_version
        version = PortfolioVersion.objects.create(
            portfolio=portfolio,
            version_number=next_version,
            snapshot=snapshot,
            theme_slug=portfolio.theme.slug if portfolio.theme else "",
            section_settings=dict(portfolio.section_settings or {}),
            rendered_html=rendered_html,
            change_summary=change_summary,
            created_by=user,
        )
        portfolio.current_version = next_version + 1
        portfolio.save(update_fields=["current_version"])
        return version

    @staticmethod
    def list_versions(portfolio: Portfolio) -> list:
        return portfolio.versions.order_by("-version_number")

    # ── Section Settings ──────────────────────────────────────────────────────

    @staticmethod
    def toggle_section(portfolio: Portfolio, section: str, enabled: bool, user) -> Portfolio:
        settings = dict(portfolio.section_settings or {})
        existing = settings.get(section, {})
        settings[section] = {**existing, "enabled": enabled}
        portfolio.section_settings = settings
        portfolio.save(update_fields=["section_settings", "updated_at"])
        PortfolioService._save_version(portfolio, user, f"Section '{section}' {'enabled' if enabled else 'disabled'}")
        return portfolio

    @staticmethod
    def reorder_sections(portfolio: Portfolio, order: list[str], user) -> Portfolio:
        settings = dict(portfolio.section_settings or {})
        for idx, section in enumerate(order):
            existing = settings.get(section, {})
            settings[section] = {**existing, "order": idx}
        portfolio.section_settings = settings
        portfolio.save(update_fields=["section_settings", "updated_at"])
        PortfolioService._save_version(portfolio, user, "Sections reordered")
        return portfolio

    # ── SEO ───────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_seo(portfolio: Portfolio) -> dict:
        from apps.profiles.profile_utils import ProfileSerializer
        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "skills",
        ).get(user=portfolio.user)
        profile_data = ProfileSerializer.to_dict(profile)
        return SEOGenerator.generate(profile_data, portfolio)

    @staticmethod
    def auto_fill_seo(portfolio: Portfolio, user) -> Portfolio:
        """Populate seo_title and seo_description from profile if blank."""
        seo = PortfolioService.generate_seo(portfolio)
        if not portfolio.seo_title:
            portfolio.seo_title = seo["title"]
        if not portfolio.seo_description:
            portfolio.seo_description = seo["description"]
        if not portfolio.seo_keywords:
            portfolio.seo_keywords = seo["keywords"]
        portfolio.save(update_fields=["seo_title", "seo_description", "seo_keywords", "updated_at"])
        PortfolioService._save_version(portfolio, user, "Auto-filled SEO metadata")
        return portfolio

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_theme(theme_slug: str | None) -> Template | None:
        if not theme_slug:
            return None
        try:
            return Template.objects.get(slug=theme_slug, type=TemplateType.PORTFOLIO)
        except Template.DoesNotExist:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"theme_slug": f"Theme '{theme_slug}' not found."})

    @staticmethod
    def _unique_slug(base: str) -> str:
        slug = slugify(base)[:80]
        candidate = slug
        counter = 1
        while Portfolio.objects.filter(slug=candidate).exists():
            candidate = f"{slug}-{counter}"
            counter += 1
        return candidate
