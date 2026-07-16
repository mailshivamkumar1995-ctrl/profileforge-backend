"""
API tests for Career Hub Recommendation endpoints.

GET    /api/v1/career-hub/recommendations/              — RecommendationListView
GET    /api/v1/career-hub/recommendations/{id}/         — RecommendationDetailView
PATCH  /api/v1/career-hub/recommendations/{id}/dismiss/ — RecommendationDismissView

Authentication: force_authenticate bypasses JWT.
ORM calls are mocked — no database access.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.career_hub.models import JobRecommendation
from apps.career_hub.views import (
    RecommendationDetailView,
    RecommendationDismissView,
    RecommendationListView,
)
from rest_framework.test import APIRequestFactory, force_authenticate


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user():
    user = MagicMock()
    user.is_authenticated = True
    return user


def _make_job_ns(**kwargs):
    source = SimpleNamespace(id=uuid.uuid4(), name="Adzuna", slug="adzuna")
    defaults = dict(
        id=uuid.uuid4(),
        source=source,
        title="Senior Python Developer",
        company="TechCorp",
        description="We are looking for a Python developer.",
        apply_url="https://example.com/apply",
        city="Bangalore",
        work_type="hybrid",
        salary_min=None,
        salary_max=None,
        salary_currency="INR",
        posted_at=None,
        is_active=True,
        is_private=False,
        fetched_at=datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_rec_ns(**kwargs):
    job = _make_job_ns()
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        job=job,
        score=Decimal("0.847"),
        score_breakdown={
            "skill": 0.82, "title": 0.75, "location": 1.0, "saved": 0.0, "salary": 0.5,
        },
        algorithm_version="v1",
        generated_at=now,
        expires_at=now + timedelta(hours=24),
        is_dismissed=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_rec_mock(**kwargs):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.is_dismissed = False
    for k, v in kwargs.items():
        setattr(mock, k, v)
    return mock


def _make_list_qs(recs):
    """Chained mock queryset: filter→filter→[filter]→select_related→order_by → recs."""
    mock_qs = MagicMock()
    mock_qs.filter.return_value = mock_qs
    mock_qs.select_related.return_value = mock_qs
    mock_qs.order_by.return_value = recs
    return mock_qs


factory = APIRequestFactory()


# ─── RecommendationListView — Authentication ──────────────────────────────────

class TestRecommendationListAuth:
    def test_returns_401_without_auth(self):
        request = factory.get("/api/v1/career-hub/recommendations/")
        response = RecommendationListView.as_view()(request)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.filter.return_value = _make_list_qs([])
            request = factory.get("/api/v1/career-hub/recommendations/")
            force_authenticate(request, user=user)
            response = RecommendationListView.as_view()(request)
        assert response.status_code == 200


# ─── RecommendationListView — Response ────────────────────────────────────────

class TestRecommendationListResponse:
    def _get_list(self, recs=None, params=None):
        user = _make_user()
        if recs is None:
            recs = []
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.filter.return_value = _make_list_qs(recs)
            request = factory.get("/api/v1/career-hub/recommendations/", params or {})
            force_authenticate(request, user=user)
            response = RecommendationListView.as_view()(request)
            response.accepted_renderer = MagicMock()
            response.accepted_media_type = "application/json"
            response.renderer_context = {}
        return response

    def test_response_has_success_envelope(self):
        response = self._get_list()
        assert response.data["success"] is True

    def test_response_has_pagination(self):
        response = self._get_list()
        assert "pagination" in response.data

    def test_response_has_meta(self):
        response = self._get_list()
        assert "meta" in response.data

    def test_meta_has_required_fields(self):
        response = self._get_list()
        meta = response.data["meta"]
        assert "request_id" in meta
        assert "timestamp" in meta
        assert meta["version"] == "v1"

    def test_data_is_empty_list_when_no_recommendations(self):
        response = self._get_list()
        assert response.data["data"] == []

    def test_data_includes_recommendation_score(self):
        rec = _make_rec_ns()
        response = self._get_list(recs=[rec])
        assert str(response.data["data"][0]["score"]) == str(rec.score)

    def test_data_includes_job_title(self):
        rec = _make_rec_ns()
        response = self._get_list(recs=[rec])
        assert response.data["data"][0]["job"]["title"] == rec.job.title

    def test_data_includes_score_breakdown(self):
        rec = _make_rec_ns()
        response = self._get_list(recs=[rec])
        assert response.data["data"][0]["score_breakdown"] == rec.score_breakdown

    def test_data_includes_algorithm_version(self):
        rec = _make_rec_ns()
        response = self._get_list(recs=[rec])
        assert response.data["data"][0]["algorithm_version"] == "v1"

    def test_data_includes_is_dismissed_false(self):
        rec = _make_rec_ns(is_dismissed=False)
        response = self._get_list(recs=[rec])
        assert response.data["data"][0]["is_dismissed"] is False


# ─── RecommendationListView — BOLA & Filters ─────────────────────────────────

class TestRecommendationListBOLA:
    def test_queryset_filtered_by_request_user(self):
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.filter.return_value = _make_list_qs([])
            request = factory.get("/api/v1/career-hub/recommendations/")
            force_authenticate(request, user=user)
            RecommendationListView.as_view()(request)
        MockRec.filter.assert_called_once_with(user=user)

    def test_default_excludes_dismissed(self):
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            mock_qs = _make_list_qs([])
            MockRec.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/recommendations/")
            force_authenticate(request, user=user)
            RecommendationListView.as_view()(request)
        mock_qs.filter.assert_any_call(is_dismissed=False)

    def test_dismissed_true_does_not_filter_is_dismissed(self):
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            mock_qs = _make_list_qs([])
            MockRec.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/recommendations/", {"dismissed": "true"})
            force_authenticate(request, user=user)
            RecommendationListView.as_view()(request)
        for c in mock_qs.filter.call_args_list:
            assert "is_dismissed" not in c.kwargs

    def test_ordering_is_score_desc_then_generated_at_desc(self):
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            mock_qs = _make_list_qs([])
            MockRec.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/recommendations/")
            force_authenticate(request, user=user)
            RecommendationListView.as_view()(request)
        mock_qs.order_by.assert_called_once_with("-score", "-generated_at")

    def test_select_related_is_applied(self):
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            mock_qs = _make_list_qs([])
            MockRec.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/recommendations/")
            force_authenticate(request, user=user)
            RecommendationListView.as_view()(request)
        mock_qs.select_related.assert_called_once_with("job__source")


# ─── RecommendationDetailView — Authentication ────────────────────────────────

class TestRecommendationDetailAuth:
    def test_returns_401_without_auth(self):
        pk = uuid.uuid4()
        request = factory.get(f"/api/v1/career-hub/recommendations/{pk}/")
        response = RecommendationDetailView.as_view()(request, pk=pk)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        pk = uuid.uuid4()
        rec = _make_rec_ns(id=pk)
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.select_related.return_value.get.return_value = rec
            request = factory.get(f"/api/v1/career-hub/recommendations/{pk}/")
            force_authenticate(request, user=_make_user())
            response = RecommendationDetailView.as_view()(request, pk=pk)
        assert response.status_code == 200


# ─── RecommendationDetailView — Response ─────────────────────────────────────

class TestRecommendationDetailResponse:
    def _get_detail(self, rec=None):
        if rec is None:
            rec = _make_rec_ns()
        user = _make_user()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.select_related.return_value.get.return_value = rec
            request = factory.get(f"/api/v1/career-hub/recommendations/{rec.id}/")
            force_authenticate(request, user=user)
            response = RecommendationDetailView.as_view()(request, pk=rec.id)
        return response, rec

    def test_response_has_success_envelope(self):
        response, _ = self._get_detail()
        assert response.data["success"] is True

    def test_response_has_no_pagination(self):
        response, _ = self._get_detail()
        assert "pagination" not in response.data

    def test_response_data_includes_score(self):
        rec = _make_rec_ns()
        response, _ = self._get_detail(rec)
        assert str(response.data["data"]["score"]) == str(rec.score)

    def test_response_data_includes_full_job_description(self):
        rec = _make_rec_ns()
        response, _ = self._get_detail(rec)
        assert response.data["data"]["job"]["description"] == rec.job.description

    def test_response_data_includes_apply_url(self):
        rec = _make_rec_ns()
        response, _ = self._get_detail(rec)
        assert response.data["data"]["job"]["apply_url"] == rec.job.apply_url

    def test_response_data_includes_score_breakdown(self):
        rec = _make_rec_ns()
        response, _ = self._get_detail(rec)
        assert response.data["data"]["score_breakdown"] == rec.score_breakdown


# ─── RecommendationDetailView — BOLA ─────────────────────────────────────────

class TestRecommendationDetailBOLA:
    def test_returns_404_for_nonexistent_recommendation(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.select_related.return_value.get.side_effect = JobRecommendation.DoesNotExist()
            request = factory.get(f"/api/v1/career-hub/recommendations/{pk}/")
            force_authenticate(request, user=_make_user())
            response = RecommendationDetailView.as_view()(request, pk=pk)
        assert response.status_code == 404

    def test_404_has_success_false(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.select_related.return_value.get.side_effect = JobRecommendation.DoesNotExist()
            request = factory.get(f"/api/v1/career-hub/recommendations/{pk}/")
            force_authenticate(request, user=_make_user())
            response = RecommendationDetailView.as_view()(request, pk=pk)
        assert response.data["success"] is False

    def test_get_called_with_user_isolation(self):
        pk = uuid.uuid4()
        user = _make_user()
        rec = _make_rec_ns(id=pk)
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.select_related.return_value.get.return_value = rec
            request = factory.get(f"/api/v1/career-hub/recommendations/{pk}/")
            force_authenticate(request, user=user)
            RecommendationDetailView.as_view()(request, pk=pk)
        call_kwargs = MockRec.select_related.return_value.get.call_args.kwargs
        assert call_kwargs["user"] == user
        assert call_kwargs["pk"] == pk


# ─── RecommendationDismissView — Authentication ───────────────────────────────

class TestRecommendationDismissAuth:
    def test_returns_401_without_auth(self):
        pk = uuid.uuid4()
        request = factory.patch(f"/api/v1/career-hub/recommendations/{pk}/dismiss/")
        response = RecommendationDismissView.as_view()(request, pk=pk)
        assert response.status_code == 401

    def test_method_not_allowed_for_get(self):
        pk = uuid.uuid4()
        request = factory.get(f"/api/v1/career-hub/recommendations/{pk}/dismiss/")
        force_authenticate(request, user=_make_user())
        response = RecommendationDismissView.as_view()(request, pk=pk)
        assert response.status_code == 405


# ─── RecommendationDismissView — Action ───────────────────────────────────────

class TestRecommendationDismissAction:
    def _patch_dismiss(self, pk=None, user=None):
        if pk is None:
            pk = uuid.uuid4()
        if user is None:
            user = _make_user()
        rec = _make_rec_mock(id=pk)
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.get.return_value = rec
            request = factory.patch(f"/api/v1/career-hub/recommendations/{pk}/dismiss/")
            force_authenticate(request, user=user)
            response = RecommendationDismissView.as_view()(request, pk=pk)
        return response, rec, MockRec

    def test_returns_200(self):
        response, _, _ = self._patch_dismiss()
        assert response.status_code == 200

    def test_response_has_success_envelope(self):
        response, _, _ = self._patch_dismiss()
        assert response.data["success"] is True

    def test_response_data_has_id(self):
        pk = uuid.uuid4()
        response, _, _ = self._patch_dismiss(pk=pk)
        assert response.data["data"]["id"] == str(pk)

    def test_response_data_is_dismissed_true(self):
        response, _, _ = self._patch_dismiss()
        assert response.data["data"]["is_dismissed"] is True

    def test_sets_is_dismissed_true_on_record(self):
        _, rec, _ = self._patch_dismiss()
        assert rec.is_dismissed is True

    def test_calls_save_with_update_fields(self):
        _, rec, _ = self._patch_dismiss()
        rec.save.assert_called_once_with(update_fields=["is_dismissed"])

    def test_returns_404_for_nonexistent_recommendation(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.get.side_effect = JobRecommendation.DoesNotExist()
            request = factory.patch(f"/api/v1/career-hub/recommendations/{pk}/dismiss/")
            force_authenticate(request, user=_make_user())
            response = RecommendationDismissView.as_view()(request, pk=pk)
        assert response.status_code == 404


# ─── RecommendationDismissView — BOLA ─────────────────────────────────────────

class TestRecommendationDismissBOLA:
    def test_returns_404_for_other_users_recommendation(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.get.side_effect = JobRecommendation.DoesNotExist()
            request = factory.patch(f"/api/v1/career-hub/recommendations/{pk}/dismiss/")
            force_authenticate(request, user=_make_user())
            response = RecommendationDismissView.as_view()(request, pk=pk)
        assert response.status_code == 404

    def test_get_called_with_user_isolation(self):
        pk = uuid.uuid4()
        user = _make_user()
        rec = _make_rec_mock(id=pk)
        with patch("apps.career_hub.views.JobRecommendation.objects") as MockRec:
            MockRec.get.return_value = rec
            request = factory.patch(f"/api/v1/career-hub/recommendations/{pk}/dismiss/")
            force_authenticate(request, user=user)
            RecommendationDismissView.as_view()(request, pk=pk)
        MockRec.get.assert_called_once_with(pk=pk, user=user)
