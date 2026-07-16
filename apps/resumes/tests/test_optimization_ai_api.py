"""
API tests for POST /resumes/{id}/optimize-ai/ and GET /resumes/{id}/ai-optimization/.

All AI calls are mocked — no real provider calls are made.
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.ai_engine.providers.base import AIResponse


BASE = "/api/v1/resumes/"


def _optimize_ai_url(resume_id):
    return f"{BASE}{resume_id}/optimize-ai/"


def _ai_optimization_url(resume_id):
    return f"{BASE}{resume_id}/ai-optimization/"


def _make_ai_response(content: str = "AI generated rewrite") -> AIResponse:
    return AIResponse(
        content=content,
        model="gpt-4o-mini",
        prompt_tokens=80,
        completion_tokens=40,
        total_tokens=120,
    )


@contextmanager
def _mock_ai(content: str = "AI generated rewrite"):
    provider = MagicMock()
    provider.complete.return_value = _make_ai_response(content)
    provider.provider_name = "openai"
    provider.model_name = "gpt-4o-mini"
    with patch("apps.ai_engine.services.get_ai_provider", return_value=provider):
        yield


def _make_weak_experience(profile, company="TestCo", job_title="Developer"):
    from apps.profiles.models import WorkExperience
    return WorkExperience.objects.create(
        profile=profile,
        company_name=company,
        job_title=job_title,
        employment_type="full_time",
        start_date="2021-01-01",
        is_current=True,
        achievements=["worked on things", "helped the team"],
        technologies=[],
        display_order=99,
    )


# ── POST /resumes/{id}/optimize-ai/ ──────────────────────────────────────────

@pytest.mark.django_db
class TestOptimizeAIEndpoint:

    def test_requires_authentication(self, api_client, resume):
        response = api_client.post(_optimize_ai_url(resume.id), {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_own_resume_returns_200(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other = Resume.objects.create(
            user=second_user, profile=profile, title="Other", status="active"
        )
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(other.id), {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_id_returns_404(self, auth_client):
        import uuid
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(uuid.uuid4()), {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_has_success_envelope(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        assert response.json()["success"] is True

    def test_response_has_current_score(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "current_score" in data
        assert isinstance(data["current_score"], int)

    def test_response_has_sections_list(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "sections" in data
        assert isinstance(data["sections"], list)
        assert len(data["sections"]) > 0

    def test_response_has_potential_score(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "potential_score" in data
        assert data["potential_score"] >= data["current_score"]

    def test_suggestion_has_rewrite_field(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        sections = response.json()["data"]["sections"]
        for sec in sections:
            for sug in sec["suggestions"]:
                assert "rewrite" in sug

    def test_strengthen_bullet_gets_ai_rewrite(self, auth_client, resume, db):
        _make_weak_experience(resume.user.profile)
        rewrite_text = "Engineered 3 microservices cutting latency by 40%"
        with _mock_ai(rewrite_text):
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        sections = response.json()["data"]["sections"]
        all_sugs = [s for sec in sections for s in sec["suggestions"]]
        bullet_sugs = [s for s in all_sugs if s["type"] == "STRENGTHEN_BULLET"]
        assert len(bullet_sugs) > 0
        assert all(s["rewrite"] == rewrite_text for s in bullet_sugs)

    def test_job_description_too_long_returns_400(self, auth_client, resume):
        payload = {"job_description": "x" * 3001}
        response = auth_client.post(_optimize_ai_url(resume.id), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_job_description_provided_sets_flag(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(
                _optimize_ai_url(resume.id),
                {"job_description": "Need kubernetes terraform golang."},
                format="json",
            )
        assert response.json()["data"]["job_description_provided"] is True

    def test_empty_body_accepted(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_persists_ai_optimization_key(self, auth_client, resume):
        with _mock_ai():
            auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        resume.refresh_from_db()
        assert "ai_optimization" in resume.ats_analysis

    def test_persists_base_optimization_key(self, auth_client, resume):
        with _mock_ai():
            auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        resume.refresh_from_db()
        assert "optimization" in resume.ats_analysis

    def test_ai_failure_still_returns_200(self, auth_client, resume):
        with patch("apps.ai_engine.services.get_ai_provider") as mock_prov:
            mock_prov.return_value.complete.side_effect = Exception("Provider down")
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_ai_failure_rewrites_are_null(self, auth_client, resume, db):
        _make_weak_experience(resume.user.profile)
        with patch("apps.ai_engine.services.get_ai_provider") as mock_prov:
            mock_prov.return_value.complete.side_effect = Exception("Provider down")
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        sections = response.json()["data"]["sections"]
        all_sugs = [s for sec in sections for s in sec["suggestions"]]
        bullet_sugs = [s for s in all_sugs if s["type"] == "STRENGTHEN_BULLET"]
        assert len(bullet_sugs) > 0
        assert all(s["rewrite"] is None for s in bullet_sugs)

    def test_deterministic_optimize_endpoint_still_works(self, auth_client, resume):
        response = auth_client.post(f"{BASE}{resume.id}/optimize/", {}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_sections_sorted_by_opportunity_descending(self, auth_client, resume):
        with _mock_ai():
            response = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        sections = response.json()["data"]["sections"]
        opportunities = [s["opportunity"] for s in sections]
        assert opportunities == sorted(opportunities, reverse=True)


# ── GET /resumes/{id}/ai-optimization/ ───────────────────────────────────────

@pytest.mark.django_db
class TestAIOptimizationEndpoint:

    def test_requires_authentication(self, api_client, resume):
        response = api_client.get(_ai_optimization_url(resume.id))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_200_null_before_optimize_ai_is_run(self, auth_client, resume):
        response = auth_client.get(_ai_optimization_url(resume.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] is None

    def test_returns_200_after_optimize_ai(self, auth_client, resume):
        with _mock_ai():
            auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        response = auth_client.get(_ai_optimization_url(resume.id))
        assert response.status_code == status.HTTP_200_OK

    def test_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other = Resume.objects.create(
            user=second_user, profile=profile, title="Other", status="active"
        )
        response = auth_client.get(_ai_optimization_url(other.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_id_returns_404(self, auth_client):
        import uuid
        response = auth_client.get(_ai_optimization_url(uuid.uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_has_success_envelope(self, auth_client, resume):
        with _mock_ai():
            auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        response = auth_client.get(_ai_optimization_url(resume.id))
        assert response.json()["success"] is True

    def test_score_matches_post(self, auth_client, resume):
        with _mock_ai():
            post_resp = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        post_score = post_resp.json()["data"]["current_score"]

        get_resp = auth_client.get(_ai_optimization_url(resume.id))
        get_score = get_resp.json()["data"]["current_score"]
        assert get_score == post_score

    def test_sections_count_matches_post(self, auth_client, resume):
        with _mock_ai():
            post_resp = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        post_sections = len(post_resp.json()["data"]["sections"])

        get_resp = auth_client.get(_ai_optimization_url(resume.id))
        get_sections = len(get_resp.json()["data"]["sections"])
        assert get_sections == post_sections

    def test_generated_at_matches_post(self, auth_client, resume):
        with _mock_ai():
            post_resp = auth_client.post(_optimize_ai_url(resume.id), {}, format="json")
        post_ts = post_resp.json()["data"]["generated_at"]

        get_resp = auth_client.get(_ai_optimization_url(resume.id))
        get_ts = get_resp.json()["data"]["generated_at"]
        assert get_ts == post_ts

    def test_malformed_stored_data_returns_200_null(self, auth_client, resume):
        resume.ats_analysis = {"ai_optimization": "not-a-dict"}
        resume.save(update_fields=["ats_analysis"])
        response = auth_client.get(_ai_optimization_url(resume.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] is None
