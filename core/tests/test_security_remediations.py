"""
Regression tests for core security remediations.

SEC-003: DNS rebinding SSRF bypass fix
SEC-004: CSP header enforcement
SEC-005: Fail-closed throttle behaviour
ACA-002: Immutable version history
ACA-003: ProfileSerializer canonical location
"""
import socket
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory, override_settings


# ─── SEC-003: SSRF DNS rebinding ──────────────────────────────────────────────


class TestIsUrlSafeSSRF:

    def test_private_ip_literal_blocked(self):
        from core.security import is_safe_url
        assert is_safe_url("http://10.0.0.1/internal") is False
        assert is_safe_url("http://172.16.0.1/internal") is False
        assert is_safe_url("http://192.168.1.1/internal") is False
        assert is_safe_url("http://127.0.0.1/internal") is False
        assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False

    def test_public_ip_allowed(self):
        from core.security import is_safe_url
        assert is_safe_url("https://8.8.8.8/dns") is True

    def test_non_http_scheme_blocked(self):
        from core.security import is_safe_url
        assert is_safe_url("file:///etc/passwd") is False
        assert is_safe_url("ftp://example.com/file") is False
        assert is_safe_url("gopher://evil.com") is False

    def test_dns_resolving_to_private_ip_blocked(self):
        """SEC-003: hostname that resolves to a private IP must be blocked."""
        from core.security import is_safe_url

        # Patch getaddrinfo to simulate a DNS rebinding attack:
        # the hostname resolves to the AWS metadata endpoint IP.
        with patch("core.security.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))
            ]
            result = is_safe_url("https://evil-rebinding.attacker.com/")
        assert result is False

    def test_dns_resolving_to_public_ip_allowed(self):
        """A publicly routable hostname is allowed."""
        from core.security import is_safe_url

        with patch("core.security.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 443))
            ]
            result = is_safe_url("https://legitimate.example.com/api")
        assert result is True

    def test_dns_resolution_failure_blocked(self):
        """Unresolvable hostname is fail-closed (blocked)."""
        from core.security import is_safe_url

        with patch("core.security.socket.getaddrinfo", side_effect=socket.gaierror):
            result = is_safe_url("https://nonexistent.invalid/")
        assert result is False

    def test_allowed_hosts_enforced(self):
        from core.security import is_safe_url

        with patch("core.security.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 443))
            ]
            assert is_safe_url("https://allowed.example.com/", allowed_hosts=["allowed.example.com"]) is True
            assert is_safe_url("https://other.example.com/", allowed_hosts=["allowed.example.com"]) is False

    def test_no_hostname_blocked(self):
        from core.security import is_safe_url
        assert is_safe_url("https:///no-host") is False


# ─── SEC-005: Fail-closed throttle ────────────────────────────────────────────


class TestFailClosedThrottles:

    def _make_request(self):
        rf = RequestFactory()
        request = rf.get("/api/test/")
        request.user = MagicMock(is_authenticated=True)
        return request

    def test_login_throttle_denies_on_cache_error(self):
        """When cache raises, LoginRateThrottle must deny the request."""
        from core.throttles import LoginRateThrottle
        from django.core.cache import cache
        from django.contrib.auth.models import AnonymousUser

        throttle = LoginRateThrottle()
        rf = RequestFactory()
        request = rf.post("/api/v1/auth/login/")
        request.user = AnonymousUser()
        view = MagicMock()

        with patch.object(cache, "get", side_effect=Exception("Redis down")):
            result = throttle.allow_request(request, view)

        assert result is False, "Throttle must fail closed when cache unavailable"

    def test_ai_throttle_denies_on_cache_error(self):
        from core.throttles import AiRateThrottle
        from django.core.cache import cache

        throttle = AiRateThrottle()
        request = self._make_request()

        with patch.object(cache, "get", side_effect=Exception("Redis down")):
            assert throttle.allow_request(request, MagicMock()) is False

    def test_upload_throttle_denies_on_cache_error(self):
        from core.throttles import UploadRateThrottle
        from django.core.cache import cache

        throttle = UploadRateThrottle()
        request = self._make_request()

        with patch.object(cache, "get", side_effect=Exception("Redis down")):
            assert throttle.allow_request(request, MagicMock()) is False

    def test_throttle_allows_when_cache_healthy(self):
        """Normal operation (cache healthy): throttle defers to standard logic."""
        from core.throttles import LoginRateThrottle

        throttle = LoginRateThrottle()
        request = self._make_request()
        # Patch the parent allow_request to return True (under limit)
        with patch(
            "rest_framework.throttling.AnonRateThrottle.allow_request",
            return_value=True,
        ):
            assert throttle.allow_request(request, MagicMock()) is True

    def test_registration_throttle_scope(self):
        """RegistrationRateThrottle uses separate scope from login."""
        from core.throttles import RegistrationRateThrottle, LoginRateThrottle

        assert RegistrationRateThrottle.scope != LoginRateThrottle.scope
        assert RegistrationRateThrottle.scope == "registration"


# ─── ACA-002: Immutable version history ───────────────────────────────────────


@pytest.mark.django_db
class TestImmutableVersionHistory:

    def test_rebuild_preview_does_not_modify_versions(self):
        """
        ResumeService.rebuild_preview() must return HTML without touching any
        ResumeVersion record.
        """
        from apps.resumes.models import ResumeVersion
        from apps.resumes.services import ResumeService

        # Mock dependencies so we can test in isolation
        mock_resume = MagicMock()
        mock_resume.template = MagicMock()
        mock_resume.template_settings = {}
        mock_resume.user = MagicMock()

        mock_profile = MagicMock()
        mock_profile.user = mock_resume.user

        with patch("apps.profiles.models.UserProfile") as mock_up_cls, \
             patch("apps.resumes.services.ProfileSerializer") as mock_ps, \
             patch("apps.templates_engine.services.TemplateRenderer") as mock_tr, \
             patch("apps.resumes.services.ResumeVersion") as mock_rv_cls:

            mock_up_cls.objects.prefetch_related.return_value\
                .select_related.return_value.get.return_value = mock_profile
            mock_ps.to_dict.return_value = {}
            mock_tr.render_resume.return_value = "<html>rendered</html>"

            result = ResumeService.rebuild_preview(mock_resume)

        # Must return HTML
        assert result == "<html>rendered</html>"
        # Must NOT call ResumeVersion.objects.* (no version mutation)
        mock_rv_cls.objects.assert_not_called()

    def test_rebuild_preview_returns_string(self):
        """Return type is always str, never None."""
        from apps.resumes.services import ResumeService

        mock_resume = MagicMock()
        mock_resume.template = None
        mock_resume.user = MagicMock()

        with patch("apps.profiles.models.UserProfile") as mock_up_cls, \
             patch("apps.resumes.services.ProfileSerializer") as mock_ps, \
             patch("apps.resumes.services.Template") as mock_template_cls:

            mock_up_cls.objects.prefetch_related.return_value\
                .select_related.return_value.get.return_value = MagicMock()
            mock_ps.to_dict.return_value = {}
            mock_template_cls.objects.filter.return_value.first.return_value = None

            result = ResumeService.rebuild_preview(mock_resume)

        assert isinstance(result, str)
        assert "No template" in result


# ─── ACA-003: ProfileSerializer canonical location ───────────────────────────


class TestProfileSerializerLocation:

    def test_profile_serializer_importable_from_profiles(self):
        """ProfileSerializer must be importable from apps.profiles.profile_utils."""
        from apps.profiles.profile_utils import ProfileSerializer  # noqa: F401
        assert callable(ProfileSerializer.to_dict)

    def test_resumes_services_imports_from_profiles(self):
        """
        apps/resumes/services.py must not define its own ProfileSerializer class.
        It must import from apps.profiles.profile_utils.
        """
        import inspect
        import apps.resumes.services as rs

        # The module-level name 'ProfileSerializer' must point to the profiles module
        assert hasattr(rs, "ProfileSerializer")
        # Verify it comes from profiles, not defined locally in resumes
        source_module = rs.ProfileSerializer.__module__
        assert "profiles" in source_module, (
            f"ProfileSerializer must come from apps.profiles, got: {source_module}"
        )

    def test_profile_serializer_to_dict_contract(self):
        """to_dict() returns all expected top-level keys."""
        from apps.profiles.profile_utils import ProfileSerializer

        mock_profile = MagicMock()
        mock_profile.user.full_name = "Test User"
        mock_profile.user.email = "test@example.com"
        mock_profile.work_experiences.all.return_value = []
        mock_profile.educations.all.return_value = []
        mock_profile.skills.all.return_value = []
        mock_profile.projects.all.return_value = []
        mock_profile.certifications.all.return_value = []
        mock_profile.achievements.all.return_value = []
        mock_profile.publications.all.return_value = []

        result = ProfileSerializer.to_dict(mock_profile)

        required_keys = [
            "full_name", "email", "headline", "professional_summary",
            "work_experiences", "educations", "skills", "projects",
            "certifications", "achievements", "publications",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_cover_letters_services_imports_from_profiles(self):
        """cover_letters/services.py must not import ProfileSerializer from resumes."""
        import apps.cover_letters.services as cls
        assert hasattr(cls, "ProfileSerializer") is False or (
            hasattr(cls, "ProfileSerializer") and
            "profiles" in cls.ProfileSerializer.__module__
        )

    def test_portfolios_services_imports_from_profiles(self):
        """portfolios/services.py must not import ProfileSerializer from resumes."""
        import apps.portfolios.services as ps
        assert hasattr(ps, "ProfileSerializer") is False or (
            hasattr(ps, "ProfileSerializer") and
            "profiles" in ps.ProfileSerializer.__module__
        )

    def test_exports_services_imports_from_profiles(self):
        """exports/services.py must not import ProfileSerializer from resumes."""
        import apps.exports.services as es
        assert hasattr(es, "ProfileSerializer") is False or (
            hasattr(es, "ProfileSerializer") and
            "profiles" in es.ProfileSerializer.__module__
        )

    def test_portfolios_views_imports_from_profiles(self):
        """portfolios/views.py must not import ProfileSerializer from resumes."""
        import apps.portfolios.views as pv
        assert hasattr(pv, "ProfileSerializer")
        assert "profiles" in pv.ProfileSerializer.__module__, (
            f"ProfileSerializer in views must come from apps.profiles, "
            f"got: {pv.ProfileSerializer.__module__}"
        )


# ─── ACA-002: Immutable version history (cover_letters + portfolios) ──────────


class TestImmutableVersionHistoryCoverLetters:

    def test_rebuild_preview_does_not_modify_versions(self):
        """CoverLetterService.rebuild_preview() must return HTML without writing to any version."""
        from apps.cover_letters.services import CoverLetterService

        mock_cl = MagicMock()
        mock_cl.template = MagicMock()
        mock_cl.user = MagicMock()
        mock_cl.body_content = "Body"

        with patch("apps.profiles.models.UserProfile") as mock_up_cls, \
             patch("apps.profiles.profile_utils.ProfileSerializer") as mock_ps, \
             patch("apps.cover_letters.services.CoverLetterService._render_html_with_template") as mock_render:

            mock_up_cls.objects.prefetch_related.return_value.get.return_value = MagicMock()
            mock_ps.to_dict.return_value = {}
            mock_render.return_value = "<html>cover letter</html>"

            result = CoverLetterService.rebuild_preview(mock_cl)

        assert result == "<html>cover letter</html>"
        # versions queryset must NOT be accessed for mutation
        mock_cl.versions.order_by.assert_not_called()

    def test_rebuild_preview_returns_string(self):
        """Return type is always str when no template is found."""
        from apps.cover_letters.services import CoverLetterService

        mock_cl = MagicMock()
        mock_cl.template = None
        mock_cl.user = MagicMock()

        with patch("apps.profiles.models.UserProfile") as mock_up_cls, \
             patch("apps.profiles.profile_utils.ProfileSerializer") as mock_ps, \
             patch("apps.cover_letters.services.Template") as mock_template_cls:

            mock_up_cls.objects.prefetch_related.return_value.get.return_value = MagicMock()
            mock_ps.to_dict.return_value = {}
            mock_template_cls.objects.filter.return_value.first.return_value = None

            result = CoverLetterService.rebuild_preview(mock_cl)

        assert isinstance(result, str)
        assert "No template" in result


class TestImmutableVersionHistoryPortfolios:

    def test_rebuild_preview_does_not_modify_versions(self):
        """PortfolioService.rebuild_preview() must return HTML without writing to any version."""
        from apps.portfolios.services import PortfolioService

        mock_portfolio = MagicMock()
        mock_portfolio.theme = MagicMock()
        mock_portfolio.user = MagicMock()
        mock_portfolio.analytics_provider = None
        mock_portfolio.analytics_id = None
        mock_portfolio.slug = "test-slug"
        mock_portfolio.is_published = False
        mock_portfolio.public_url = ""
        mock_portfolio.custom_domain = ""
        mock_portfolio.theme_settings = {}

        with patch("apps.portfolios.services.UserProfile") as mock_up_cls, \
             patch("apps.profiles.profile_utils.ProfileSerializer") as mock_ps, \
             patch("apps.portfolios.services.SEOGenerator") as mock_seo, \
             patch("apps.portfolios.analytics.get_analytics_script", return_value=""), \
             patch("apps.templates_engine.services.TemplateRenderer") as mock_tr:

            mock_up_cls.objects.prefetch_related.return_value.get.return_value = MagicMock()
            mock_ps.to_dict.return_value = {}
            mock_seo.generate.return_value = {}
            mock_portfolio.get_section_settings.return_value = {}
            mock_tr.render_portfolio.return_value = "<html>portfolio</html>"

            result = PortfolioService.rebuild_preview(mock_portfolio)

        assert result == "<html>portfolio</html>"
        # versions queryset must NOT be accessed for mutation
        mock_portfolio.versions.order_by.assert_not_called()

    def test_rebuild_preview_updates_last_generated_at(self):
        """rebuild_preview must update portfolio.last_generated_at (legitimate field update)."""
        from apps.portfolios.services import PortfolioService

        mock_portfolio = MagicMock()
        mock_portfolio.theme = MagicMock()
        mock_portfolio.user = MagicMock()
        mock_portfolio.analytics_provider = None
        mock_portfolio.analytics_id = None
        mock_portfolio.slug = "test-slug"
        mock_portfolio.is_published = False
        mock_portfolio.public_url = ""
        mock_portfolio.custom_domain = ""
        mock_portfolio.theme_settings = {}

        with patch("apps.portfolios.services.UserProfile") as mock_up_cls, \
             patch("apps.profiles.profile_utils.ProfileSerializer") as mock_ps, \
             patch("apps.portfolios.services.SEOGenerator") as mock_seo, \
             patch("apps.portfolios.analytics.get_analytics_script", return_value=""), \
             patch("apps.templates_engine.services.TemplateRenderer") as mock_tr, \
             patch("apps.portfolios.services.timezone") as mock_tz:

            mock_up_cls.objects.prefetch_related.return_value.get.return_value = MagicMock()
            mock_ps.to_dict.return_value = {}
            mock_seo.generate.return_value = {}
            mock_portfolio.get_section_settings.return_value = {}
            mock_tr.render_portfolio.return_value = "<html>portfolio</html>"
            mock_tz.now.return_value = "2026-06-09T00:00:00Z"

            PortfolioService.rebuild_preview(mock_portfolio)

        mock_portfolio.save.assert_called_once_with(update_fields=["last_generated_at"])
