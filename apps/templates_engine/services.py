import logging
import os
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
from apps.templates_engine.models import Template, TemplateType

logger = logging.getLogger(__name__)

_TEMPLATE_DIRS = {
    TemplateType.RESUME: Path(__file__).parent / "resume_templates",
    TemplateType.COVER_LETTER: Path(__file__).parent / "cover_letter_templates",
    TemplateType.PORTFOLIO: Path(__file__).parent / "portfolio_themes",
}


def _split_bullets(text: str) -> list[str]:
    """Split a description into bullet lines.

    Uses explicit newlines when present; falls back to sentence splitting on
    '. ' boundaries so single-block paragraphs become readable bullet lists.
    """
    if not text:
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) > 1:
        return lines
    parts = re.split(r'(?<=\.)\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _get_jinja_env(template_type: str) -> Environment:
    template_dir = _TEMPLATE_DIRS.get(template_type)
    if template_dir is None:
        raise ValueError(f"Unknown template type: {template_type}")
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["split_bullets"] = _split_bullets
    return env


class TemplateRenderer:
    """Renders a Template record against profile data to produce HTML.

    Pure function per critical invariant: no side effects, no DB writes.
    """

    @staticmethod
    def render_resume(template: Template, profile_data: dict, settings: dict | None = None) -> str:
        env = _get_jinja_env(TemplateType.RESUME)
        template_file = f"{template.slug}.html"
        try:
            tmpl = env.get_template(template_file)
        except TemplateNotFound:
            logger.warning("Template file not found, falling back to default: %s", template_file)
            tmpl = env.get_template("classic.html")

        ctx = {
            "profile": profile_data,
            "settings": settings or {},
            "template": {
                "name": template.name,
                "category": template.category,
                "is_ats_optimized": template.is_ats_optimized,
            },
        }
        return tmpl.render(**ctx)

    @staticmethod
    def render_cover_letter(
        template: Template, profile_data: dict, letter_data: dict, settings: dict | None = None
    ) -> str:
        env = _get_jinja_env(TemplateType.COVER_LETTER)
        template_file = f"{template.slug}.html"
        try:
            tmpl = env.get_template(template_file)
        except TemplateNotFound:
            tmpl = env.get_template("professional_letter.html")

        ctx = {
            "profile": profile_data,
            "letter": letter_data,
            "settings": settings or {},
        }
        return tmpl.render(**ctx)

    @staticmethod
    def render_portfolio(
        template: Template,
        profile_data: dict,
        portfolio_data: dict,
        section_settings: dict,
        settings: dict | None = None,
        analytics_script: str = "",
    ) -> str:
        env = _get_jinja_env(TemplateType.PORTFOLIO)
        template_file = f"{template.slug}.html"
        try:
            tmpl = env.get_template(template_file)
        except TemplateNotFound:
            logger.warning("Portfolio theme not found, falling back: %s", template_file)
            tmpl = env.get_template("professional.html")

        ordered_section_keys = sorted(
            section_settings.keys(),
            key=lambda k: section_settings[k].get("order", 99)
        )

        ctx = {
            "profile": profile_data,
            "portfolio": portfolio_data,
            "sections": section_settings,
            "ordered_sections": ordered_section_keys,
            "settings": settings or {},
            "analytics_script": analytics_script,
        }
        return tmpl.render(**ctx)


class TemplateService:
    @staticmethod
    def list_active(template_type: str | None = None):
        qs = Template.objects.filter(is_active=True)
        if template_type:
            qs = qs.filter(type=template_type)
        return qs.order_by("category", "name")

    @staticmethod
    def get_by_slug(slug: str) -> Template:
        return Template.objects.get(slug=slug, is_active=True)
