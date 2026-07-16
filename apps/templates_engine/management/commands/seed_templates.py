"""
Management command to seed the templates table with all built-in templates.
Run once after initial migration: python manage.py seed_templates
Idempotent — safe to re-run.
"""
from django.core.management.base import BaseCommand
from apps.templates_engine.models import Template, TemplateType, TemplateCategory

RESUME_TEMPLATES = [
    {
        "slug": "classic",
        "name": "Classic",
        "category": TemplateCategory.PROFESSIONAL,
        "is_ats_optimized": False,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/professional.png",
        "description": "Clean two-column professional layout. Great for most industries.",
    },
    {
        "slug": "ats_clean_resume",
        "name": "ATS Clean",
        "category": TemplateCategory.ATS,
        "is_ats_optimized": True,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/ats.png",
        "description": "Single-column ATS-optimised layout. Maximises parser compatibility.",
    },
    {
        "slug": "modern_tech",
        "name": "Modern Tech",
        "category": TemplateCategory.TECHNICAL,
        "is_ats_optimized": True,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/technical.png",
        "description": "Bold, tech-focused layout highlighting technical skills, GitHub repositories, and major projects. Best for DevOps & SWE.",
    },
    {
        "slug": "creative_minimal",
        "name": "Creative Minimalist",
        "category": TemplateCategory.MINIMAL,
        "is_ats_optimized": False,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/minimal.png",
        "description": "Elegant serif typography with subtle colour accents. Ideal for modern startups and design-forward roles.",
    },
    {
        "slug": "executive_pro",
        "name": "Executive Pro",
        "category": TemplateCategory.EXECUTIVE,
        "is_ats_optimized": True,
        "is_single_page": False,
        "is_premium": True,
        "thumbnail_path": "/templates/executive.png",
        "description": "High-density, highly professional layout tailored for senior engineering leadership and C-suite executives.",
    },
]

COVER_LETTER_TEMPLATES = [
    {
        "slug": "professional_letter",
        "name": "Professional Letter",
        "category": TemplateCategory.PROFESSIONAL,
        "is_ats_optimized": False,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/professional.png",
        "description": "Classic business letter format. Works for all industries.",
    },
    {
        "slug": "executive_letter",
        "name": "Executive Letter",
        "category": TemplateCategory.EXECUTIVE,
        "is_ats_optimized": False,
        "is_single_page": True,
        "is_premium": True,
        "thumbnail_path": "/templates/executive.png",
        "description": "Authoritative layout with serif typography for senior leadership roles.",
    },
    {
        "slug": "technical_letter",
        "name": "Technical Letter",
        "category": TemplateCategory.TECHNICAL,
        "is_ats_optimized": False,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/technical.png",
        "description": "Clean modern layout with skills highlight block. Ideal for engineering roles.",
    },
    {
        "slug": "modern_ats_letter",
        "name": "Modern ATS Letter",
        "category": TemplateCategory.ATS,
        "is_ats_optimized": True,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/ats.png",
        "description": "ATS-first single-column layout with maximum parser compatibility.",
    },
    {
        "slug": "ats_clean_letter",
        "name": "ATS Clean",
        "category": TemplateCategory.ATS,
        "is_ats_optimized": True,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/ats.png",
        "description": "ATS-first single-column layout with maximum parser compatibility.",
    },
]

PORTFOLIO_THEMES = [
    {
        "slug": "professional",
        "name": "Professional",
        "category": TemplateCategory.PROFESSIONAL,
        "is_ats_optimized": False,
        "is_single_page": False,
        "is_premium": False,
        "thumbnail_path": "/templates/professional.png",
        "description": "Clean, corporate portfolio with blue accent. Works for all industries.",
    },
    {
        "slug": "developer",
        "name": "Developer",
        "category": TemplateCategory.TECHNICAL,
        "is_ats_optimized": False,
        "is_single_page": False,
        "is_premium": False,
        "thumbnail_path": "/templates/technical.png",
        "description": "Dark terminal-inspired theme with monospace typography. Perfect for engineers.",
    },
    {
        "slug": "executive",
        "name": "Executive",
        "category": TemplateCategory.EXECUTIVE,
        "is_ats_optimized": False,
        "is_single_page": False,
        "is_premium": True,
        "thumbnail_path": "/templates/executive.png",
        "description": "Navy and gold luxury design for senior leadership and C-suite profiles.",
    },
    {
        "slug": "minimal",
        "name": "Minimal",
        "category": TemplateCategory.MINIMAL,
        "is_ats_optimized": False,
        "is_single_page": False,
        "is_premium": False,
        "thumbnail_path": "/templates/minimal.png",
        "description": "Ultra-clean serif typography. Content-first, zero visual noise.",
    },
    {
        "slug": "ats_clean_portfolio",
        "name": "ATS Clean",
        "category": TemplateCategory.ATS,
        "is_ats_optimized": True,
        "is_single_page": True,
        "is_premium": False,
        "thumbnail_path": "/templates/ats.png",
        "description": "Clean, parser-friendly text portfolio layout focusing heavily on readability and accessibility.",
    },
]


class Command(BaseCommand):
    help = "Seed all built-in resume, cover-letter, and portfolio templates into the database"

    def handle(self, *args, **options):
        from apps.templates_engine.services import TemplateRenderer
        
        DUMMY_PROFILE = {
            "full_name": "Jane Doe",
            "headline": "Senior Software Engineer",
            "email": "jane@example.com",
            "phone": "+1 555-0100",
            "location": {"city": "San Francisco", "state": "CA"},
            "professional_summary": "Experienced engineer specializing in scalable backend systems and cloud infrastructure. Proven track record of improving system performance and leading high-performing teams.",
            "work_experiences": [
                {
                    "job_title": "Senior Engineer",
                    "company_name": "Tech Corp",
                    "start_date": "2020-01",
                    "is_current": True,
                    "location": {"city": "San Francisco"},
                    "description": "Led the backend team.\nArchitected microservices.\nImproved DB performance by 40%."
                },
                {
                    "job_title": "Software Engineer",
                    "company_name": "Startup Inc",
                    "start_date": "2017-06",
                    "end_date": "2019-12",
                    "location": {"city": "New York"},
                    "description": "Developed REST APIs.\nMaintained legacy systems."
                }
            ],
            "educations": [
                {
                    "degree": "B.S. Computer Science",
                    "institution": "University of Technology",
                    "start_date": "2013",
                    "end_date": "2017",
                    "gpa": "3.9"
                }
            ],
            "skills": [
                {"name": "Python", "category": "Languages"},
                {"name": "TypeScript", "category": "Languages"},
                {"name": "PostgreSQL", "category": "Databases"},
                {"name": "AWS", "category": "Cloud"}
            ]
        }
        
        DUMMY_LETTER = {
            "recipient_name": "Hiring Manager",
            "recipient_company": "Future Employer LLC",
            "recipient_address": "123 Business Rd",
            "body": "I am writing to express my interest in the open position. With my background in building scalable systems and my passion for engineering excellence, I am confident I can make an immediate impact."
        }
        
        DUMMY_PORTFOLIO = {
            "hero_title": "Hello, I'm Jane.",
            "hero_subtitle": "I build things for the web.",
            "about_text": "I'm a software engineer based in SF.",
            "seo": {"title": "Jane Doe - Portfolio", "description": "My portfolio", "json_ld": {}}
        }

        created = 0
        updated = 0

        for tmpl_data in RESUME_TEMPLATES:
            t, was_created = Template.objects.update_or_create(
                slug=tmpl_data["slug"],
                defaults={**tmpl_data, "type": TemplateType.RESUME, "is_active": True},
            )
            html = TemplateRenderer.render_resume(t, DUMMY_PROFILE)
            t.preview_data = {"html": html}
            t.save(update_fields=["preview_data"])
            if was_created:
                created += 1
            else:
                updated += 1

        for tmpl_data in COVER_LETTER_TEMPLATES:
            t, was_created = Template.objects.update_or_create(
                slug=tmpl_data["slug"],
                defaults={**tmpl_data, "type": TemplateType.COVER_LETTER, "is_active": True},
            )
            html = TemplateRenderer.render_cover_letter(t, DUMMY_PROFILE, DUMMY_LETTER)
            t.preview_data = {"html": html}
            t.save(update_fields=["preview_data"])
            if was_created:
                created += 1
            else:
                updated += 1

        for tmpl_data in PORTFOLIO_THEMES:
            t, was_created = Template.objects.update_or_create(
                slug=tmpl_data["slug"],
                defaults={**tmpl_data, "type": TemplateType.PORTFOLIO, "is_active": True},
            )
            html = TemplateRenderer.render_portfolio(t, DUMMY_PROFILE, DUMMY_PORTFOLIO, {})
            t.preview_data = {"html": html}
            t.save(update_fields=["preview_data"])
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Templates seeded: {created} created, {updated} updated."
            )
        )
