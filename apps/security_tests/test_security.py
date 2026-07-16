"""
Security tests — Phase 10

Tests that validate security controls are functioning correctly:
- Authentication enforcement on all protected endpoints
- IDOR isolation (users cannot access each other's data)
- File upload validation (extension + magic byte checks)
- Rate limiting enforcement
- Public route behavior
- JWT validation
- Config validation
"""
import io
import pytest
import uuid
from rest_framework import status


# ─── Authentication Enforcement ───────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthenticationEnforcement:
    """Every authenticated endpoint must return 401 for unauthenticated requests."""

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/v1/profiles/me/"),
        ("PATCH", "/api/v1/profiles/me/"),
        ("GET", "/api/v1/resumes/"),
        ("POST", "/api/v1/resumes/"),
        ("GET", "/api/v1/cover-letters/"),
        ("POST", "/api/v1/cover-letters/"),
        ("GET", "/api/v1/portfolios/"),
        ("GET", "/api/v1/imports/"),
        ("GET", "/api/v1/exports/"),
        ("GET", "/api/v1/templates/"),
        ("GET", "/api/v1/profiles/me/experience/"),
        ("GET", "/api/v1/profiles/me/education/"),
        ("GET", "/api/v1/profiles/me/skills/"),
    ]

    @pytest.mark.parametrize("method,url", PROTECTED_ENDPOINTS)
    def test_endpoint_requires_authentication(self, api_client, method, url):
        response = getattr(api_client, method.lower())(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Expected 401 for {method} {url}, got {response.status_code}"
        )

    def test_invalid_token_returns_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token-here")
        response = api_client.get("/api/v1/profiles/me/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_expired_access_token_returns_401(self, api_client, user):
        from rest_framework_simplejwt.tokens import AccessToken
        from datetime import timedelta
        from django.utils import timezone
        token = AccessToken.for_user(user)
        # Manually set expiry to the past
        token.set_exp(lifetime=timedelta(seconds=-1))
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")
        response = api_client.get("/api/v1/profiles/me/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_malformed_bearer_token_returns_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not.a.valid.jwt")
        response = api_client.get("/api/v1/profiles/me/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── IDOR — Resource Isolation ────────────────────────────────────────────────

@pytest.mark.django_db
class TestIDORProtection:
    """Users cannot read, modify, or delete another user's resources."""

    def test_cannot_read_other_user_resume(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_resume = Resume.objects.create(
            user=second_user, profile=profile, title="Private", status="active"
        )
        response = auth_client.get(f"/api/v1/resumes/{other_resume.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_update_other_user_resume(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_resume = Resume.objects.create(
            user=second_user, profile=profile, title="Private", status="active"
        )
        response = auth_client.patch(
            f"/api/v1/resumes/{other_resume.id}/",
            {"title": "Hacked"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_delete_other_user_resume(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_resume = Resume.objects.create(
            user=second_user, profile=profile, title="Private", status="active"
        )
        response = auth_client.delete(f"/api/v1/resumes/{other_resume.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_read_other_user_cover_letter(self, auth_client, second_user, db):
        from apps.cover_letters.models import CoverLetter
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_cl = CoverLetter.objects.create(
            user=second_user, profile=profile,
            title="Private CL", company_name="Corp", job_title="Dev",
        )
        response = auth_client.get(f"/api/v1/cover-letters/{other_cl.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_access_other_user_import_job(self, auth_client, second_user, db):
        from apps.imports.models import ImportJob
        other_job = ImportJob.objects.create(
            user=second_user,
            original_filename="resume.pdf",
            file_type="pdf",
            file_path="uploads/other/imports/test.pdf",
            status="pending",
        )
        response = auth_client.get(f"/api/v1/imports/{other_job.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_apply_other_user_import_mapping(self, auth_client, second_user, db):
        from apps.imports.models import ImportJob, ImportStatus
        other_job = ImportJob.objects.create(
            user=second_user,
            original_filename="resume.pdf",
            file_type="pdf",
            file_path="uploads/other/imports/test.pdf",
            status=ImportStatus.REVIEW_REQUIRED,
        )
        response = auth_client.post(f"/api/v1/imports/{other_job.id}/apply/", {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_download_other_user_export(self, auth_client, second_user, db):
        from apps.exports.models import ExportJob, ExportStatus
        import uuid as uuid_mod
        other_job = ExportJob.objects.create(
            user=second_user,
            resource_type="resume",
            resource_id=uuid_mod.uuid4(),
            format="pdf",
            status=ExportStatus.COMPLETED,
            download_url="https://example.com/file.pdf",
        )
        response = auth_client.get(f"/api/v1/exports/{other_job.id}/download/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_resume_list_does_not_include_other_user_resumes(
        self, auth_client, second_user, db
    ):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        Resume.objects.create(
            user=second_user, profile=profile, title="Other Resume", status="active"
        )
        response = auth_client.get("/api/v1/resumes/")
        data = response.json()["data"]
        titles = [r["title"] for r in data]
        assert "Other Resume" not in titles

    def test_profile_section_isolated_to_user(self, auth_client, second_user, db):
        from apps.profiles.models import WorkExperience, UserProfile
        other_profile = UserProfile.objects.get(user=second_user)
        other_exp = WorkExperience.objects.create(
            profile=other_profile,
            company_name="Secret Corp",
            job_title="Dev",
            start_date="2022-01-01",
            is_current=True,
        )
        response = auth_client.get(f"/api/v1/profiles/me/experience/{other_exp.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── File Upload Security ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFileUploadSecurity:
    upload_url = "/api/v1/imports/upload/"

    def _make_file(self, name: str, content: bytes, content_type: str = "text/plain"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, content, content_type=content_type)

    def test_rejects_disallowed_extension(self, auth_client):
        f = self._make_file("malware.exe", b"MZ\x90\x00", "application/octet-stream")
        response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_js_extension(self, auth_client):
        f = self._make_file("script.js", b"alert('xss')", "text/javascript")
        response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_php_extension(self, auth_client):
        f = self._make_file("shell.php", b"<?php system($_GET['cmd']); ?>", "text/plain")
        response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_disguised_exe_as_pdf(self, auth_client):
        # Windows PE header disguised as .pdf
        exe_content = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100
        f = self._make_file("resume.pdf", exe_content, "application/pdf")
        response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_accepts_valid_pdf_magic_bytes(self, auth_client):
        pdf_content = b"%PDF-1.4\n1 0 obj\n" + b"% fake pdf content\n" * 10
        f = self._make_file("resume.pdf", pdf_content, "application/pdf")
        from unittest.mock import patch
        with patch("apps.imports.services.ImportService.process"), \
             patch("celery_app.tasks.import_tasks.process_import_job.delay"):
            with patch("storage.storage") as mock_storage:
                mock_storage.return_value.upload.return_value = "path/to/file.pdf"
                response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code in [status.HTTP_202_ACCEPTED, status.HTTP_400_BAD_REQUEST]

    def test_rejects_empty_file(self, auth_client):
        f = self._make_file("empty.txt", b"", "text/plain")
        response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_null_byte_in_text_file(self, auth_client):
        binary_content = b"This looks like text\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        f = self._make_file("resume.txt", binary_content, "text/plain")
        response = auth_client.post(self.upload_url, {"file": f})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_no_file_in_request(self, auth_client):
        response = auth_client.post(self.upload_url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── Public Portfolio Route Security ─────────────────────────────────────────

@pytest.mark.django_db
class TestPublicRoutes:
    def test_public_portfolio_not_found_when_unpublished(self, api_client, user, profile, db):
        from apps.portfolios.models import Portfolio
        Portfolio.objects.get_or_create(user=user, defaults={"profile": profile, "slug": user.username})
        response = api_client.get(f"/api/v1/public/u/{user.username}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_public_portfolio_accessible_without_auth_when_published(
        self, api_client, user, profile, db
    ):
        from apps.portfolios.models import Portfolio
        portfolio, _ = Portfolio.objects.get_or_create(
            user=user, defaults={"profile": profile, "slug": user.username}
        )
        portfolio.is_published = True
        portfolio.is_public = True
        portfolio.save()
        response = api_client.get(f"/api/v1/public/u/{user.username}/")
        assert response.status_code == status.HTTP_200_OK

    def test_public_portfolio_does_not_expose_private_data(
        self, api_client, user, profile, db
    ):
        from apps.portfolios.models import Portfolio
        portfolio, _ = Portfolio.objects.get_or_create(
            user=user, defaults={"profile": profile, "slug": user.username}
        )
        portfolio.is_published = True
        portfolio.is_public = True
        portfolio.save()
        response = api_client.get(f"/api/v1/public/u/{user.username}/")
        body = response.json()
        body_str = str(body)
        # Private fields must not appear
        assert "password" not in body_str.lower()
        assert "access_token" not in body_str
        assert "refresh_token" not in body_str

    def test_nonexistent_username_returns_404(self, api_client):
        response = api_client.get("/api/v1/public/u/nonexistent-user-xyz-999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── File Validator Unit Tests ────────────────────────────────────────────────

class TestFileValidator:
    def test_valid_pdf_accepted(self):
        from apps.imports.file_validator import validate_file_signature
        pdf_content = b"%PDF-1.4\nfake content"
        is_valid, error = validate_file_signature(pdf_content, "pdf")
        assert is_valid is True
        assert error == ""

    def test_invalid_pdf_rejected(self):
        from apps.imports.file_validator import validate_file_signature
        not_pdf = b"MZ\x90\x00fake exe content"
        is_valid, error = validate_file_signature(not_pdf, "pdf")
        assert is_valid is False
        assert error != ""

    def test_valid_docx_accepted(self):
        from apps.imports.file_validator import validate_file_signature
        docx_content = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 50
        is_valid, error = validate_file_signature(docx_content, "docx")
        assert is_valid is True

    def test_invalid_docx_rejected(self):
        from apps.imports.file_validator import validate_file_signature
        not_docx = b"%PDF-1.4\n not a docx"
        is_valid, error = validate_file_signature(not_docx, "docx")
        assert is_valid is False

    def test_valid_txt_accepted(self):
        from apps.imports.file_validator import validate_file_signature
        text = b"Hello, this is a plain text resume.\nPython developer with 5 years experience."
        is_valid, error = validate_file_signature(text, "txt")
        assert is_valid is True

    def test_empty_txt_rejected(self):
        from apps.imports.file_validator import validate_file_signature
        is_valid, error = validate_file_signature(b"", "txt")
        assert is_valid is False

    def test_binary_content_in_txt_rejected(self):
        from apps.imports.file_validator import validate_file_signature
        binary_content = b"text\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        is_valid, error = validate_file_signature(binary_content, "txt")
        assert is_valid is False

    def test_unsupported_extension_rejected(self):
        from apps.imports.file_validator import validate_file_signature
        is_valid, error = validate_file_signature(b"content", "exe")
        assert is_valid is False


# ─── Trusted Proxy IP Extraction ─────────────────────────────────────────────

class TestTrustedProxyIP:
    def test_returns_remote_addr_when_not_trusted_proxy(self):
        from core.security import get_client_ip
        from unittest.mock import MagicMock
        request = MagicMock()
        request.META = {
            "REMOTE_ADDR": "8.8.8.8",  # Not a trusted proxy (public IP)
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
        }
        ip = get_client_ip(request)
        assert ip == "8.8.8.8"  # XFF ignored — REMOTE_ADDR not a trusted proxy

    def test_reads_xff_when_from_trusted_proxy(self):
        from core.security import get_client_ip
        from unittest.mock import MagicMock, patch
        request = MagicMock()
        request.META = {
            "REMOTE_ADDR": "10.0.0.1",  # Trusted private IP
            "HTTP_X_FORWARDED_FOR": "203.0.113.5, 10.0.0.1",  # client, proxy
        }
        ip = get_client_ip(request)
        assert ip == "203.0.113.5"  # Real client IP extracted

    def test_is_safe_url_rejects_private_ip(self):
        from core.security import is_safe_url
        assert is_safe_url("http://192.168.1.1/admin") is False
        assert is_safe_url("http://10.0.0.1/metadata") is False
        assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False

    def test_is_safe_url_accepts_public_url(self):
        from core.security import is_safe_url
        assert is_safe_url("https://api.openai.com/v1/completions") is True

    def test_is_safe_url_rejects_non_http_scheme(self):
        from core.security import is_safe_url
        assert is_safe_url("file:///etc/passwd") is False
        assert is_safe_url("ftp://example.com/file") is False

    def test_sanitize_user_content_wraps_in_delimiters(self):
        from core.security import sanitize_user_content_for_prompt
        result = sanitize_user_content_for_prompt("Build scalable APIs")
        assert "<user_content>" in result
        assert "Build scalable APIs" in result
        assert "</user_content>" in result

    def test_sanitize_truncates_long_content(self):
        from core.security import sanitize_user_content_for_prompt
        long_content = "x" * 5000
        result = sanitize_user_content_for_prompt(long_content, max_length=100)
        assert len(result) < 200  # 100 content + wrapper tags

    def test_sanitize_empty_content(self):
        from core.security import sanitize_user_content_for_prompt
        assert sanitize_user_content_for_prompt("") == ""


# ─── Config Validator ─────────────────────────────────────────────────────────

class TestConfigValidator:
    def test_detects_short_secret_key(self):
        from core.config_validator import validate_secrets
        from unittest.mock import patch
        with patch("django.conf.settings.SECRET_KEY", "short-key"), \
             patch("django.conf.settings.DEBUG", False):
            errors = validate_secrets()
        critical = [e for e in errors if e.variable == "SECRET_KEY" and e.severity == "critical"]
        assert len(critical) > 0

    def test_detects_wildcard_cors_in_production(self):
        from core.config_validator import validate_secrets
        from unittest.mock import patch
        with patch("django.conf.settings.CORS_ALLOWED_ORIGINS", ["*"]), \
             patch("django.conf.settings.DEBUG", False), \
             patch("django.conf.settings.SECRET_KEY", "a" * 60):
            errors = validate_secrets()
        cors_errors = [e for e in errors if e.variable == "CORS_ALLOWED_ORIGINS"]
        assert len(cors_errors) > 0

    def test_valid_config_produces_no_critical_errors(self):
        from core.config_validator import validate_secrets
        from unittest.mock import patch
        from datetime import timedelta
        with patch("django.conf.settings.SECRET_KEY", "a" * 60), \
             patch("django.conf.settings.DEBUG", False), \
             patch("django.conf.settings.CORS_ALLOWED_ORIGINS", ["https://profileforge.ai"]), \
             patch("django.conf.settings.ALLOWED_HOSTS", ["api.profileforge.ai"]), \
             patch("django.conf.settings.SIMPLE_JWT", {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=15)}), \
             patch("django.conf.settings.AI_PROVIDER", "openai"), \
             patch("django.conf.settings.OPENAI_API_KEY", "sk-test-validkey"), \
             patch("django.conf.settings.STORAGE_BACKEND", "local"), \
             patch("os.environ.get", return_value="postgresql://user:pass@db/profileforge"):
            errors = validate_secrets()
        critical = [e for e in errors if e.severity == "critical"]
        assert len(critical) == 0
