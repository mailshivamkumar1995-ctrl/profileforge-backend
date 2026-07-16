"""
API tests for Career Hub Saved Jobs endpoints.

POST   /api/v1/career-hub/jobs/{id}/save/   — SaveJobView
DELETE /api/v1/career-hub/jobs/{id}/save/   — SaveJobView
GET    /api/v1/career-hub/saved-jobs/       — SavedJobListView

Authentication: force_authenticate bypasses JWT.
ORM calls are mocked — no database access.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.career_hub.models import Job, UserJob
from apps.career_hub.views import SavedJobListView, SaveJobView
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
        title="Python Developer",
        company="TechCorp",
        description="Great role.",
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


def _make_user_job_ns(job=None, **kwargs):
    job = job or _make_job_ns()
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        job=job,
        status="saved",
        notes="",
        applied_at=None,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


factory = APIRequestFactory()


# ─── SaveJobView POST — Authentication ────────────────────────────────────────

class TestSaveJobAuth:
    def test_post_returns_401_without_auth(self):
        pk = uuid.uuid4()
        request = factory.post(f"/api/v1/career-hub/jobs/{pk}/save/")
        response = SaveJobView.as_view()(request, pk=pk)
        assert response.status_code == 401

    def test_delete_returns_401_without_auth(self):
        pk = uuid.uuid4()
        request = factory.delete(f"/api/v1/career-hub/jobs/{pk}/save/")
        response = SaveJobView.as_view()(request, pk=pk)
        assert response.status_code == 401


# ─── SaveJobView POST — 404 cases ─────────────────────────────────────────────

class TestSaveJobNotFound:
    def test_returns_404_for_nonexistent_job(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.Job.objects") as MockObjs:
            MockObjs.select_related.return_value.get.side_effect = Job.DoesNotExist()
            request = factory.post(f"/api/v1/career-hub/jobs/{pk}/save/")
            force_authenticate(request, user=_make_user())
            response = SaveJobView.as_view()(request, pk=pk)
        assert response.status_code == 404

    def test_save_enforces_active_non_private_non_deleted_filter(self):
        # F-06: replaces duplicate inactive-job test with verification that
        # the three access guards (is_active, is_private, deleted_at__isnull)
        # are all present in the .get() call kwargs
        pk = uuid.uuid4()
        mock_job = _make_job_ns(id=pk)
        with (
            patch("apps.career_hub.views.Job.objects") as MockJobObjs,
            patch("apps.career_hub.views.UserJob.objects") as MockUJObjs,
        ):
            MockJobObjs.select_related.return_value.get.return_value = mock_job
            MockUJObjs.get_or_create.return_value = (_make_user_job_ns(job=mock_job), True)
            request = factory.post(f"/api/v1/career-hub/jobs/{pk}/save/")
            force_authenticate(request, user=_make_user())
            SaveJobView.as_view()(request, pk=pk)
            call_kwargs = MockJobObjs.select_related.return_value.get.call_args.kwargs
        assert call_kwargs["is_active"] is True
        assert call_kwargs["is_private"] is False
        assert call_kwargs["deleted_at__isnull"] is True

    def test_404_response_has_success_false(self):
        pk = uuid.uuid4()
        with patch("apps.career_hub.views.Job.objects") as MockObjs:
            MockObjs.select_related.return_value.get.side_effect = Job.DoesNotExist()
            request = factory.post(f"/api/v1/career-hub/jobs/{pk}/save/")
            force_authenticate(request, user=_make_user())
            response = SaveJobView.as_view()(request, pk=pk)
        assert response.data["success"] is False


# ─── SaveJobView POST — Create ─────────────────────────────────────────────────

class TestSaveJobCreate:
    def _post_save(self, created=True):
        job = _make_job_ns()
        user_job = _make_user_job_ns(job=job)
        user = _make_user()

        with (
            patch("apps.career_hub.views.Job.objects") as MockJobObjs,
            patch("apps.career_hub.views.UserJob.objects") as MockUJObjs,
        ):
            MockJobObjs.select_related.return_value.get.return_value = job
            MockUJObjs.get_or_create.return_value = (user_job, created)
            request = factory.post(f"/api/v1/career-hub/jobs/{job.id}/save/")
            force_authenticate(request, user=user)
            response = SaveJobView.as_view()(request, pk=job.id)

        return response, job, user_job

    def test_returns_201_when_newly_saved(self):
        response, _, _ = self._post_save(created=True)
        assert response.status_code == 201

    def test_returns_200_when_already_saved(self):
        response, _, _ = self._post_save(created=False)
        assert response.status_code == 200

    def test_response_has_success_envelope(self):
        response, _, _ = self._post_save()
        assert response.data["success"] is True
        assert "data" in response.data

    def test_response_includes_job_title(self):
        response, job, _ = self._post_save()
        assert response.data["data"]["job"]["title"] == job.title

    def test_response_includes_job_company(self):
        response, job, _ = self._post_save()
        assert response.data["data"]["job"]["company"] == job.company

    def test_response_includes_status_saved(self):
        response, _, _ = self._post_save()
        assert response.data["data"]["status"] == "saved"

    def test_get_or_create_called_with_correct_args(self):
        job = _make_job_ns()
        user_job = _make_user_job_ns(job=job)
        user = _make_user()

        with (
            patch("apps.career_hub.views.Job.objects") as MockJobObjs,
            patch("apps.career_hub.views.UserJob.objects") as MockUJObjs,
        ):
            MockJobObjs.select_related.return_value.get.return_value = job
            MockUJObjs.get_or_create.return_value = (user_job, True)
            request = factory.post(f"/api/v1/career-hub/jobs/{job.id}/save/")
            force_authenticate(request, user=user)
            SaveJobView.as_view()(request, pk=job.id)

            call_kwargs = MockUJObjs.get_or_create.call_args.kwargs
            assert call_kwargs["user"] == user
            assert call_kwargs["job"] == job
            assert call_kwargs["defaults"]["status"] == UserJob.Status.SAVED


# ─── SaveJobView DELETE ────────────────────────────────────────────────────────

class TestUnsaveJob:
    def _delete_save(self, deleted_count=1):
        job_id = uuid.uuid4()
        user = _make_user()

        with patch("apps.career_hub.views.UserJob.objects") as MockUJObjs:
            mock_qs = MagicMock()
            mock_qs.delete.return_value = (deleted_count, {})
            MockUJObjs.filter.return_value = mock_qs
            request = factory.delete(f"/api/v1/career-hub/jobs/{job_id}/save/")
            force_authenticate(request, user=user)
            response = SaveJobView.as_view()(request, pk=job_id)

        return response, MockUJObjs, job_id, user

    def test_returns_204_when_unsaved(self):
        response, _, _, _ = self._delete_save(deleted_count=1)
        assert response.status_code == 204

    def test_returns_404_when_not_saved(self):
        response, _, _, _ = self._delete_save(deleted_count=0)
        assert response.status_code == 404

    def test_filter_called_with_user_and_job_id(self):
        _, MockUJObjs, job_id, user = self._delete_save()
        MockUJObjs.filter.assert_called_once_with(user=user, job_id=job_id)

    def test_delete_called_on_queryset(self):
        response, MockUJObjs, _, _ = self._delete_save()
        MockUJObjs.filter.return_value.delete.assert_called_once()

    def test_204_response_has_no_body(self):
        response, _, _, _ = self._delete_save(deleted_count=1)
        assert not response.data


# ─── SavedJobListView — Authentication ────────────────────────────────────────

class TestSavedJobListAuth:
    def test_returns_401_without_auth(self):
        request = factory.get("/api/v1/career-hub/saved-jobs/")
        response = SavedJobListView.as_view()(request)
        assert response.status_code == 401

    def test_returns_200_with_valid_auth(self):
        user = _make_user()
        with patch("apps.career_hub.views.UserJob.objects") as MockUJObjs:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.select_related.return_value = mock_qs
            mock_qs.order_by.return_value = []
            MockUJObjs.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/saved-jobs/")
            force_authenticate(request, user=user)
            response = SavedJobListView.as_view()(request)
        assert response.status_code == 200


# ─── SavedJobListView — Response ──────────────────────────────────────────────

class TestSavedJobListResponse:
    def _get_list(self, user_jobs=None):
        user = _make_user()
        if user_jobs is None:
            user_jobs = []

        with patch("apps.career_hub.views.UserJob.objects") as MockUJObjs:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.select_related.return_value = mock_qs
            mock_qs.order_by.return_value = user_jobs
            MockUJObjs.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/saved-jobs/")
            force_authenticate(request, user=user)
            response = SavedJobListView.as_view()(request)
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

    def test_response_data_is_empty_list_when_no_saved_jobs(self):
        response = self._get_list()
        assert response.data["data"] == []

    def test_response_includes_job_details(self):
        job = _make_job_ns()
        user_job = _make_user_job_ns(job=job)
        response = self._get_list(user_jobs=[user_job])
        assert response.data["data"][0]["job"]["title"] == job.title

    def test_queryset_filtered_by_user(self):
        user = _make_user()
        with patch("apps.career_hub.views.UserJob.objects") as MockUJObjs:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.select_related.return_value = mock_qs
            mock_qs.order_by.return_value = []
            MockUJObjs.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/saved-jobs/")
            force_authenticate(request, user=user)
            SavedJobListView.as_view()(request)
            MockUJObjs.filter.assert_called_once_with(user=user)

    def test_queryset_ordered_by_created_at_desc(self):
        user = _make_user()
        with patch("apps.career_hub.views.UserJob.objects") as MockUJObjs:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.select_related.return_value = mock_qs
            mock_qs.order_by.return_value = []
            MockUJObjs.filter.return_value = mock_qs
            request = factory.get("/api/v1/career-hub/saved-jobs/")
            force_authenticate(request, user=user)
            SavedJobListView.as_view()(request)
            mock_qs.order_by.assert_called_once_with("-created_at")

    def test_paginated_response_has_meta_key(self):
        # F-05: paginated saved-jobs list must include meta to match non-paginated envelope
        response = self._get_list()
        assert "meta" in response.data

    def test_paginated_response_meta_has_required_fields(self):
        response = self._get_list()
        meta = response.data["meta"]
        assert "request_id" in meta
        assert "timestamp" in meta
        assert meta["version"] == "v1"
