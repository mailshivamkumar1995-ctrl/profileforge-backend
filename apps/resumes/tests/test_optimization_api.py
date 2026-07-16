"""
API tests for POST /resumes/{id}/optimize/ and GET /resumes/{id}/optimization/.
"""
import pytest
from rest_framework import status


BASE = "/api/v1/resumes/"


def _optimize_url(resume_id):
    return f"{BASE}{resume_id}/optimize/"


def _optimization_url(resume_id):
    return f"{BASE}{resume_id}/optimization/"


# ── POST /resumes/{id}/optimize/ ──────────────────────────────────────────────

@pytest.mark.django_db
class TestOptimizeEndpoint:

    def test_requires_authentication(self, api_client, resume):
        response = api_client.post(_optimize_url(resume.id), {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_own_resume_returns_200(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other = Resume.objects.create(user=second_user, profile=profile,
                                      title="Other", status="active")
        response = auth_client.post(_optimize_url(other.id), {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_id_returns_404(self, auth_client):
        import uuid
        response = auth_client.post(_optimize_url(uuid.uuid4()), {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_has_success_envelope(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        assert "success" in response.json()
        assert response.json()["success"] is True

    def test_response_has_current_score(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "current_score" in data
        assert isinstance(data["current_score"], int)

    def test_response_has_potential_score(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "potential_score" in data
        assert isinstance(data["potential_score"], int)

    def test_response_has_sections_list(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "sections" in data
        assert isinstance(data["sections"], list)
        assert len(data["sections"]) > 0

    def test_response_has_keyword_gaps_list(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "keyword_gaps" in data
        assert isinstance(data["keyword_gaps"], list)

    def test_response_has_generated_at(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert "generated_at" in data
        assert data["generated_at"] != ""

    def test_empty_keyword_gaps_without_job_description(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert data["keyword_gaps"] == []
        assert data["job_description_provided"] is False

    def test_keyword_gaps_present_with_job_description(self, auth_client, resume):
        payload = {"job_description": "Need kubernetes terraform golang microservices experience."}
        response = auth_client.post(_optimize_url(resume.id), payload, format="json")
        data = response.json()["data"]
        assert data["job_description_provided"] is True

    def test_job_description_too_long_returns_400(self, auth_client, resume):
        payload = {"job_description": "x" * 3001}
        response = auth_client.post(_optimize_url(resume.id), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_updates_resume_ats_score_in_db(self, auth_client, resume):
        auth_client.post(_optimize_url(resume.id), {}, format="json")
        resume.refresh_from_db()
        assert resume.ats_score is not None

    def test_updates_resume_ats_analysis_in_db(self, auth_client, resume):
        auth_client.post(_optimize_url(resume.id), {}, format="json")
        resume.refresh_from_db()
        assert "optimization" in resume.ats_analysis

    def test_sections_sorted_by_opportunity_descending(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        sections = response.json()["data"]["sections"]
        opportunities = [s["opportunity"] for s in sections]
        assert opportunities == sorted(opportunities, reverse=True)

    def test_section_has_required_fields(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        section = response.json()["data"]["sections"][0]
        for field in ("name", "current_pts", "max_pts", "opportunity", "suggestions"):
            assert field in section

    def test_suggestion_has_required_fields(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        sections = response.json()["data"]["sections"]
        # Find first section with suggestions
        for sec in sections:
            if sec["suggestions"]:
                sug = sec["suggestions"][0]
                for field in ("id", "type", "priority", "guidance", "target", "original", "rewrite"):
                    assert field in sug
                break

    def test_potential_score_not_below_current(self, auth_client, resume):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        data = response.json()["data"]
        assert data["potential_score"] >= data["current_score"]

    def test_full_profile_has_higher_score_than_empty(self, auth_client, resume, full_profile):
        response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        score_with_full_profile = response.json()["data"]["current_score"]
        assert score_with_full_profile > 0


# ── GET /resumes/{id}/optimization/ ──────────────────────────────────────────

@pytest.mark.django_db
class TestOptimizationEndpoint:

    def test_requires_authentication(self, api_client, resume):
        response = api_client.get(_optimization_url(resume.id))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_200_null_before_optimize_is_run(self, auth_client, resume):
        response = auth_client.get(_optimization_url(resume.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] is None

    def test_returns_200_after_optimize(self, auth_client, resume):
        auth_client.post(_optimize_url(resume.id), {}, format="json")
        response = auth_client.get(_optimization_url(resume.id))
        assert response.status_code == status.HTTP_200_OK

    def test_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other = Resume.objects.create(user=second_user, profile=profile,
                                      title="Other", status="active")
        response = auth_client.get(_optimization_url(other.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_id_returns_404(self, auth_client):
        import uuid
        response = auth_client.get(_optimization_url(uuid.uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_has_success_envelope(self, auth_client, resume):
        auth_client.post(_optimize_url(resume.id), {}, format="json")
        response = auth_client.get(_optimization_url(resume.id))
        assert response.json()["success"] is True

    def test_retrieved_score_matches_post(self, auth_client, resume):
        post_response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        post_score = post_response.json()["data"]["current_score"]

        get_response = auth_client.get(_optimization_url(resume.id))
        get_score = get_response.json()["data"]["current_score"]

        assert get_score == post_score

    def test_retrieved_sections_match_post(self, auth_client, resume):
        post_response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        post_sections = len(post_response.json()["data"]["sections"])

        get_response = auth_client.get(_optimization_url(resume.id))
        get_sections = len(get_response.json()["data"]["sections"])

        assert get_sections == post_sections

    def test_retrieved_generated_at_matches_post(self, auth_client, resume):
        post_response = auth_client.post(_optimize_url(resume.id), {}, format="json")
        post_generated_at = post_response.json()["data"]["generated_at"]

        get_response = auth_client.get(_optimization_url(resume.id))
        get_generated_at = get_response.json()["data"]["generated_at"]

        assert get_generated_at == post_generated_at

    def test_job_description_provided_flag_persisted(self, auth_client, resume):
        auth_client.post(_optimize_url(resume.id),
                         {"job_description": "Need python kubernetes."}, format="json")
        response = auth_client.get(_optimization_url(resume.id))
        assert response.json()["data"]["job_description_provided"] is True

    def test_returns_200_null_with_malformed_optimization_data(self, auth_client, resume):
        resume.optimization_data = "invalid-json"
        resume.save()
        response = auth_client.get(_optimization_url(resume.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] is None
