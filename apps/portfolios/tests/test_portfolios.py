import pytest
from unittest.mock import patch
from rest_framework import status

BASE_URL = "/api/v1/portfolios/"
PUBLIC_URL = "/api/v1/public/"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def portfolio_theme(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="professional",
        defaults={
            "name": "Professional",
            "type": "portfolio",
            "category": "professional",
            "is_active": True,
        },
    )
    return t


@pytest.fixture
def portfolio(user, profile, db):
    from apps.portfolios.models import Portfolio
    p, _ = Portfolio.objects.get_or_create(
        user=user,
        defaults={
            "profile": profile,
            "slug": user.username,
        },
    )
    return p


@pytest.fixture
def published_portfolio(portfolio, portfolio_theme):
    from apps.portfolios.models import Portfolio
    portfolio.theme = portfolio_theme
    portfolio.is_published = True
    portfolio.is_public = True
    portfolio.save()
    return portfolio


# ─── Auth & Basic Access ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortfolioAccess:
    def test_list_requires_auth(self, api_client):
        response = api_client.get(BASE_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_creates_portfolio_if_none(self, auth_client):
        response = auth_client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "slug" in data
        assert "is_published" in data

    def test_list_returns_existing_portfolio(self, auth_client, portfolio):
        response = auth_client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["slug"] == portfolio.slug

    def test_retrieve_returns_portfolio(self, auth_client, portfolio):
        response = auth_client.get(f"{BASE_URL}{portfolio.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["id"] == str(portfolio.id)

    def test_portfolio_contains_expected_fields(self, auth_client, portfolio):
        response = auth_client.get(BASE_URL)
        data = response.json()["data"]
        for field in ["id", "slug", "is_published", "section_settings", "public_url"]:
            assert field in data


# ─── Update ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortfolioUpdate:
    def test_update_slug(self, auth_client, portfolio):
        response = auth_client.patch(
            f"{BASE_URL}{portfolio.id}/",
            {"slug": "my-new-slug"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["slug"] == "my-new-slug"

    def test_update_duplicate_slug_rejected(self, auth_client, portfolio, second_user, db):
        from apps.portfolios.models import Portfolio
        other_portfolio = Portfolio.objects.get(user=second_user)
        other_portfolio.slug = "taken-slug"
        other_portfolio.save()
        response = auth_client.patch(
            f"{BASE_URL}{portfolio.id}/",
            {"slug": "taken-slug"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_seo_fields(self, auth_client, portfolio):
        response = auth_client.patch(
            f"{BASE_URL}{portfolio.id}/",
            {"seo_title": "John Doe — Senior Engineer", "seo_description": "My portfolio"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["seo_title"] == "John Doe — Senior Engineer"

    def test_update_analytics(self, auth_client, portfolio):
        response = auth_client.patch(
            f"{BASE_URL}{portfolio.id}/",
            {"analytics_provider": "plausible", "analytics_id": "mysite.com"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["analytics_provider"] == "plausible"

    def test_update_theme(self, auth_client, portfolio, portfolio_theme):
        response = auth_client.patch(
            f"{BASE_URL}{portfolio.id}/",
            {"theme_slug": portfolio_theme.slug},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["theme"]["slug"] == portfolio_theme.slug

    def test_update_invalid_theme_slug(self, auth_client, portfolio):
        response = auth_client.patch(
            f"{BASE_URL}{portfolio.id}/",
            {"theme_slug": "nonexistent-theme"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_creates_version(self, auth_client, portfolio):
        from apps.portfolios.models import PortfolioVersion
        initial = PortfolioVersion.objects.filter(portfolio=portfolio).count()
        auth_client.patch(f"{BASE_URL}{portfolio.id}/", {"seo_title": "Updated"}, format="json")
        assert PortfolioVersion.objects.filter(portfolio=portfolio).count() > initial


# ─── Publish / Unpublish ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortfolioPublishing:
    def test_publish_portfolio(self, auth_client, portfolio, portfolio_theme, full_profile):
        auth_client.patch(f"{BASE_URL}{portfolio.id}/", {"theme_slug": portfolio_theme.slug}, format="json")
        response = auth_client.post(f"{BASE_URL}publish/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_published"] is True

    def test_publish_sets_published_at(self, auth_client, portfolio, portfolio_theme, full_profile):
        auth_client.patch(f"{BASE_URL}{portfolio.id}/", {"theme_slug": portfolio_theme.slug}, format="json")
        auth_client.post(f"{BASE_URL}publish/")
        portfolio.refresh_from_db()
        assert portfolio.published_at is not None

    def test_unpublish_portfolio(self, auth_client, published_portfolio):
        response = auth_client.post(f"{BASE_URL}unpublish/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_published"] is False

    def test_unpublish_clears_published_status(self, auth_client, published_portfolio):
        from apps.portfolios.models import Portfolio
        auth_client.post(f"{BASE_URL}unpublish/")
        published_portfolio.refresh_from_db()
        assert not published_portfolio.is_published


# ─── Preview ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortfolioPreview:
    def test_preview_returns_html(self, auth_client, portfolio, portfolio_theme, full_profile):
        auth_client.patch(f"{BASE_URL}{portfolio.id}/", {"theme_slug": portfolio_theme.slug}, format="json")
        response = auth_client.get(f"{BASE_URL}preview/")
        assert response.status_code == status.HTTP_200_OK
        assert "html" in response.json()["data"]

    def test_preview_html_not_empty(self, auth_client, portfolio, portfolio_theme, full_profile):
        auth_client.patch(f"{BASE_URL}{portfolio.id}/", {"theme_slug": portfolio_theme.slug}, format="json")
        response = auth_client.get(f"{BASE_URL}preview/")
        assert len(response.json()["data"]["html"]) > 0

    def test_preview_without_theme_returns_fallback(self, auth_client, portfolio):
        response = auth_client.get(f"{BASE_URL}preview/")
        assert response.status_code == status.HTTP_200_OK


# ─── Versions ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortfolioVersions:
    def test_versions_list(self, auth_client, portfolio):
        response = auth_client.get(f"{BASE_URL}versions/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json()["data"], list)

    def test_version_has_expected_fields(self, auth_client, portfolio):
        auth_client.patch(f"{BASE_URL}{portfolio.id}/", {"seo_title": "v2"}, format="json")
        response = auth_client.get(f"{BASE_URL}versions/")
        versions = response.json()["data"]
        if versions:
            assert "version_number" in versions[0]
            assert "change_summary" in versions[0]


# ─── Section Management ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSectionManagement:
    def test_default_sections_exist(self, auth_client, portfolio):
        response = auth_client.get(BASE_URL)
        sections = response.json()["data"]["section_settings"]
        assert "hero" in sections
        assert "experience" in sections
        assert "contact" in sections

    def test_toggle_section_off(self, auth_client, portfolio):
        response = auth_client.post(
            f"{BASE_URL}toggle-section/",
            {"section": "achievements", "enabled": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        sections = response.json()["data"]["section_settings"]
        assert sections["achievements"]["enabled"] is False

    def test_toggle_section_on(self, auth_client, portfolio):
        response = auth_client.post(
            f"{BASE_URL}toggle-section/",
            {"section": "publications", "enabled": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        sections = response.json()["data"]["section_settings"]
        assert sections["publications"]["enabled"] is True

    def test_toggle_invalid_section_returns_400(self, auth_client, portfolio):
        response = auth_client.post(
            f"{BASE_URL}toggle-section/",
            {"section": "nonexistent", "enabled": True},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reorder_sections(self, auth_client, portfolio):
        new_order = ["hero", "skills", "experience", "projects", "contact"]
        response = auth_client.post(
            f"{BASE_URL}reorder-sections/",
            {"order": new_order},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_reorder_invalid_type_returns_400(self, auth_client, portfolio):
        response = auth_client.post(
            f"{BASE_URL}reorder-sections/",
            {"order": "not-a-list"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── SEO ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSEO:
    def test_seo_endpoint_returns_data(self, auth_client, portfolio):
        response = auth_client.get(f"{BASE_URL}seo/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "title" in data
        assert "description" in data
        assert "json_ld" in data

    def test_seo_contains_json_ld(self, auth_client, portfolio):
        response = auth_client.get(f"{BASE_URL}seo/")
        json_ld = response.json()["data"]["json_ld"]
        assert json_ld["@type"] == "Person"

    def test_auto_fill_seo_populates_empty_fields(self, auth_client, portfolio, full_profile):
        response = auth_client.post(f"{BASE_URL}auto-fill-seo/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["seo_title"] != ""
        assert data["seo_description"] != ""


# ─── Public Endpoints ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPublicEndpoints:
    def test_public_by_username_not_found_when_unpublished(self, api_client, portfolio):
        response = api_client.get(f"{PUBLIC_URL}u/{portfolio.user.username}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_public_by_username_returns_data_when_published(
        self, api_client, published_portfolio
    ):
        username = published_portfolio.user.username
        response = api_client.get(f"{PUBLIC_URL}u/{username}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "portfolio" in data
        assert "profile" in data
        assert "seo" in data

    def test_public_by_slug_not_found_when_unpublished(self, api_client, portfolio):
        response = api_client.get(f"{PUBLIC_URL}portfolio/{portfolio.slug}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_public_by_slug_returns_data_when_published(
        self, api_client, published_portfolio
    ):
        response = api_client.get(f"{PUBLIC_URL}portfolio/{published_portfolio.slug}/")
        assert response.status_code == status.HTTP_200_OK
        assert "portfolio" in response.json()["data"]

    def test_public_endpoints_no_auth_required(self, api_client, published_portfolio):
        resp1 = api_client.get(f"{PUBLIC_URL}u/{published_portfolio.user.username}/")
        resp2 = api_client.get(f"{PUBLIC_URL}portfolio/{published_portfolio.slug}/")
        assert resp1.status_code == status.HTTP_200_OK
        assert resp2.status_code == status.HTTP_200_OK

    def test_public_profile_data_present(self, api_client, published_portfolio, full_profile):
        response = api_client.get(f"{PUBLIC_URL}u/{published_portfolio.user.username}/")
        profile = response.json()["data"]["profile"]
        assert "full_name" in profile
        assert "work_experiences" in profile


# ─── Analytics ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAnalytics:
    def test_google_analytics_script_generated(self):
        from apps.portfolios.analytics import get_analytics_script
        script = get_analytics_script("google_analytics", "G-XXXXXXXXXX")
        assert "G-XXXXXXXXXX" in script
        assert "gtag" in script

    def test_plausible_script_generated(self):
        from apps.portfolios.analytics import get_analytics_script
        script = get_analytics_script("plausible", "mysite.com")
        assert "mysite.com" in script
        assert "plausible.io" in script

    def test_posthog_script_generated(self):
        from apps.portfolios.analytics import get_analytics_script
        script = get_analytics_script("posthog", "phc_test123")
        assert "phc_test123" in script

    def test_none_provider_returns_empty(self):
        from apps.portfolios.analytics import get_analytics_script
        assert get_analytics_script("none", "") == ""
        assert get_analytics_script("none", "some-id") == ""

    def test_empty_id_returns_empty(self):
        from apps.portfolios.analytics import get_analytics_script
        assert get_analytics_script("google_analytics", "") == ""


# ─── Service Layer ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortfolioService:
    def test_get_or_create_creates_portfolio(self, user, db):
        from apps.portfolios.services import PortfolioService
        portfolio, created = PortfolioService.get_or_create_for_user(user)
        assert portfolio.pk is not None
        assert created or portfolio.user == user

    def test_seo_generator_includes_json_ld(self, user, profile, db):
        from apps.portfolios.services import SEOGenerator, PortfolioService
        portfolio, _ = PortfolioService.get_or_create_for_user(user)
        seo = PortfolioService.generate_seo(portfolio)
        assert "@type" in seo["json_ld"]
        assert seo["json_ld"]["@type"] == "Person"

    def test_unique_slug_generation(self, user, db):
        from apps.portfolios.services import PortfolioService
        slug = PortfolioService._unique_slug("testuser")
        assert slug is not None
        assert len(slug) > 0

    def test_section_defaults_merged(self, portfolio):
        sections = portfolio.get_section_settings()
        assert "hero" in sections
        assert "contact" in sections
        assert sections["hero"]["enabled"] is True

    def test_rebuild_preview_returns_string(self, portfolio, portfolio_theme, full_profile):
        portfolio.theme = portfolio_theme
        portfolio.save()
        from apps.portfolios.services import PortfolioService
        html = PortfolioService.rebuild_preview(portfolio)
        assert isinstance(html, str)
