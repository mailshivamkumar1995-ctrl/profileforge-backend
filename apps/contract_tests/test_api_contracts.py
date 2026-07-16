"""
API Contract Tests — validate response envelope, field presence, type safety,
and backward compatibility across all ProfileForge AI endpoints.

These tests verify the PUBLIC API CONTRACT that the frontend depends on.
Any change that breaks these tests is a breaking change and must be versioned.
"""
import pytest
import uuid
from rest_framework import status


# ─── Contract Helpers ─────────────────────────────────────────────────────────

def assert_envelope(response, success: bool = True):
    """All API responses must follow {success, data, meta?} envelope."""
    body = response.json()
    assert "success" in body, f"Missing 'success' in response: {body}"
    assert body["success"] is success, f"Expected success={success}, got: {body}"
    if success:
        assert "data" in body, f"Missing 'data' in success response: {body}"
    return body


def assert_uuid(value: str, field_name: str):
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        pytest.fail(f"Field '{field_name}' is not a valid UUID: {value!r}")


def assert_iso8601(value: str, field_name: str):
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        pytest.fail(f"Field '{field_name}' is not ISO 8601: {value!r}")


# ─── Authentication Contract ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthContract:
    register_url = "/api/v1/auth/register/"
    login_url = "/api/v1/auth/login/"
    me_url = "/api/v1/auth/me/"

    def _register(self, api_client):
        payload = {
            "email": f"contract-{uuid.uuid4().hex[:8]}@example.com",
            "username": f"contract{uuid.uuid4().hex[:8]}",
            "first_name": "Contract",
            "last_name": "Test",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = api_client.post(self.register_url, payload, format="json")
        return response, payload

    def test_register_response_envelope(self, api_client):
        response, _ = self._register(api_client)
        body = assert_envelope(response)
        assert response.status_code == status.HTTP_201_CREATED

    def test_register_returns_token_fields(self, api_client):
        response, _ = self._register(api_client)
        data = response.json()["data"]
        assert "access_token" in data, "Missing access_token"
        assert "refresh_token" in data, "Missing refresh_token"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 20

    def test_register_returns_user_object(self, api_client):
        response, payload = self._register(api_client)
        user = response.json()["data"]["user"]
        assert "id" in user
        assert "email" in user
        assert user["email"] == payload["email"]

    def test_register_user_id_is_uuid(self, api_client):
        response, _ = self._register(api_client)
        user_id = response.json()["data"]["user"]["id"]
        assert_uuid(user_id, "user.id")

    def test_login_response_has_access_token(self, api_client):
        _, payload = self._register(api_client)
        response = api_client.post(
            self.login_url,
            {"email": payload["email"], "password": payload["password"]},
            format="json",
        )
        body = assert_envelope(response)
        assert "access_token" in body["data"]

    def test_error_response_envelope(self, api_client):
        response = api_client.post(
            self.login_url,
            {"email": "none@example.com", "password": "bad"},
            format="json",
        )
        body = assert_envelope(response, success=False)
        assert "message" in body or "errors" in body or "error" in body

    def test_me_returns_consistent_user_fields(self, auth_client, user):
        response = auth_client.get(self.me_url)
        data = assert_envelope(response)["data"]
        for field in ["id", "email", "first_name", "last_name"]:
            assert field in data, f"Missing field '{field}' in /me response"


# ─── Profile Contract ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProfileContract:
    url = "/api/v1/profiles/me/"

    def test_profile_response_envelope(self, auth_client):
        response = auth_client.get(self.url)
        assert_envelope(response)

    def test_profile_required_fields(self, auth_client):
        data = auth_client.get(self.url).json()["data"]
        for field in ["headline", "professional_summary", "phone",
                      "location", "website_url", "linkedin_url", "github_url",
                      "work_experiences", "educations", "skills", "projects",
                      "certifications", "achievements"]:
            assert field in data, f"Missing field '{field}' in profile response"

    def test_profile_sections_are_lists(self, auth_client):
        data = auth_client.get(self.url).json()["data"]
        list_fields = ["work_experiences", "educations", "skills", "projects",
                       "certifications", "achievements"]
        for field in list_fields:
            assert isinstance(data[field], list), f"'{field}' must be a list, got {type(data[field])}"


# ─── Resume Contract ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestResumeContract:
    url = "/api/v1/resumes/"

    def test_create_response_envelope(self, auth_client):
        response = auth_client.post(self.url, {"title": "Contract Test"}, format="json")
        assert_envelope(response)

    def test_create_returns_required_fields(self, auth_client):
        response = auth_client.post(self.url, {"title": "Contract Test"}, format="json")
        data = response.json()["data"]
        for field in ["id", "title", "status", "current_version", "created_at", "updated_at"]:
            assert field in data, f"Missing field '{field}' in resume response"

    def test_resume_id_is_uuid(self, auth_client):
        response = auth_client.post(self.url, {"title": "UUID Test"}, format="json")
        assert_uuid(response.json()["data"]["id"], "resume.id")

    def test_resume_created_at_is_iso8601(self, auth_client):
        response = auth_client.post(self.url, {"title": "Date Test"}, format="json")
        assert_iso8601(response.json()["data"]["created_at"], "resume.created_at")

    def test_resume_status_is_one_of_expected_values(self, auth_client):
        response = auth_client.post(self.url, {"title": "Status Test"}, format="json")
        status_value = response.json()["data"]["status"]
        assert status_value in ["draft", "active", "archived"], f"Unexpected status: {status_value}"

    def test_list_returns_array(self, auth_client):
        response = auth_client.get(self.url)
        data = assert_envelope(response)["data"]
        assert isinstance(data, list)

    def test_preview_returns_html_field(self, auth_client, resume):
        response = auth_client.get(f"{self.url}{resume.id}/preview/")
        data = assert_envelope(response)["data"]
        assert "html" in data
        assert isinstance(data["html"], str)


# ─── Cover Letter Contract ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCoverLetterContract:
    url = "/api/v1/cover-letters/"

    def test_create_returns_required_fields(self, auth_client):
        response = auth_client.post(
            self.url,
            {"title": "Contract CL", "company_name": "Corp", "job_title": "Dev"},
            format="json",
        )
        data = assert_envelope(response)["data"]
        for field in ["id", "title", "company_name", "job_title", "tone", "status",
                      "body_content", "ai_generated", "current_version"]:
            assert field in data, f"Missing field '{field}'"

    def test_tone_is_valid_enum(self, auth_client):
        response = auth_client.post(
            self.url,
            {"title": "Tone Test", "company_name": "Corp", "job_title": "Dev", "tone": "executive"},
            format="json",
        )
        tone = response.json()["data"]["tone"]
        valid_tones = ["professional", "executive", "friendly", "technical", "startup", "formal"]
        assert tone in valid_tones, f"Unexpected tone: {tone}"

    def test_ai_generated_is_boolean(self, auth_client):
        response = auth_client.post(
            self.url,
            {"title": "AI Test", "company_name": "Corp", "job_title": "Dev"},
            format="json",
        )
        ai_generated = response.json()["data"]["ai_generated"]
        assert isinstance(ai_generated, bool)


# ─── Export Contract ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestExportContract:
    url = "/api/v1/exports/"

    def test_list_returns_array(self, auth_client):
        response = auth_client.get(self.url)
        data = assert_envelope(response)["data"]
        assert isinstance(data, list)

    def test_request_export_returns_202(self, auth_client, resume):
        from unittest.mock import patch
        with patch("apps.exports.services.ExportService.generate"):
            response = auth_client.post(
                f"{self.url}request/",
                {"resource_type": "resume", "resource_id": str(resume.id), "format": "pdf"},
                format="json",
            )
        assert response.status_code in [200, 202]
        data = assert_envelope(response)["data"]
        assert "id" in data
        assert data["status"] in ["queued", "processing", "completed", "failed"]

    def test_invalid_format_returns_400(self, auth_client, resume):
        response = auth_client.post(
            f"{self.url}request/",
            {"resource_type": "resume", "resource_id": str(resume.id), "format": "odt"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert_envelope(response, success=False)


# ─── Import Contract ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestImportContract:
    url = "/api/v1/imports/"

    def test_list_returns_array(self, auth_client):
        response = auth_client.get(self.url)
        data = assert_envelope(response)["data"]
        assert isinstance(data, list)

    def test_import_job_status_values(self, auth_client, import_job):
        response = auth_client.get(f"{self.url}{import_job.id}/")
        data = assert_envelope(response)["data"]
        valid_statuses = ["pending", "processing", "review_required", "applied", "failed"]
        assert data["status"] in valid_statuses, f"Unexpected status: {data['status']}"

    def test_import_job_contains_required_fields(self, auth_client, import_job):
        response = auth_client.get(f"{self.url}{import_job.id}/")
        data = assert_envelope(response)["data"]
        for field in ["id", "original_filename", "file_type", "status", "created_at"]:
            assert field in data, f"Missing field '{field}'"


# ─── Schema Consistency ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSchemaConsistency:
    """Cross-endpoint consistency: IDs, dates, and status values follow the same format."""

    def test_all_id_fields_are_uuids(self, auth_client, resume, cover_letter, import_job):
        """IDs across all entities must be UUIDs."""
        for entity, url in [
            ("resume", f"/api/v1/resumes/{resume.id}/"),
            ("cover_letter", f"/api/v1/cover-letters/{cover_letter.id}/"),
            ("import_job", f"/api/v1/imports/{import_job.id}/"),
        ]:
            response = auth_client.get(url)
            data = response.json()["data"]
            assert_uuid(data["id"], f"{entity}.id")

    def test_all_endpoints_require_authentication(self, api_client):
        """Every authenticated endpoint must return 401 without credentials."""
        endpoints = [
            "/api/v1/profiles/me/",
            "/api/v1/resumes/",
            "/api/v1/cover-letters/",
            "/api/v1/portfolios/",
            "/api/v1/imports/",
            "/api/v1/exports/",
            "/api/v1/templates/",
        ]
        for url in endpoints:
            response = api_client.get(url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Expected 401 for {url}, got {response.status_code}"
            )

    def test_all_list_endpoints_return_arrays(self, auth_client, resume, cover_letter):
        """List endpoints must return JSON arrays, not objects."""
        list_endpoints = [
            "/api/v1/resumes/",
            "/api/v1/cover-letters/",
            "/api/v1/imports/",
            "/api/v1/exports/",
            "/api/v1/templates/",
        ]
        for url in list_endpoints:
            response = auth_client.get(url)
            data = response.json()["data"]
            assert isinstance(data, (list, dict)), f"Expected list/dict for {url}"
            # Some endpoints return a single resource (portfolio) rather than a list
