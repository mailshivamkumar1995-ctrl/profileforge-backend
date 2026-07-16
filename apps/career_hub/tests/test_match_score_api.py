"""
Tests for P7-1B Resume Match Score API and service layer.

View tests use APIRequestFactory + force_authenticate + patch — no DB access.
Service tests patch ORM and engine calls directly.
Serializer tests use SimpleNamespace stubs — no DB access.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory, force_authenticate

from apps.career_hub.serializers import (
    MatchScoreBulkGenerateSerializer,
    MatchScoreGenerateSerializer,
    ResumeMatchScoreSerializer,
)
from apps.career_hub.services.match_service import (
    _build_scoring_inputs,
    _explanation_to_defaults,
    bulk_generate_match_scores,
    generate_match_score,
)
from apps.career_hub.services.match_scoring import MATCH_ALGORITHM_VERSION
from apps.career_hub.views import (
    JobMatchScoreView,
    MatchScoreBulkGenerateView,
    MatchScoreDetailView,
    MatchScoreGenerateView,
    MatchScoreListView,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

factory = APIRequestFactory()
_NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
_SCORE_ID = uuid.uuid4()
_JOB_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = _USER_ID
    user.is_authenticated = True
    return user


def _make_job_ns(**kwargs) -> SimpleNamespace:
    source = SimpleNamespace(id=uuid.uuid4(), name="adzuna", slug="adzuna")
    defaults = dict(
        id=_JOB_ID,
        source=source,
        title="Senior Python Developer",
        company="TechCorp",
        description="We need a Python Django developer.",
        apply_url="https://example.com/apply",
        city="Bangalore",
        work_type="hybrid",
        salary_min=None,
        salary_max=None,
        salary_currency="INR",
        posted_at=None,
        is_active=True,
        is_private=False,
        fetched_at=_NOW,
        deleted_at=None,
        technologies=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_score_ns(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=_SCORE_ID,
        job=_make_job_ns(),
        overall_score=Decimal("0.750"),
        skill_score=Decimal("0.8000"),
        experience_score=Decimal("0.7000"),
        keyword_score=Decimal("0.6500"),
        title_score=Decimal("0.9000"),
        education_score=Decimal("0.7000"),
        certification_score=Decimal("0.5000"),
        location_score=Decimal("1.0000"),
        salary_score=Decimal("0.5000"),
        skill_gaps={"critical": [], "moderate": [], "low": []},
        scoring_version=MATCH_ALGORITHM_VERSION,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_list_qs(scores: list) -> MagicMock:
    """Chain: filter→select_related→order_by→[optional filter] supporting pagination.

    order_by returns an inner mock with proper count/iter/getitem so that
    DRF's PageNumberPagination works. The inner mock's .filter() returns the
    raw scores list for the min_score secondary-filter path.
    """
    inner = MagicMock()
    inner.count.return_value = len(scores)
    inner.__len__ = MagicMock(return_value=len(scores))
    inner.__iter__ = MagicMock(side_effect=lambda: iter(scores))
    inner.__getitem__ = MagicMock(
        side_effect=lambda s: scores[s] if isinstance(s, int) else scores[s.start : s.stop]
    )
    # Secondary filter (min_score) returns the scores list — len() works on a list
    inner.filter.return_value = scores

    mock_qs = MagicMock()
    mock_qs.filter.return_value = mock_qs
    mock_qs.select_related.return_value = mock_qs
    mock_qs.order_by.return_value = inner
    return mock_qs


def _make_explanation_ns(**kwargs) -> SimpleNamespace:
    defaults = dict(
        total=Decimal("0.750"),
        breakdown={
            "skill": 0.8, "experience": 0.7, "keyword": 0.65,
            "title": 0.9, "education": 0.7, "certification": 0.5,
            "location": 1.0, "salary": 0.5,
        },
        skill_gaps={"critical": [], "moderate": [], "low": []},
        algorithm_version=MATCH_ALGORITHM_VERSION,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_profile_ns(**kwargs):
    defaults = dict(
        headline="Python Developer",
        professional_summary="Experienced developer",
        ats_keywords=["Python", "Django"],
        location={"city": "Bangalore"},
    )
    defaults.update(kwargs)
    profile = SimpleNamespace(**defaults)
    for attr in ("skills", "work_experiences", "educations", "certifications", "projects"):
        m = MagicMock()
        m.all.return_value = []
        setattr(profile, attr, m)
    return profile


# ─── MatchScoreListView — Authentication ──────────────────────────────────────

class TestMatchScoreListAuth:
    def test_returns_401_without_auth(self):
        request = factory.get("/api/v1/career-hub/match-scores/")
        response = MatchScoreListView.as_view()(request)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.filter.return_value = _make_list_qs([])
            request = factory.get("/api/v1/career-hub/match-scores/")
            force_authenticate(request, user=user)
            response = MatchScoreListView.as_view()(request)
        assert response.status_code == 200

    def test_response_envelope_is_success(self):
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.filter.return_value = _make_list_qs([])
            request = factory.get("/api/v1/career-hub/match-scores/")
            force_authenticate(request, user=user)
            response = MatchScoreListView.as_view()(request)
        assert response.data["success"] is True


# ─── MatchScoreListView — Response shape ─────────────────────────────────────

class TestMatchScoreListResponse:
    def _get_list(self, scores=None, params=None):
        user = _make_user()
        if scores is None:
            scores = []
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.filter.return_value = _make_list_qs(scores)
            request = factory.get("/api/v1/career-hub/match-scores/", params or {})
            force_authenticate(request, user=user)
            response = MatchScoreListView.as_view()(request)
            response.accepted_renderer = MagicMock()
            response.accepted_media_type = "application/json"
            response.renderer_context = {}
        return response

    def test_has_pagination(self):
        assert "pagination" in self._get_list().data

    def test_has_meta(self):
        assert "meta" in self._get_list().data

    def test_meta_has_version(self):
        assert self._get_list().data["meta"]["version"] == "v1"

    def test_meta_has_request_id(self):
        assert "request_id" in self._get_list().data["meta"]

    def test_meta_has_timestamp(self):
        assert "timestamp" in self._get_list().data["meta"]

    def test_empty_data(self):
        assert self._get_list().data["data"] == []

    def test_score_in_data(self):
        score = _make_score_ns()
        response = self._get_list(scores=[score])
        assert str(response.data["data"][0]["overall_score"]) == str(score.overall_score)

    def test_score_display_in_data(self):
        score = _make_score_ns(overall_score=Decimal("0.750"))
        response = self._get_list(scores=[score])
        assert response.data["data"][0]["score_display"] == 75

    def test_job_title_in_data(self):
        score = _make_score_ns()
        response = self._get_list(scores=[score])
        assert response.data["data"][0]["job"]["title"] == score.job.title

    def test_scoring_version_in_data(self):
        score = _make_score_ns()
        response = self._get_list(scores=[score])
        assert response.data["data"][0]["scoring_version"] == MATCH_ALGORITHM_VERSION

    def test_skill_gaps_in_data(self):
        score = _make_score_ns()
        response = self._get_list(scores=[score])
        assert "skill_gaps" in response.data["data"][0]


# ─── MatchScoreListView — BOLA ────────────────────────────────────────────────

class TestMatchScoreListBOLA:
    def test_filter_called_with_request_user(self):
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.filter.return_value = _make_list_qs([])
            request = factory.get("/api/v1/career-hub/match-scores/")
            force_authenticate(request, user=user)
            MatchScoreListView.as_view()(request)
        MockObj.filter.assert_called_once_with(user=user)

    def test_min_score_filter_accepted(self):
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.filter.return_value = _make_list_qs([])
            request = factory.get(
                "/api/v1/career-hub/match-scores/", {"min_score": "0.5"}
            )
            force_authenticate(request, user=user)
            response = MatchScoreListView.as_view()(request)
        assert response.status_code == 200

    def test_invalid_min_score_returns_400(self):
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.filter.return_value = _make_list_qs([])
            request = factory.get(
                "/api/v1/career-hub/match-scores/", {"min_score": "not-a-number"}
            )
            force_authenticate(request, user=user)
            response = MatchScoreListView.as_view()(request)
        assert response.status_code == 400


# ─── MatchScoreDetailView — Authentication ────────────────────────────────────

class TestMatchScoreDetailAuth:
    def test_returns_401_without_auth(self):
        request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
        response = MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
            force_authenticate(request, user=user)
            response = MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        assert response.status_code == 200


# ─── MatchScoreDetailView — BOLA ──────────────────────────────────────────────

class TestMatchScoreDetailBOLA:
    def test_get_called_with_user_filter(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
            force_authenticate(request, user=user)
            MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        MockObj.select_related.return_value.get.assert_called_once_with(
            pk=_SCORE_ID, user=user
        )

    def test_returns_404_for_other_users_score(self):
        from apps.career_hub.models import ResumeMatchScore
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.side_effect = (
                ResumeMatchScore.DoesNotExist
            )
            request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
            force_authenticate(request, user=user)
            response = MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        assert response.status_code == 404

    def test_detail_response_has_all_dimension_scores(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
            force_authenticate(request, user=user)
            response = MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        data = response.data["data"]
        for dim in [
            "skill_score", "experience_score", "keyword_score", "title_score",
            "education_score", "certification_score", "location_score", "salary_score",
        ]:
            assert dim in data

    def test_detail_response_has_score_display(self):
        user = _make_user()
        score = _make_score_ns(overall_score=Decimal("0.850"))
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
            force_authenticate(request, user=user)
            response = MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        assert response.data["data"]["score_display"] == 85

    def test_detail_response_has_success_envelope(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/match-scores/{_SCORE_ID}/")
            force_authenticate(request, user=user)
            response = MatchScoreDetailView.as_view()(request, pk=_SCORE_ID)
        assert response.data["success"] is True


# ─── MatchScoreGenerateView — Authentication ──────────────────────────────────

class TestMatchScoreGenerateAuth:
    def test_returns_401_without_auth(self):
        request = factory.post(
            "/api/v1/career-hub/match-scores/generate/",
            {"job_id": str(_JOB_ID)},
            format="json",
        )
        response = MatchScoreGenerateView.as_view()(request)
        assert response.status_code == 401

    def test_returns_400_for_missing_job_id(self):
        user = _make_user()
        request = factory.post(
            "/api/v1/career-hub/match-scores/generate/", {}, format="json"
        )
        force_authenticate(request, user=user)
        response = MatchScoreGenerateView.as_view()(request)
        assert response.status_code == 400


# ─── MatchScoreGenerateView — Success ─────────────────────────────────────────

class TestMatchScoreGenerateSuccess:
    def _post_generate(self, job_id=None, service_return=None):
        user = _make_user()
        job = _make_job_ns()
        score = service_return or _make_score_ns()
        jid = job_id or str(_JOB_ID)

        # Single patch for Job.objects — covers both serializer validate_job_id
        # and the view's job fetch (different chains: .filter vs .select_related)
        with patch("apps.career_hub.views.Job.objects") as MockJob, \
             patch("apps.career_hub.views.generate_match_score") as MockService:
            MockJob.filter.return_value.exists.return_value = True
            MockJob.select_related.return_value.get.return_value = job
            MockService.return_value = score

            request = factory.post(
                "/api/v1/career-hub/match-scores/generate/",
                {"job_id": jid},
                format="json",
            )
            force_authenticate(request, user=user)
            response = MatchScoreGenerateView.as_view()(request)

        return response, MockService, user, job

    def test_returns_201_on_success(self):
        response, *_ = self._post_generate()
        assert response.status_code == 201

    def test_response_has_success_envelope(self):
        response, *_ = self._post_generate()
        assert response.data["success"] is True

    def test_service_called_once_with_user_and_job(self):
        _, MockService, user, job = self._post_generate()
        MockService.assert_called_once_with(user, job)

    def test_returns_overall_score_in_response(self):
        response, *_ = self._post_generate()
        assert "overall_score" in response.data["data"]

    def test_returns_score_display_in_response(self):
        response, *_ = self._post_generate()
        assert "score_display" in response.data["data"]

    def test_returns_dimension_scores_in_response(self):
        response, *_ = self._post_generate()
        data = response.data["data"]
        for dim in [
            "skill_score", "experience_score", "keyword_score", "title_score",
            "education_score", "certification_score", "location_score", "salary_score",
        ]:
            assert dim in data

    def test_returns_skill_gaps_in_response(self):
        response, *_ = self._post_generate()
        assert "skill_gaps" in response.data["data"]

    def test_returns_scoring_version_in_response(self):
        response, *_ = self._post_generate()
        assert response.data["data"]["scoring_version"] == MATCH_ALGORITHM_VERSION

    def test_missing_profile_returns_400(self):
        from apps.profiles.models import UserProfile
        user = _make_user()
        job = _make_job_ns()

        with patch("apps.career_hub.views.Job.objects") as MockJob, \
             patch("apps.career_hub.views.generate_match_score") as MockService:
            MockJob.filter.return_value.exists.return_value = True
            MockJob.select_related.return_value.get.return_value = job
            MockService.side_effect = UserProfile.DoesNotExist

            request = factory.post(
                "/api/v1/career-hub/match-scores/generate/",
                {"job_id": str(_JOB_ID)},
                format="json",
            )
            force_authenticate(request, user=user)
            response = MatchScoreGenerateView.as_view()(request)

        assert response.status_code == 400

    def test_inactive_job_rejected_by_serializer(self):
        user = _make_user()
        with patch("apps.career_hub.views.Job.objects") as MockJob:
            MockJob.filter.return_value.exists.return_value = False
            request = factory.post(
                "/api/v1/career-hub/match-scores/generate/",
                {"job_id": str(_JOB_ID)},
                format="json",
            )
            force_authenticate(request, user=user)
            response = MatchScoreGenerateView.as_view()(request)
        assert response.status_code == 400


# ─── MatchScoreBulkGenerateView — Authentication ─────────────────────────────

class TestMatchScoreBulkGenerateAuth:
    def test_returns_401_without_auth(self):
        request = factory.post(
            "/api/v1/career-hub/match-scores/bulk-generate/",
            {"job_ids": [str(_JOB_ID)]},
            format="json",
        )
        response = MatchScoreBulkGenerateView.as_view()(request)
        assert response.status_code == 401

    def test_returns_400_for_empty_job_ids(self):
        user = _make_user()
        request = factory.post(
            "/api/v1/career-hub/match-scores/bulk-generate/",
            {"job_ids": []},
            format="json",
        )
        force_authenticate(request, user=user)
        response = MatchScoreBulkGenerateView.as_view()(request)
        assert response.status_code == 400

    def test_returns_400_for_missing_job_ids_field(self):
        user = _make_user()
        request = factory.post(
            "/api/v1/career-hub/match-scores/bulk-generate/", {}, format="json"
        )
        force_authenticate(request, user=user)
        response = MatchScoreBulkGenerateView.as_view()(request)
        assert response.status_code == 400


# ─── MatchScoreBulkGenerateView — Success ────────────────────────────────────

class TestMatchScoreBulkGenerateSuccess:
    def _post_bulk(self, job_ids=None, scores=None):
        user = _make_user()
        jids = job_ids or [str(_JOB_ID)]
        returned_scores = scores if scores is not None else [_make_score_ns()]

        with patch("apps.career_hub.views.bulk_generate_match_scores") as MockBulk:
            MockBulk.return_value = returned_scores
            request = factory.post(
                "/api/v1/career-hub/match-scores/bulk-generate/",
                {"job_ids": jids},
                format="json",
            )
            force_authenticate(request, user=user)
            response = MatchScoreBulkGenerateView.as_view()(request)
        return response, MockBulk

    def test_returns_200_on_success(self):
        response, _ = self._post_bulk()
        assert response.status_code == 200

    def test_response_has_success_envelope(self):
        response, _ = self._post_bulk()
        assert response.data["success"] is True

    def test_response_has_generated_count(self):
        response, _ = self._post_bulk()
        assert response.data["data"]["generated"] == 1

    def test_response_has_scores_list(self):
        response, _ = self._post_bulk()
        assert isinstance(response.data["data"]["scores"], list)

    def test_service_called_once(self):
        _, MockBulk = self._post_bulk()
        MockBulk.assert_called_once()

    def test_empty_result_returns_zero_generated(self):
        response, _ = self._post_bulk(scores=[])
        assert response.data["data"]["generated"] == 0

    def test_empty_result_returns_empty_scores_list(self):
        response, _ = self._post_bulk(scores=[])
        assert response.data["data"]["scores"] == []

    def test_missing_profile_returns_400(self):
        from apps.profiles.models import UserProfile
        user = _make_user()
        with patch("apps.career_hub.views.bulk_generate_match_scores") as MockBulk:
            MockBulk.side_effect = UserProfile.DoesNotExist
            request = factory.post(
                "/api/v1/career-hub/match-scores/bulk-generate/",
                {"job_ids": [str(_JOB_ID)]},
                format="json",
            )
            force_authenticate(request, user=user)
            response = MatchScoreBulkGenerateView.as_view()(request)
        assert response.status_code == 400

    def test_returns_400_for_more_than_50_job_ids(self):
        user = _make_user()
        too_many = [str(uuid.uuid4()) for _ in range(51)]
        request = factory.post(
            "/api/v1/career-hub/match-scores/bulk-generate/",
            {"job_ids": too_many},
            format="json",
        )
        force_authenticate(request, user=user)
        response = MatchScoreBulkGenerateView.as_view()(request)
        assert response.status_code == 400

    def test_multiple_scores_in_response(self):
        scores = [_make_score_ns(), _make_score_ns(id=uuid.uuid4())]
        response, _ = self._post_bulk(
            job_ids=[str(uuid.uuid4()), str(uuid.uuid4())], scores=scores
        )
        assert response.data["data"]["generated"] == 2
        assert len(response.data["data"]["scores"]) == 2

    def test_scores_have_overall_score(self):
        response, _ = self._post_bulk()
        assert "overall_score" in response.data["data"]["scores"][0]

    def test_scores_have_score_display(self):
        response, _ = self._post_bulk()
        assert "score_display" in response.data["data"]["scores"][0]


# ─── JobMatchScoreView ────────────────────────────────────────────────────────

class TestJobMatchScoreView:
    def test_returns_401_without_auth(self):
        request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
        response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert response.status_code == 401

    def test_returns_200_when_score_exists(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert response.status_code == 200

    def test_returns_404_when_no_score(self):
        from apps.career_hub.models import ResumeMatchScore
        user = _make_user()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.side_effect = (
                ResumeMatchScore.DoesNotExist
            )
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert response.status_code == 404

    def test_get_filtered_by_user_and_job(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        MockObj.select_related.return_value.get.assert_called_once_with(
            job_id=_JOB_ID, user=user
        )

    def test_response_includes_overall_score(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert "overall_score" in response.data["data"]

    def test_response_includes_score_display(self):
        user = _make_user()
        score = _make_score_ns(overall_score=Decimal("0.750"))
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert response.data["data"]["score_display"] == 75

    def test_response_includes_job_nested(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert isinstance(response.data["data"]["job"], dict)

    def test_response_has_success_envelope(self):
        user = _make_user()
        score = _make_score_ns()
        with patch("apps.career_hub.views.ResumeMatchScore.objects") as MockObj:
            MockObj.select_related.return_value.get.return_value = score
            request = factory.get(f"/api/v1/career-hub/jobs/{_JOB_ID}/match-score/")
            force_authenticate(request, user=user)
            response = JobMatchScoreView.as_view()(request, pk=_JOB_ID)
        assert response.data["success"] is True


# ─── ResumeMatchScoreSerializer ───────────────────────────────────────────────

class TestResumeMatchScoreSerializer:
    def test_includes_all_required_fields(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        expected = {
            "id", "job", "overall_score", "score_display",
            "skill_score", "experience_score", "keyword_score",
            "title_score", "education_score", "certification_score",
            "location_score", "salary_score",
            "skill_gaps", "scoring_version", "created_at", "updated_at",
        }
        assert expected.issubset(set(ser.data.keys()))

    def test_score_display_is_integer(self):
        score = _make_score_ns(overall_score=Decimal("0.750"))
        ser = ResumeMatchScoreSerializer(score)
        assert isinstance(ser.data["score_display"], int)

    def test_score_display_value_75(self):
        score = _make_score_ns(overall_score=Decimal("0.750"))
        ser = ResumeMatchScoreSerializer(score)
        assert ser.data["score_display"] == 75

    def test_score_display_rounds_half_up(self):
        score = _make_score_ns(overall_score=Decimal("0.856"))
        ser = ResumeMatchScoreSerializer(score)
        assert ser.data["score_display"] == 86

    def test_score_display_100_for_perfect(self):
        score = _make_score_ns(overall_score=Decimal("1.000"))
        ser = ResumeMatchScoreSerializer(score)
        assert ser.data["score_display"] == 100

    def test_score_display_0_for_zero(self):
        score = _make_score_ns(overall_score=Decimal("0.000"))
        ser = ResumeMatchScoreSerializer(score)
        assert ser.data["score_display"] == 0

    def test_job_is_nested_dict(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        assert isinstance(ser.data["job"], dict)
        assert "title" in ser.data["job"]

    def test_job_has_company(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        assert ser.data["job"]["company"] == "TechCorp"

    def test_skill_gaps_is_dict(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        assert isinstance(ser.data["skill_gaps"], dict)

    def test_scoring_version_is_algorithm_version(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        assert ser.data["scoring_version"] == MATCH_ALGORITHM_VERSION

    def test_overall_score_matches(self):
        score = _make_score_ns(overall_score=Decimal("0.823"))
        ser = ResumeMatchScoreSerializer(score)
        assert str(ser.data["overall_score"]) == "0.823"

    def test_skill_score_in_output(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        assert "skill_score" in ser.data

    def test_all_dimension_scores_present(self):
        score = _make_score_ns()
        ser = ResumeMatchScoreSerializer(score)
        for dim in [
            "skill_score", "experience_score", "keyword_score", "title_score",
            "education_score", "certification_score", "location_score", "salary_score",
        ]:
            assert dim in ser.data


# ─── MatchScoreGenerateSerializer ────────────────────────────────────────────

class TestMatchScoreGenerateSerializer:
    def test_valid_uuid_accepted(self):
        with patch("apps.career_hub.serializers.Job.objects") as MockJob:
            MockJob.filter.return_value.exists.return_value = True
            ser = MatchScoreGenerateSerializer(data={"job_id": str(_JOB_ID)})
            assert ser.is_valid(), ser.errors

    def test_invalid_uuid_rejected(self):
        ser = MatchScoreGenerateSerializer(data={"job_id": "not-a-uuid"})
        assert not ser.is_valid()
        assert "job_id" in ser.errors

    def test_missing_job_id_rejected(self):
        ser = MatchScoreGenerateSerializer(data={})
        assert not ser.is_valid()
        assert "job_id" in ser.errors

    def test_nonexistent_or_inactive_job_rejected(self):
        with patch("apps.career_hub.serializers.Job.objects") as MockJob:
            MockJob.filter.return_value.exists.return_value = False
            ser = MatchScoreGenerateSerializer(data={"job_id": str(_JOB_ID)})
            assert not ser.is_valid()
            assert "job_id" in ser.errors

    def test_active_job_passes_validation(self):
        with patch("apps.career_hub.serializers.Job.objects") as MockJob:
            MockJob.filter.return_value.exists.return_value = True
            ser = MatchScoreGenerateSerializer(data={"job_id": str(_JOB_ID)})
            assert ser.is_valid()
            assert ser.validated_data["job_id"] is not None

    def test_validated_data_has_uuid_type(self):
        with patch("apps.career_hub.serializers.Job.objects") as MockJob:
            MockJob.filter.return_value.exists.return_value = True
            ser = MatchScoreGenerateSerializer(data={"job_id": str(_JOB_ID)})
            ser.is_valid()
            assert isinstance(ser.validated_data["job_id"], uuid.UUID)


# ─── MatchScoreBulkGenerateSerializer ────────────────────────────────────────

class TestMatchScoreBulkGenerateSerializer:
    def test_valid_single_id_accepted(self):
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": [str(_JOB_ID)]})
        assert ser.is_valid(), ser.errors

    def test_empty_list_rejected(self):
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": []})
        assert not ser.is_valid()
        assert "job_ids" in ser.errors

    def test_more_than_50_rejected(self):
        ids = [str(uuid.uuid4()) for _ in range(51)]
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": ids})
        assert not ser.is_valid()

    def test_exactly_50_accepted(self):
        ids = [str(uuid.uuid4()) for _ in range(50)]
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": ids})
        assert ser.is_valid(), ser.errors

    def test_non_uuid_in_list_rejected(self):
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": ["not-a-uuid"]})
        assert not ser.is_valid()

    def test_missing_job_ids_field_rejected(self):
        ser = MatchScoreBulkGenerateSerializer(data={})
        assert not ser.is_valid()

    def test_validated_data_contains_uuid_objects(self):
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": [str(_JOB_ID)]})
        ser.is_valid()
        assert isinstance(ser.validated_data["job_ids"][0], uuid.UUID)

    def test_multiple_ids_accepted(self):
        ids = [str(uuid.uuid4()) for _ in range(5)]
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": ids})
        assert ser.is_valid(), ser.errors

    def test_exactly_1_accepted(self):
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": [str(_JOB_ID)]})
        assert ser.is_valid(), ser.errors

    def test_51_ids_rejected(self):
        ids = [str(uuid.uuid4()) for _ in range(51)]
        ser = MatchScoreBulkGenerateSerializer(data={"job_ids": ids})
        assert not ser.is_valid()
        assert "job_ids" in ser.errors


# ─── Service — _build_scoring_inputs ──────────────────────────────────────────

class TestBuildScoringInputs:
    def test_returns_headline(self):
        profile = _make_profile_ns(headline="ML Engineer")
        inputs = _build_scoring_inputs(profile)
        assert inputs["headline"] == "ML Engineer"

    def test_empty_headline_becomes_empty_string(self):
        profile = _make_profile_ns(headline=None)
        inputs = _build_scoring_inputs(profile)
        assert inputs["headline"] == ""

    def test_returns_professional_summary(self):
        profile = _make_profile_ns(professional_summary="Expert in Python")
        inputs = _build_scoring_inputs(profile)
        assert inputs["professional_summary"] == "Expert in Python"

    def test_empty_summary_becomes_empty_string(self):
        profile = _make_profile_ns(professional_summary=None)
        inputs = _build_scoring_inputs(profile)
        assert inputs["professional_summary"] == ""

    def test_returns_ats_keywords(self):
        profile = _make_profile_ns(ats_keywords=["Python", "AWS"])
        inputs = _build_scoring_inputs(profile)
        assert inputs["ats_keywords"] == ["Python", "AWS"]

    def test_null_ats_keywords_becomes_empty_list(self):
        profile = _make_profile_ns(ats_keywords=None)
        inputs = _build_scoring_inputs(profile)
        assert inputs["ats_keywords"] == []

    def test_extracts_city_from_location_dict(self):
        profile = _make_profile_ns(location={"city": "Bangalore"})
        inputs = _build_scoring_inputs(profile)
        assert inputs["user_city"] == "Bangalore"

    def test_empty_location_gives_empty_city(self):
        profile = _make_profile_ns(location={})
        inputs = _build_scoring_inputs(profile)
        assert inputs["user_city"] == ""

    def test_null_location_gives_empty_city(self):
        profile = _make_profile_ns(location=None)
        inputs = _build_scoring_inputs(profile)
        assert inputs["user_city"] == ""

    def test_expected_salary_always_none(self):
        profile = _make_profile_ns()
        inputs = _build_scoring_inputs(profile)
        assert inputs["expected_salary_min"] is None
        assert inputs["expected_salary_max"] is None

    def test_custom_section_texts_is_empty_list(self):
        profile = _make_profile_ns()
        inputs = _build_scoring_inputs(profile)
        assert inputs["custom_section_texts"] == []

    def test_all_required_keys_present(self):
        profile = _make_profile_ns()
        inputs = _build_scoring_inputs(profile)
        expected_keys = {
            "skills", "work_experiences", "educations", "certifications", "projects",
            "headline", "professional_summary", "ats_keywords", "target_role",
            "custom_section_texts", "user_city",
            "expected_salary_min", "expected_salary_max",
        }
        assert expected_keys == set(inputs.keys())

    def test_skills_are_list(self):
        profile = _make_profile_ns()
        inputs = _build_scoring_inputs(profile)
        assert isinstance(inputs["skills"], list)

    def test_missing_target_role_attribute_defaults_to_empty(self):
        profile = _make_profile_ns()
        # target_role is not set on the profile namespace
        inputs = _build_scoring_inputs(profile)
        assert inputs["target_role"] == ""


# ─── Service — _explanation_to_defaults ───────────────────────────────────────

class TestExplanationToDefaults:
    def test_all_dimension_fields_present(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        expected = {
            "overall_score", "skill_score", "experience_score", "keyword_score",
            "title_score", "education_score", "certification_score",
            "location_score", "salary_score", "skill_gaps", "scoring_version",
        }
        assert expected == set(defaults.keys())

    def test_overall_score_is_explanation_total(self):
        expl = _make_explanation_ns(total=Decimal("0.823"))
        defaults = _explanation_to_defaults(expl)
        assert defaults["overall_score"] == Decimal("0.823")

    def test_scoring_version_is_algorithm_version(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        assert defaults["scoring_version"] == MATCH_ALGORITHM_VERSION

    def test_skill_score_is_decimal(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        assert isinstance(defaults["skill_score"], Decimal)

    def test_experience_score_is_decimal(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        assert isinstance(defaults["experience_score"], Decimal)

    def test_keyword_score_is_decimal(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        assert isinstance(defaults["keyword_score"], Decimal)

    def test_location_score_is_decimal(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        assert isinstance(defaults["location_score"], Decimal)

    def test_salary_score_is_decimal(self):
        expl = _make_explanation_ns()
        defaults = _explanation_to_defaults(expl)
        assert isinstance(defaults["salary_score"], Decimal)

    def test_skill_gaps_passed_through(self):
        gaps = {"critical": ["python"], "moderate": [], "low": []}
        expl = _make_explanation_ns(skill_gaps=gaps)
        defaults = _explanation_to_defaults(expl)
        assert defaults["skill_gaps"] == gaps

    def test_individual_scores_match_breakdown(self):
        bd = {
            "skill": 0.9, "experience": 0.8, "keyword": 0.7,
            "title": 0.6, "education": 0.5, "certification": 0.4,
            "location": 0.3, "salary": 0.2,
        }
        expl = _make_explanation_ns(breakdown=bd)
        defaults = _explanation_to_defaults(expl)
        assert defaults["skill_score"] == Decimal("0.9")
        assert defaults["salary_score"] == Decimal("0.2")


# ─── Service — generate_match_score (mocked ORM) ─────────────────────────────

class TestGenerateMatchScore:
    def _run(self):
        user = _make_user()
        job = _make_job_ns()
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score = MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj:
            MockFetch.return_value = profile
            MockEngine.return_value = expl
            MockObj.update_or_create.return_value = (score, True)
            result = generate_match_score(user, job)
        return result, score, MockObj, MockEngine, user, job

    def test_calls_update_or_create(self):
        _, _, MockObj, *_ = self._run()
        MockObj.update_or_create.assert_called_once()

    def test_update_or_create_called_with_user_and_job(self):
        _, _, MockObj, _, user, job = self._run()
        call_kwargs = MockObj.update_or_create.call_args.kwargs
        assert call_kwargs["user"] is user
        assert call_kwargs["job"] is job

    def test_attaches_job_to_returned_score(self):
        _, score, _, _, _, job = self._run()
        assert score.job is job

    def test_engine_called_with_job(self):
        _, _, _, MockEngine, _, job = self._run()
        MockEngine.assert_called_once()
        assert MockEngine.call_args.kwargs["job"] is job

    def test_returns_score_from_update_or_create(self):
        result, score, *_ = self._run()
        assert result is score

    def test_profile_fetched_once(self):
        user = _make_user()
        job = _make_job_ns()
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score = MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj:
            MockFetch.return_value = profile
            MockEngine.return_value = expl
            MockObj.update_or_create.return_value = (score, True)
            generate_match_score(user, job)
        MockFetch.assert_called_once_with(user)


# ─── Service — bulk_generate_match_scores (mocked ORM) ───────────────────────

class TestBulkGenerateMatchScores:
    def test_empty_job_ids_returns_empty_list(self):
        result = bulk_generate_match_scores(_make_user(), [])
        assert result == []

    def test_skips_nonexistent_jobs(self):
        user = _make_user()
        profile = _make_profile_ns()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.Job.objects") as MockJob, \
             patch("apps.career_hub.services.match_service.transaction.atomic"):
            MockFetch.return_value = profile
            MockJob.filter.return_value = []
            result = bulk_generate_match_scores(user, [str(uuid.uuid4())])
        assert result == []

    def test_returns_scores_for_valid_jobs(self):
        user = _make_user()
        job = _make_job_ns()
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score = MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.Job.objects") as MockJob, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj, \
             patch("apps.career_hub.services.match_service.transaction.atomic"):
            MockFetch.return_value = profile
            MockJob.filter.return_value = [job]
            MockEngine.return_value = expl
            MockObj.update_or_create.return_value = (score, True)
            result = bulk_generate_match_scores(user, [str(_JOB_ID)])
        assert len(result) == 1
        assert result[0] is score

    def test_idempotent_update_or_create_called(self):
        user = _make_user()
        job = _make_job_ns()
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score = MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.Job.objects") as MockJob, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj, \
             patch("apps.career_hub.services.match_service.transaction.atomic"):
            MockFetch.return_value = profile
            MockJob.filter.return_value = [job]
            MockEngine.return_value = expl
            MockObj.update_or_create.return_value = (score, True)
            bulk_generate_match_scores(user, [str(_JOB_ID)])
        MockObj.update_or_create.assert_called_once()

    def test_job_attached_to_score_after_bulk(self):
        user = _make_user()
        job = _make_job_ns()
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score = MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.Job.objects") as MockJob, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj, \
             patch("apps.career_hub.services.match_service.transaction.atomic"):
            MockFetch.return_value = profile
            MockJob.filter.return_value = [job]
            MockEngine.return_value = expl
            MockObj.update_or_create.return_value = (score, True)
            bulk_generate_match_scores(user, [str(_JOB_ID)])
        assert score.job is job

    def test_multiple_jobs_produce_multiple_scores(self):
        user = _make_user()
        job1 = _make_job_ns()
        job2 = _make_job_ns(id=uuid.uuid4())
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score1, score2 = MagicMock(), MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.Job.objects") as MockJob, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj, \
             patch("apps.career_hub.services.match_service.transaction.atomic"):
            MockFetch.return_value = profile
            MockJob.filter.return_value = [job1, job2]
            MockEngine.return_value = expl
            MockObj.update_or_create.side_effect = [(score1, True), (score2, True)]
            result = bulk_generate_match_scores(user, [str(job1.id), str(job2.id)])
        assert len(result) == 2

    def test_profile_fetched_once_for_bulk(self):
        user = _make_user()
        job = _make_job_ns()
        profile = _make_profile_ns()
        expl = _make_explanation_ns()
        score = MagicMock()
        with patch("apps.career_hub.services.match_service._fetch_profile") as MockFetch, \
             patch("apps.career_hub.services.match_service.Job.objects") as MockJob, \
             patch("apps.career_hub.services.match_service.compute_resume_match_score") as MockEngine, \
             patch("apps.career_hub.services.match_service.ResumeMatchScore.objects") as MockObj, \
             patch("apps.career_hub.services.match_service.transaction.atomic"):
            MockFetch.return_value = profile
            MockJob.filter.return_value = [job]
            MockEngine.return_value = expl
            MockObj.update_or_create.return_value = (score, True)
            bulk_generate_match_scores(user, [str(_JOB_ID)])
        MockFetch.assert_called_once_with(user)
