"""
API tests for Career Hub Job endpoints.

Authentication: force_authenticate bypasses JWT — tests focus on view logic.
ORM and service calls are mocked — no database access.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.career_hub.models import Job
from apps.career_hub.views import JobDetailView, JobListView
from rest_framework.test import APIRequestFactory, force_authenticate


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user():
    user = MagicMock()
    user.is_authenticated = True
    # Must be a concrete value: CareerHubSearchThrottle uses str(user.pk) as
    # the cache key, and MagicMock's auto-generated pk produces characters that
    # DummyCache's key validator rejects, causing _FailClosedMixin to deny requests.
    user.pk = uuid.uuid4()
    return user


def _make_job_ns(**kwargs):
    job_id = uuid.uuid4()
    source = SimpleNamespace(id=uuid.uuid4(), name="Adzuna", slug="adzuna")
    defaults = dict(
        id=job_id,
        source=source,
        title="Python Developer",
        company="TechCorp",
        description="A great opportunity for Python developers.",
        apply_url="https://example.com/jobs/1",
        city="Bangalore",
        work_type="hybrid",
        salary_min=None,
        salary_max=None,
        salary_currency="INR",
        posted_at=None,
        is_active=True,
        is_private=False,
        fetched_at=datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


factory = APIRequestFactory()


# ─── Job List — Authentication ────────────────────────────────────────────────

class TestJobListAuth:
    def test_returns_401_without_auth(self):
        request = factory.get("/api/v1/career-hub/jobs/")
        response = JobListView.as_view()(request)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        with patch("apps.career_hub.views.JobSearchService") as MockSvc:
            MockSvc.return_value.search.return_value = []
            request = factory.get("/api/v1/career-hub/jobs/")
            force_authenticate(request, user=_make_user())
            response = JobListView.as_view()(request)
        assert response.status_code == 200


# ─── Job List — Response envelope ────────────────────────────────────────────

class TestJobListEnvelope:
    def _get(self, params=None):
        with patch("apps.career_hub.views.JobSearchService") as MockSvc:
            MockSvc.return_value.search.return_value = []
            request = factory.get("/api/v1/career-hub/jobs/", params or {})
            force_authenticate(request, user=_make_user())
            response = JobListView.as_view()(request)
            response.accepted_renderer = MagicMock()
            response.accepted_media_type = "application/json"
            response.renderer_context = {}
        return response

    def test_response_has_success_true(self):
        response = self._get()
        assert response.data["success"] is True

    def test_response_has_data_key(self):
        response = self._get()
        assert "data" in response.data

    def test_response_data_is_empty_list_when_no_results(self):
        response = self._get()
        assert response.data["data"] == []

    def test_response_has_pagination_key(self):
        response = self._get()
        assert "pagination" in response.data

    def test_pagination_has_required_fields(self):
        response = self._get()
        pagination = response.data["pagination"]
        for key in ("count", "next", "previous", "page_size", "current_page", "total_pages"):
            assert key in pagination, f"Missing pagination key: {key}"

    def test_pagination_count_is_zero_for_empty_results(self):
        response = self._get()
        assert response.data["pagination"]["count"] == 0

    def test_response_has_meta_key(self):
        # F-05: paginated responses must include meta to match non-paginated envelope
        response = self._get()
        assert "meta" in response.data

    def test_meta_has_required_fields(self):
        response = self._get()
        meta = response.data["meta"]
        assert "request_id" in meta
        assert "timestamp" in meta
        assert meta["version"] == "v1"


# ─── Job List — Service call arguments ───────────────────────────────────────

class TestJobListServiceParams:
    def _call_and_capture(self, params):
        with patch("apps.career_hub.views.JobSearchService") as MockSvc:
            mock_instance = MagicMock()
            mock_instance.search.return_value = []
            MockSvc.return_value = mock_instance
            request = factory.get("/api/v1/career-hub/jobs/", params)
            force_authenticate(request, user=_make_user())
            JobListView.as_view()(request)
            return mock_instance.search.call_args.kwargs

    def test_q_param_passed_to_service(self):
        kwargs = self._call_and_capture({"q": "python engineer"})
        assert kwargs["q"] == "python engineer"

    def test_city_param_passed_to_service(self):
        kwargs = self._call_and_capture({"city": "Mumbai"})
        assert kwargs["city"] == "Mumbai"

    def test_work_type_param_passed_to_service(self):
        kwargs = self._call_and_capture({"work_type": "remote"})
        assert kwargs["work_type"] == "remote"

    def test_sort_param_passed_to_service(self):
        kwargs = self._call_and_capture({"sort": "salary_high"})
        assert kwargs["sort"] == "salary_high"

    def test_salary_min_passed_to_service(self):
        kwargs = self._call_and_capture({"salary_min": "500000"})
        assert kwargs["salary_min"] == Decimal("500000")

    def test_salary_max_passed_to_service(self):
        kwargs = self._call_and_capture({"salary_max": "1000000"})
        assert kwargs["salary_max"] == Decimal("1000000")

    def test_source_param_passed_to_service(self):
        kwargs = self._call_and_capture({"source": "adzuna"})
        assert kwargs["source"] == "adzuna"

    def test_defaults_used_when_no_params(self):
        kwargs = self._call_and_capture({})
        assert kwargs["q"] == ""
        assert kwargs["city"] == ""
        assert kwargs["work_type"] is None
        assert kwargs["source"] is None
        assert kwargs["salary_min"] is None
        assert kwargs["salary_max"] is None
        assert kwargs["sort"] == "newest"


# ─── Job List — Validation ────────────────────────────────────────────────────

class TestJobListValidation:
    def _get_status(self, params):
        with patch("apps.career_hub.views.JobSearchService") as MockSvc:
            MockSvc.return_value.search.return_value = []
            request = factory.get("/api/v1/career-hub/jobs/", params)
            force_authenticate(request, user=_make_user())
            response = JobListView.as_view()(request)
        return response.status_code

    def test_invalid_salary_range_returns_400(self):
        status = self._get_status({"salary_min": "1000000", "salary_max": "500000"})
        assert status == 400

    def test_invalid_work_type_returns_400(self):
        status = self._get_status({"work_type": "spaceship"})
        assert status == 400

    def test_page_size_over_max_returns_400(self):
        status = self._get_status({"page_size": "999"})
        assert status == 400

    def test_invalid_sort_value_returns_400(self):
        status = self._get_status({"sort": "random_order"})
        assert status == 400

    def test_page_zero_returns_400(self):
        # F-01: serializer min_value=1 on page field — verified here explicitly
        status = self._get_status({"page": "0"})
        assert status == 400

    def test_page_negative_returns_400(self):
        status = self._get_status({"page": "-1"})
        assert status == 400


# ─── Job Detail — Authentication ──────────────────────────────────────────────

class TestJobDetailAuth:
    def test_returns_401_without_auth(self):
        pk = uuid.uuid4()
        request = factory.get(f"/api/v1/career-hub/jobs/{pk}/")
        response = JobDetailView.as_view()(request, pk=pk)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        mock_job = _make_job_ns()
        with patch("apps.career_hub.views.Job.objects") as MockObjects:
            MockObjects.select_related.return_value.get.return_value = mock_job
            request = factory.get(f"/api/v1/career-hub/jobs/{mock_job.id}/")
            force_authenticate(request, user=_make_user())
            response = JobDetailView.as_view()(request, pk=mock_job.id)
        assert response.status_code == 200


# ─── Job Detail — Response envelope ──────────────────────────────────────────

class TestJobDetailEnvelope:
    def _get_detail(self, job=None):
        mock_job = job or _make_job_ns()
        with patch("apps.career_hub.views.Job.objects") as MockObjects:
            MockObjects.select_related.return_value.get.return_value = mock_job
            request = factory.get(f"/api/v1/career-hub/jobs/{mock_job.id}/")
            force_authenticate(request, user=_make_user())
            response = JobDetailView.as_view()(request, pk=mock_job.id)
        return response, mock_job

    def test_response_has_success_envelope(self):
        response, _ = self._get_detail()
        assert response.data["success"] is True
        assert "data" in response.data
        assert "meta" in response.data

    def test_response_includes_apply_url(self):
        response, mock_job = self._get_detail()
        assert response.data["data"]["apply_url"] == mock_job.apply_url

    def test_response_includes_description(self):
        response, mock_job = self._get_detail()
        assert response.data["data"]["description"] == mock_job.description

    def test_response_includes_source_name(self):
        response, mock_job = self._get_detail()
        assert response.data["data"]["source_name"] == mock_job.source.name

    def test_response_includes_work_type(self):
        response, mock_job = self._get_detail()
        assert response.data["data"]["work_type"] == mock_job.work_type


# ─── Job Detail — 404 cases ───────────────────────────────────────────────────

class TestJobDetailNotFound:
    def test_returns_404_for_nonexistent_job(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.Job.objects") as MockObjects:
            MockObjects.select_related.return_value.get.side_effect = Job.DoesNotExist()
            request = factory.get(f"/api/v1/career-hub/jobs/{pk}/")
            force_authenticate(request, user=_make_user())
            response = JobDetailView.as_view()(request, pk=pk)
        assert response.status_code == 404

    def test_404_response_has_success_false(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.Job.objects") as MockObjects:
            MockObjects.select_related.return_value.get.side_effect = Job.DoesNotExist()
            request = factory.get(f"/api/v1/career-hub/jobs/{pk}/")
            force_authenticate(request, user=_make_user())
            response = JobDetailView.as_view()(request, pk=pk)
        assert response.data["success"] is False

    def test_get_enforces_active_non_private_non_deleted_filter(self):
        # F-04: verify the three access guards are present in the .get() call kwargs
        pk = uuid.uuid4()
        mock_job = _make_job_ns(id=pk)
        with patch("apps.career_hub.views.Job.objects") as MockObjects:
            MockObjects.select_related.return_value.get.return_value = mock_job
            request = factory.get(f"/api/v1/career-hub/jobs/{pk}/")
            force_authenticate(request, user=_make_user())
            JobDetailView.as_view()(request, pk=pk)
            call_kwargs = MockObjects.select_related.return_value.get.call_args.kwargs
        assert call_kwargs["is_active"] is True
        assert call_kwargs["is_private"] is False
        assert call_kwargs["deleted_at__isnull"] is True
