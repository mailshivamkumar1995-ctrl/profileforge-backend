"""
Scenario-level tests for JobSyncService.

These tests verify end-to-end sync behavior across multi-step scenarios.
ORM operations are mocked; focus is on service orchestration correctness.

No database access. No network access.
"""
import logging
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from apps.career_hub.providers.base import NormalizedJob
from apps.career_hub.services.sync import JobSyncService, SyncResult


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _job(eid: str = "IN_001", *, title: str = "Dev", city: str = "Bangalore") -> NormalizedJob:
    return NormalizedJob(
        external_id=eid,
        title=title,
        company="Corp",
        description="Description",
        apply_url=f"https://example.com/{eid}",
        city=city,
        work_type="hybrid",
        salary_min=None,
        salary_max=None,
        salary_currency="INR",
        posted_at=None,
        is_private=False,
    )


def _make_provider(*page_lists) -> MagicMock:
    """Provider that returns page_lists[i] for page i+1; returns [] thereafter."""
    provider = MagicMock()
    provider.source_name = "adzuna"
    def _fetch(query, city, page=1):
        idx = page - 1
        return page_lists[idx] if idx < len(page_lists) else []
    provider.fetch_jobs.side_effect = _fetch
    return provider


def _run_sync(provider, upsert_return=(1, 0, 0), sweep_return=0, **sync_kwargs):
    """Run sync() with ORM methods patched."""
    service = JobSyncService(provider)
    source = MagicMock()
    source.slug = "adzuna"
    with patch.object(service, "_resolve_source", return_value=source), \
         patch.object(service, "_upsert_batch", return_value=upsert_return) as mock_upsert, \
         patch.object(service, "_mark_stale_inactive", return_value=sweep_return) as mock_sweep:
        result = service.sync("software engineer", "Bangalore", **sync_kwargs)
    return result, mock_upsert, mock_sweep


# ─── IT-01 Catalog preserved on complete provider failure ──────────────────────

class TestCatalogPreservationOnFailure:
    def test_catalog_preserved_on_complete_api_failure(self):
        provider = _make_provider()  # all pages empty
        result, _, mock_sweep = _run_sync(provider)
        assert result.sweep_skipped is True
        mock_sweep.assert_not_called()
        assert result.deactivated == 0

    def test_no_jobs_upserted_on_complete_failure(self):
        provider = _make_provider()
        result, mock_upsert, _ = _run_sync(provider)
        mock_upsert.assert_not_called()
        assert result.created == 0
        assert result.updated == 0

    def test_catalog_preserved_on_timeout_simulation(self):
        """Provider raises on fetch — errors counted, sweep skipped."""
        provider = MagicMock()
        provider.source_name = "adzuna"
        provider.fetch_jobs.side_effect = Exception("simulated timeout")
        result, _, mock_sweep = _run_sync(provider)
        assert result.errors == 1
        assert result.sweep_skipped is True
        mock_sweep.assert_not_called()


# ─── IT-02 Stale jobs deactivated on successful sync ─────────────────────────

class TestStaleJobDeactivation:
    def test_stale_sweep_runs_on_successful_sync(self):
        provider = _make_provider([_job("IN_1")])
        result, _, mock_sweep = _run_sync(provider, sweep_return=3)
        assert result.sweep_skipped is False
        mock_sweep.assert_called_once()
        assert result.deactivated == 3

    def test_sweep_receives_sync_start_before_page_fetch(self):
        """sync_start must be captured before the first fetch_jobs call."""
        from django.utils import timezone
        captured_times = []

        provider = _make_provider([_job()])
        service = JobSyncService(provider)
        source = MagicMock()
        source.slug = "adzuna"

        original_fetch = provider.fetch_jobs.side_effect

        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(1, 0, 0)), \
             patch.object(service, "_mark_stale_inactive") as mock_sweep, \
             patch("apps.career_hub.services.sync.timezone") as mock_tz:
            # Return incrementing timestamps so we can verify ordering
            times = [timezone.now(), timezone.now(), timezone.now()]
            mock_tz.now.side_effect = times
            service.sync("software engineer", "Bangalore")
            if mock_sweep.called:
                sweep_call_args = mock_sweep.call_args
                # sync_start is the second arg (source is first)
                sync_start_passed = sweep_call_args[0][1]
                # sync_start should be times[0] (captured before first fetch)
                assert sync_start_passed == times[0]


# ─── IT-03 UserJob soft-delete safety ────────────────────────────────────────

class TestUserJobPreservation:
    def test_sweep_calls_job_update_not_delete(self):
        """Stale sweep must UPDATE is_active, never DELETE jobs."""
        provider = _make_provider([_job()])
        service = JobSyncService(provider)
        source = MagicMock()
        source.slug = "adzuna"

        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(1, 0, 0)), \
             patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            mock_qs = MagicMock()
            mock_qs.update.return_value = 2
            MockJob.objects.filter.return_value = mock_qs
            service._mark_stale_inactive(source, MagicMock())

        mock_qs.delete.assert_not_called()
        mock_qs.update.assert_called_once()

    def test_sweep_update_sets_is_active_false(self):
        """Verify is_active=False is set, not True."""
        provider = _make_provider()
        service = JobSyncService(provider)
        source = MagicMock()

        with patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            mock_qs = MagicMock()
            mock_qs.update.return_value = 0
            MockJob.objects.filter.return_value = mock_qs
            service._mark_stale_inactive(source, MagicMock())

        update_kwargs = mock_qs.update.call_args.kwargs
        assert update_kwargs.get("is_active") is False


# ─── IT-04 deleted_at not modified when sweep skipped ────────────────────────

class TestDeletedAtPreservation:
    def test_no_filter_update_when_sweep_skipped(self):
        """When sweep is skipped, Job.objects.filter().update() must not be called."""
        provider = _make_provider()  # all empty
        service = JobSyncService(provider)
        source = MagicMock()

        with patch.object(service, "_resolve_source", return_value=source), \
             patch("apps.career_hub.services.sync.Job") as MockJob:
            service.sync("software engineer", "Bangalore")

        # filter().update() should never be called (the sweep path was skipped)
        if MockJob.objects.filter.called:
            # If filter was called, it was for the inactive_eids query in _upsert_batch,
            # but _upsert_batch shouldn't be called either since no jobs
            # Verify update() was not called on the filter result
            for mock_call in MockJob.objects.filter.return_value.update.call_args_list:
                pytest.fail(f"update() was called unexpectedly: {mock_call}")


# ─── IT-05 Reactivation after stale sweep ────────────────────────────────────

class TestReactivation:
    def test_reactivation_counted_separately_from_update(self):
        job = _job("IN_1")
        provider = _make_provider([job])
        service = JobSyncService(provider)
        source = MagicMock()
        source.slug = "adzuna"

        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_mark_stale_inactive", return_value=0), \
             patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            # Simulate: job was inactive
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = ["IN_1"]  # inactive
            MockJob.objects.filter.return_value = mock_qs
            MockJob.objects.update_or_create.return_value = (MagicMock(), False)

            result = service.sync("software engineer", "Bangalore")

        assert result.reactivated == 1
        assert result.updated == 0

    def test_upsert_defaults_set_is_active_true_and_deleted_at_none(self):
        """Reactivation works because defaults always set is_active=True, deleted_at=None."""
        job = _job("IN_1")
        provider = _make_provider([job])
        service = JobSyncService(provider)
        source = MagicMock()
        source.slug = "adzuna"

        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_mark_stale_inactive", return_value=0), \
             patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = []
            MockJob.objects.filter.return_value = mock_qs
            MockJob.objects.update_or_create.return_value = (MagicMock(), True)
            service.sync("software engineer", "Bangalore")

        _, call_kwargs = MockJob.objects.update_or_create.call_args
        defaults = call_kwargs.get("defaults", {})
        assert defaults.get("is_active") is True
        assert defaults.get("deleted_at") is None


# ─── External ID and field mapping ────────────────────────────────────────────

class TestFieldMapping:
    def _get_upsert_defaults(self, job: NormalizedJob) -> dict:
        provider = _make_provider([job])
        service = JobSyncService(provider)
        source = MagicMock()
        source.slug = "adzuna"

        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_mark_stale_inactive", return_value=0), \
             patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = []
            MockJob.objects.filter.return_value = mock_qs
            MockJob.objects.update_or_create.return_value = (MagicMock(), True)
            service.sync("software engineer", "Bangalore")
            _, call_kwargs = MockJob.objects.update_or_create.call_args
            return call_kwargs.get("defaults", {}), call_kwargs

    def test_external_id_passed_as_lookup_key(self):
        job = _job("IN_4678990100")
        _, call_kwargs = self._get_upsert_defaults(job)
        assert call_kwargs.get("external_id") == "IN_4678990100"

    def test_is_private_always_false_for_adzuna(self):
        job = _job("IN_1")
        defaults, _ = self._get_upsert_defaults(job)
        assert defaults.get("is_private") is False

    def test_city_none_stored_as_empty_string(self):
        job = _job("IN_1", city=None)
        defaults, _ = self._get_upsert_defaults(
            NormalizedJob(
                external_id="IN_1", title="Dev", company="Corp",
                description="Desc", apply_url="https://x.com",
                city=None, work_type="hybrid", salary_min=None,
                salary_max=None, salary_currency="INR",
                posted_at=None, is_private=False,
            )
        )
        assert defaults.get("city") == ""

    def test_sync_result_provider_matches_source_name(self):
        provider = _make_provider()
        provider.source_name = "adzuna"
        result, _, _ = _run_sync(provider)
        assert result.provider == "adzuna"
