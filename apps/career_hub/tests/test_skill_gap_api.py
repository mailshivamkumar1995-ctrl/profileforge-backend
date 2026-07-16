import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.career_hub.models import ResumeMatchScore
from apps.career_hub.services.skill_gap_service import (
    JobSkillGap,
    SkillGapEntry,
    SkillGapSummary,
)
from apps.career_hub.views import (
    JobSkillGapView,
    SkillGapRecommendationsView,
    SkillGapSummaryView,
)

_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_JOB_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
_SVC_MODULE = "apps.career_hub.views"

factory = APIRequestFactory()


def _make_user():
    user = MagicMock()
    user.id = _USER_ID
    user.is_authenticated = True
    return user


def _make_empty_summary() -> SkillGapSummary:
    return SkillGapSummary(
        career_readiness_score=None,
        total_jobs_scored=0,
        top_critical_gaps=[],
        top_moderate_gaps=[],
        top_soft_gaps=[],
        gap_counts={"critical": 0, "moderate": 0, "soft": 0, "low": 0},
    )


def _make_summary_with_data() -> SkillGapSummary:
    return SkillGapSummary(
        career_readiness_score=82,
        total_jobs_scored=10,
        top_critical_gaps=[
            SkillGapEntry("python", 8, display_name="Python", category="programming",
                          description="desc", resource_type="docs", url="https://python.org")
        ],
        top_moderate_gaps=[
            SkillGapEntry("microservices", 3)
        ],
        top_soft_gaps=[
            SkillGapEntry("leadership", 5, display_name="Leadership", category="soft_skill",
                          description="desc", resource_type="practice", url="https://example.com")
        ],
        gap_counts={"critical": 1, "moderate": 1, "soft": 1, "low": 2},
    )


def _make_job_gap() -> JobSkillGap:
    return JobSkillGap(
        job_id=str(_JOB_ID),
        job_title="Senior Engineer",
        job_company="Acme Corp",
        overall_score=Decimal("0.850"),
        score_display=85,
        critical_gaps=[
            {
                "token": "python",
                "display_name": "Python",
                "category": "programming",
                "description": "desc",
                "resource_type": "docs",
                "url": "https://python.org",
                "prerequisites": [],
            }
        ],
        moderate_gaps=[],
        soft_gaps=[],
        low_gaps=[],
    )


# ─── SkillGapSummaryView ───────────────────────────────────────────────────────

class TestSkillGapSummaryView:
    def setup_method(self):
        self.view = SkillGapSummaryView.as_view()

    def test_unauthenticated_returns_401(self):
        request = factory.get("/skill-gap-analysis/summary/")
        response = self.view(request)
        assert response.status_code == 401

    def test_authenticated_returns_200(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_empty_summary()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.status_code == 200

    def test_response_envelope_success_true(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_empty_summary()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        response.accepted_renderer = response.accepted_renderer or __import__(
            "rest_framework.renderers", fromlist=["JSONRenderer"]
        ).JSONRenderer()
        response.accepted_media_type = "application/json"
        response.renderer_context = {}
        response.render()
        assert response.data["success"] is True

    def test_response_data_has_career_readiness_score(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert "career_readiness_score" in response.data["data"]

    def test_career_readiness_score_matches_service(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"]["career_readiness_score"] == 82

    def test_null_crs_when_no_scores(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_empty_summary()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"]["career_readiness_score"] is None

    def test_total_jobs_scored_in_data(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"]["total_jobs_scored"] == 10

    def test_top_critical_gaps_in_data(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        data = response.data["data"]
        assert "top_critical_gaps" in data
        assert len(data["top_critical_gaps"]) == 1
        assert data["top_critical_gaps"][0]["token"] == "python"

    def test_gap_counts_in_data(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert "gap_counts" in response.data["data"]

    def test_calls_service_with_request_user(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_empty_summary()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            self.view(request)
        mock.assert_called_once_with(user)

    def test_top_soft_gaps_present(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert "top_soft_gaps" in response.data["data"]

    def test_top_moderate_gaps_present(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = _make_summary_with_data()
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert "top_moderate_gaps" in response.data["data"]


# ─── SkillGapRecommendationsView ───────────────────────────────────────────────

class TestSkillGapRecommendationsView:
    def setup_method(self):
        self.view = SkillGapRecommendationsView.as_view()

    def _make_recommendation(self, token="python", tier="critical", job_count=5):
        return {
            "token": token,
            "tier": tier,
            "job_count": job_count,
            "display_name": "Python",
            "category": "programming",
            "description": "desc",
            "resource_type": "docs",
            "url": "https://python.org",
            "prerequisites": [],
        }

    def test_unauthenticated_returns_401(self):
        request = factory.get("/skill-gap-analysis/recommendations/")
        response = self.view(request)
        assert response.status_code == 401

    def test_authenticated_returns_200(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.status_code == 200

    def test_default_tier_is_critical(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            self.view(request)
        _, kwargs = mock.call_args
        assert kwargs.get("tier") == "critical"

    def test_tier_moderate_param_accepted(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/", {"tier": "moderate"})
            force_authenticate(request, user=user)
            self.view(request)
        _, kwargs = mock.call_args
        assert kwargs.get("tier") == "moderate"

    def test_tier_soft_param_accepted(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/", {"tier": "soft"})
            force_authenticate(request, user=user)
            self.view(request)
        _, kwargs = mock.call_args
        assert kwargs.get("tier") == "soft"

    def test_tier_all_param_accepted(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/", {"tier": "all"})
            force_authenticate(request, user=user)
            self.view(request)
        _, kwargs = mock.call_args
        assert kwargs.get("tier") == "all"

    def test_invalid_tier_returns_400(self):
        user = _make_user()
        request = factory.get("/skill-gap-analysis/recommendations/", {"tier": "invalid"})
        force_authenticate(request, user=user)
        response = self.view(request)
        assert response.status_code == 400

    def test_response_data_is_list(self):
        user = _make_user()
        recs = [self._make_recommendation()]
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = recs
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert isinstance(response.data["data"], list)

    def test_empty_list_is_valid_response(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"] == []

    def test_recommendation_has_token(self):
        user = _make_user()
        recs = [self._make_recommendation(token="docker")]
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = recs
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"][0]["token"] == "docker"

    def test_recommendation_has_tier(self):
        user = _make_user()
        recs = [self._make_recommendation(tier="critical")]
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = recs
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"][0]["tier"] == "critical"

    def test_recommendation_has_job_count(self):
        user = _make_user()
        recs = [self._make_recommendation(job_count=7)]
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = recs
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        assert response.data["data"][0]["job_count"] == 7

    def test_calls_service_with_request_user(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = []
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            self.view(request)
        call_args = mock.call_args
        assert call_args[0][0] is user


# ─── JobSkillGapView ───────────────────────────────────────────────────────────

class TestJobSkillGapView:
    def setup_method(self):
        self.view = JobSkillGapView.as_view()

    def test_unauthenticated_returns_401(self):
        request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
        response = self.view(request, job_id=_JOB_ID)
        assert response.status_code == 401

    def test_authenticated_returns_200(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert response.status_code == 200

    def test_wrong_user_returns_404(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.side_effect = ResumeMatchScore.DoesNotExist()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert response.status_code == 404

    def test_nonexistent_job_returns_404(self):
        user = _make_user()
        other_id = uuid.uuid4()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.side_effect = ResumeMatchScore.DoesNotExist()
            request = factory.get(f"/skill-gap-analysis/jobs/{other_id}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=other_id)
        assert response.status_code == 404

    def test_job_id_in_response(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert str(response.data["data"]["job_id"]) == str(_JOB_ID)

    def test_job_title_in_response(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert response.data["data"]["job_title"] == "Senior Engineer"

    def test_score_display_in_response(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert response.data["data"]["score_display"] == 85

    def test_critical_gaps_in_response(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        data = response.data["data"]
        assert "critical_gaps" in data
        assert data["critical_gaps"][0]["token"] == "python"

    def test_all_four_gap_tiers_present(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        data = response.data["data"]
        assert "critical_gaps" in data
        assert "moderate_gaps" in data
        assert "soft_gaps" in data
        assert "low_gaps" in data

    def test_calls_service_with_user_and_job_id(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            self.view(request, job_id=_JOB_ID)
        mock.assert_called_once_with(user, _JOB_ID)

    def test_response_overall_score_present(self):
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = _make_job_gap()
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert "overall_score" in response.data["data"]

    def test_empty_critical_gaps_valid(self):
        user = _make_user()
        job_gap = _make_job_gap()
        job_gap.critical_gaps = []
        with patch(f"{_SVC_MODULE}.get_job_skill_gap") as mock:
            mock.return_value = job_gap
            request = factory.get(f"/skill-gap-analysis/jobs/{_JOB_ID}/")
            force_authenticate(request, user=user)
            response = self.view(request, job_id=_JOB_ID)
        assert response.data["data"]["critical_gaps"] == []


# ─── Serializer shape tests ────────────────────────────────────────────────────

class TestSkillGapSummarySerializerShape:
    def setup_method(self):
        self.view = SkillGapSummaryView.as_view()

    def _get_data(self, summary: SkillGapSummary) -> dict:
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_summary") as mock:
            mock.return_value = summary
            request = factory.get("/skill-gap-analysis/summary/")
            force_authenticate(request, user=user)
            response = self.view(request)
        return response.data["data"]

    def test_top_critical_gap_has_all_resource_fields(self):
        summary = _make_summary_with_data()
        data = self._get_data(summary)
        gap = data["top_critical_gaps"][0]
        for field in ["token", "job_count", "display_name", "category", "description",
                      "resource_type", "url", "prerequisites"]:
            assert field in gap, f"Missing field: {field}"

    def test_top_soft_gap_token_correct(self):
        summary = _make_summary_with_data()
        data = self._get_data(summary)
        assert data["top_soft_gaps"][0]["token"] == "leadership"

    def test_unknown_token_display_name_null(self):
        summary = SkillGapSummary(
            career_readiness_score=70,
            total_jobs_scored=3,
            top_critical_gaps=[SkillGapEntry("unknownxyz", 2)],
            top_moderate_gaps=[],
            top_soft_gaps=[],
            gap_counts={"critical": 1, "moderate": 0, "soft": 0, "low": 0},
        )
        data = self._get_data(summary)
        assert data["top_critical_gaps"][0]["display_name"] is None

    def test_prerequisites_is_list(self):
        summary = _make_summary_with_data()
        data = self._get_data(summary)
        assert isinstance(data["top_critical_gaps"][0]["prerequisites"], list)


class TestSkillGapRecommendationSerializerShape:
    def setup_method(self):
        self.view = SkillGapRecommendationsView.as_view()

    def _get_data(self, recommendations: list) -> list:
        user = _make_user()
        with patch(f"{_SVC_MODULE}.get_skill_gap_recommendations") as mock:
            mock.return_value = recommendations
            request = factory.get("/skill-gap-analysis/recommendations/")
            force_authenticate(request, user=user)
            response = self.view(request)
        return response.data["data"]

    def test_recommendation_serialized_with_all_fields(self):
        rec = {
            "token": "python",
            "tier": "critical",
            "job_count": 5,
            "display_name": "Python",
            "category": "programming",
            "description": "desc",
            "resource_type": "docs",
            "url": "https://python.org",
            "prerequisites": [],
        }
        data = self._get_data([rec])
        for field in ["token", "tier", "job_count", "display_name", "category",
                      "description", "resource_type", "url", "prerequisites"]:
            assert field in data[0], f"Missing field: {field}"

    def test_null_display_name_serialized(self):
        rec = {
            "token": "unknown",
            "tier": "critical",
            "job_count": 1,
            "display_name": None,
            "category": None,
            "description": None,
            "resource_type": None,
            "url": None,
            "prerequisites": [],
        }
        data = self._get_data([rec])
        assert data[0]["display_name"] is None

    def test_multiple_recommendations_returned(self):
        recs = [
            {"token": "python", "tier": "critical", "job_count": 5,
             "display_name": None, "category": None, "description": None,
             "resource_type": None, "url": None, "prerequisites": []},
            {"token": "docker", "tier": "critical", "job_count": 3,
             "display_name": None, "category": None, "description": None,
             "resource_type": None, "url": None, "prerequisites": []},
        ]
        data = self._get_data(recs)
        assert len(data) == 2
