import pytest
from unittest.mock import patch, MagicMock
from rest_framework import status

BASE_URL = "/api/v1/templates/"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def resume_template(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="professional-resume-test",
        defaults={
            "name": "Professional",
            "type": "resume",
            "category": "professional",
            "is_ats_optimized": False,
            "is_active": True,
        },
    )
    return t


@pytest.fixture
def cover_letter_template_t(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="cl-professional",
        defaults={
            "name": "CL Professional",
            "type": "cover_letter",
            "category": "professional",
            "is_active": True,
        },
    )
    return t


@pytest.fixture
def portfolio_template(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="portfolio-minimal",
        defaults={
            "name": "Minimal Portfolio",
            "type": "portfolio",
            "category": "minimal",
            "is_active": True,
        },
    )
    return t


@pytest.fixture
def inactive_template(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="deprecated-template",
        defaults={
            "name": "Deprecated",
            "type": "resume",
            "category": "general",
            "is_active": False,
        },
    )
    return t


# ─── Template API ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTemplateList:
    def test_requires_auth(self, api_client):
        response = api_client.get(BASE_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_returns_active_templates(self, auth_client, resume_template):
        response = auth_client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert isinstance(data, list)
        slugs = [t["slug"] for t in data]
        assert resume_template.slug in slugs

    def test_inactive_templates_excluded(self, auth_client, inactive_template, resume_template):
        response = auth_client.get(BASE_URL)
        slugs = [t["slug"] for t in response.json()["data"]]
        assert inactive_template.slug not in slugs

    def test_filter_by_type_resume(self, auth_client, resume_template, cover_letter_template_t):
        response = auth_client.get(f"{BASE_URL}?type=resume")
        assert response.status_code == status.HTTP_200_OK
        types = [t["type"] for t in response.json()["data"]]
        assert all(t == "resume" for t in types)

    def test_filter_by_type_cover_letter(self, auth_client, cover_letter_template_t):
        response = auth_client.get(f"{BASE_URL}?type=cover_letter")
        types = [t["type"] for t in response.json()["data"]]
        assert all(t == "cover_letter" for t in types)

    def test_filter_by_category(self, auth_client, resume_template):
        response = auth_client.get(f"{BASE_URL}?category=professional")
        data = response.json()["data"]
        assert all(t["category"] == "professional" for t in data)

    def test_list_contains_expected_fields(self, auth_client, resume_template):
        response = auth_client.get(BASE_URL)
        if response.json()["data"]:
            item = response.json()["data"][0]
            for field in ["id", "slug", "name", "type", "category", "is_ats_optimized"]:
                assert field in item

    def test_response_envelope(self, auth_client, resume_template):
        response = auth_client.get(BASE_URL)
        body = response.json()
        assert body["success"] is True
        assert "data" in body


@pytest.mark.django_db
class TestTemplateRetrieve:
    def test_retrieve_by_slug(self, auth_client, resume_template):
        response = auth_client.get(f"{BASE_URL}{resume_template.slug}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["slug"] == resume_template.slug

    def test_retrieve_nonexistent_returns_404(self, auth_client):
        response = auth_client.get(f"{BASE_URL}nonexistent-slug/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_inactive_template_returns_404(self, auth_client, inactive_template):
        response = auth_client.get(f"{BASE_URL}{inactive_template.slug}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── TemplateRenderer ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTemplateRenderer:
    def test_render_resume_returns_string(self, template, full_profile):
        from apps.templates_engine.services import TemplateRenderer
        from apps.profiles.profile_utils import ProfileSerializer
        from apps.profiles.models import UserProfile
        from apps.authentication.models import User
        from apps.profiles.models import UserProfile

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(id=full_profile.id)
        profile_data = ProfileSerializer.to_dict(profile)

        html = TemplateRenderer.render_resume(template, profile_data, {})
        assert isinstance(html, str)
        assert len(html) > 0

    def test_render_resume_contains_html_tag(self, template, full_profile):
        from apps.templates_engine.services import TemplateRenderer
        from apps.profiles.profile_utils import ProfileSerializer
        from apps.profiles.models import UserProfile

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(id=full_profile.id)
        profile_data = ProfileSerializer.to_dict(profile)

        html = TemplateRenderer.render_resume(template, profile_data, {})
        assert "<html" in html or "<!DOCTYPE" in html or "<div" in html

    def test_render_resume_missing_template_file_falls_back(self, db):
        from apps.templates_engine.services import TemplateRenderer
        from apps.templates_engine.models import Template
        missing_tmpl, _ = Template.objects.get_or_create(
            slug="definitely-missing-slug-xyz",
            defaults={"name": "Missing", "type": "resume", "category": "general", "is_active": True},
        )
        html = TemplateRenderer.render_resume(missing_tmpl, {"full_name": "Test User"}, {})
        assert isinstance(html, str)

    def test_render_cover_letter_returns_string(self, cover_letter_template_t, profile, db):
        from apps.templates_engine.services import TemplateRenderer
        html = TemplateRenderer.render_cover_letter(
            cover_letter_template_t,
            {"full_name": "Jane Doe", "email": "jane@example.com"},
            {
                "company_name": "Google",
                "job_title": "Engineer",
                "tone": "professional",
                "body_content": "I am excited to apply.",
            },
        )
        assert isinstance(html, str)
        assert len(html) > 0


# ─── Template Model ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTemplateModel:
    def test_str_representation(self, resume_template):
        assert "Professional" in str(resume_template)
        assert "resume" in str(resume_template)

    def test_slug_is_unique(self, db):
        from apps.templates_engine.models import Template
        from django.db import IntegrityError
        Template.objects.create(slug="unique-test-slug", name="T1", type="resume", category="general")
        with pytest.raises(IntegrityError):
            Template.objects.create(slug="unique-test-slug", name="T2", type="resume", category="general")

    def test_is_active_default_true(self, db):
        from apps.templates_engine.models import Template
        t = Template.objects.create(slug="default-active", name="T", type="resume", category="general")
        assert t.is_active is True

    def test_is_premium_default_false(self, db):
        from apps.templates_engine.models import Template
        t = Template.objects.create(slug="default-premium", name="T", type="resume", category="general")
        assert t.is_premium is False
