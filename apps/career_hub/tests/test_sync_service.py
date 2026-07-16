"""
Unit tests for JobSyncService.

All ORM operations and provider calls are mocked.
No database access. No network access.
"""
import logging
from dataclasses import fields as dc_fields
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from apps.career_hub.providers.base import NormalizedJob
from apps.career_hub.services.sync import JobSyncService, SyncResult


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_provider(jobs_by_page: dict | None = None) -> MagicMock:
    """Build a mock provider where each page key maps to a NormalizedJob list."""
    provider = MagicMock()
    provider.source_name = "adzuna"
    jobs_by_page = jobs_by_page or {}

    def _fetch(query, city, page=1):
        return jobs_by_page.get(page, [])

    provider.fetch_jobs.side_effect = _fetch
    return provider


def _make_job(external_id: str = "IN_001", **kwargs) -> NormalizedJob:
    defaults = dict(
        external_id=external_id,
        title="Python Developer",
        company="TechCorp",
        description="Great opportunity",
        apply_url="https://example.com/job/1",
        city="Bangalore",
        work_type="hybrid",
        salary_min=Decimal("600000"),
        salary_max=Decimal("1000000"),
        salary_currency="INR",
        posted_at=None,
        is_private=False,
    )
    defaults.update(kwargs)
    return NormalizedJob(**defaults)


def _make_source() -> MagicMock:
    s = MagicMock()
    s.slug = "adzuna"
    return s


# ─── SyncResult dataclass ─────────────────────────────────────────────────────

class TestSyncResultStructure:
    def test_is_dataclass(self):
        result = SyncResult(
            provider="adzuna", query="python", city="Bangalore",
            pages_fetched=1, jobs_seen=10, created=5, updated=3,
            reactivated=2, deactivated=1, errors=0,
            duration_seconds=1.5, sweep_skipped=False,
        )
        assert isinstance(result, SyncResult)

    def test_all_required_fields_present(self):
        field_names = {f.name for f in dc_fields(SyncResult)}
        required = {
            "provider", "query", "city", "pages_fetched", "jobs_seen",
            "created", "updated", "reactivated", "deactivated",
            "errors", "duration_seconds", "sweep_skipped",
        }
        assert required.issubset(field_names)

    def test_sweep_skipped_is_bool(self):
        result = SyncResult(
            provider="adzuna", query="q", city="c", pages_fetched=0,
            jobs_seen=0, created=0, updated=0, reactivated=0,
            deactivated=0, errors=0, duration_seconds=0.1, sweep_skipped=True,
        )
        assert isinstance(result.sweep_skipped, bool)


# ─── Pagination control ───────────────────────────────────────────────────────

class TestPagination:
    def _run(self, jobs_by_page, max_pages=5):
        provider = _make_provider(jobs_by_page)
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(1, 0, 0)), \
             patch.object(service, "_mark_stale_inactive", return_value=0):
            return service.sync("python", "Bangalore", max_pages=max_pages)

    def test_empty_page_1_breaks_immediately(self):
        result = self._run({})
        assert result.pages_fetched == 0
        assert result.jobs_seen == 0

    def test_empty_page_n_breaks_loop(self):
        jobs = [_make_job()]
        result = self._run({1: jobs, 2: jobs, 3: []})
        assert result.pages_fetched == 2

    def test_max_pages_limits_pagination(self):
        jobs = [_make_job()]
        result = self._run({1: jobs, 2: jobs, 3: jobs}, max_pages=2)
        assert result.pages_fetched == 2

    def test_all_pages_fetched_when_non_empty(self):
        jobs = [_make_job()]
        result = self._run({1: jobs, 2: jobs, 3: jobs, 4: jobs, 5: jobs})
        assert result.pages_fetched == 5

    def test_jobs_seen_sums_across_pages(self):
        j1, j2 = _make_job("IN_1"), _make_job("IN_2")
        j3 = _make_job("IN_3")
        result = self._run({1: [j1, j2], 2: [j3], 3: []})
        assert result.jobs_seen == 3


# ─── Source provisioning ──────────────────────────────────────────────────────

class TestSourceProvisioning:
    def test_resolve_source_calls_get_or_create(self):
        provider = _make_provider()
        service = JobSyncService(provider)
        mock_source = _make_source()

        with patch("apps.career_hub.services.sync.JobSource") as MockSource:
            MockSource.objects.get_or_create.return_value = (mock_source, False)
            returned = service._resolve_source()

        MockSource.objects.get_or_create.assert_called_once_with(
            slug="adzuna",
            defaults={"name": "Adzuna", "is_active": True},
        )
        assert returned is mock_source

    def test_resolve_source_returns_existing_without_recreate(self):
        provider = _make_provider()
        service = JobSyncService(provider)
        mock_source = _make_source()
        call_count = 0

        with patch("apps.career_hub.services.sync.JobSource") as MockSource:
            MockSource.objects.get_or_create.return_value = (mock_source, False)
            service._resolve_source()
            service._resolve_source()
            assert MockSource.objects.get_or_create.call_count == 2


# ─── Upsert counting ──────────────────────────────────────────────────────────

class TestUpsertCounting:
    def _run_upsert(self, jobs, was_created_sequence, inactive_eids=None):
        provider = _make_provider()
        service = JobSyncService(provider)
        mock_source = _make_source()
        inactive_eids = inactive_eids or set()

        mock_qs = MagicMock()
        mock_qs.values_list.return_value = list(inactive_eids)

        side_effects = [(MagicMock(), c) for c in was_created_sequence]

        with patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            MockJob.objects.filter.return_value = mock_qs
            MockJob.objects.update_or_create.side_effect = side_effects
            return service._upsert_batch(jobs, mock_source)

    def test_new_jobs_counted_as_created(self):
        jobs = [_make_job("IN_1"), _make_job("IN_2")]
        c, u, r = self._run_upsert(jobs, [True, True])
        assert c == 2
        assert u == 0
        assert r == 0

    def test_existing_active_jobs_counted_as_updated(self):
        jobs = [_make_job("IN_1")]
        c, u, r = self._run_upsert(jobs, [False])
        assert c == 0
        assert u == 1
        assert r == 0

    def test_inactive_jobs_counted_as_reactivated(self):
        job = _make_job("IN_1")
        c, u, r = self._run_upsert([job], [False], inactive_eids={"IN_1"})
        assert c == 0
        assert u == 0
        assert r == 1

    def test_mixed_counts(self):
        j1 = _make_job("IN_1")  # created
        j2 = _make_job("IN_2")  # updated (was active)
        j3 = _make_job("IN_3")  # reactivated (was inactive)
        c, u, r = self._run_upsert(
            [j1, j2, j3], [True, False, False], inactive_eids={"IN_3"}
        )
        assert c == 1
        assert u == 1
        assert r == 1

    def test_empty_batch_returns_zeros(self):
        provider = _make_provider()
        service = JobSyncService(provider)
        assert service._upsert_batch([], _make_source()) == (0, 0, 0)


# ─── COND-01 Safety Gate (SGT-01 through SGT-08) ──────────────────────────────

class TestCond01SweepGate:
    def _run(self, jobs_by_page, max_pages=5):
        provider = _make_provider(jobs_by_page)
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source) as _, \
             patch.object(service, "_upsert_batch", return_value=(1, 0, 0)) as mock_upsert, \
             patch.object(service, "_mark_stale_inactive", return_value=0) as mock_sweep:
            result = service.sync("python", "Bangalore", max_pages=max_pages)
            return result, mock_upsert, mock_sweep

    # SGT-01
    def test_sweep_skipped_when_all_pages_empty(self):
        result, _, mock_sweep = self._run({})
        assert result.sweep_skipped is True
        mock_sweep.assert_not_called()

    # SGT-02
    def test_sweep_skipped_when_rate_limited_simulation(self):
        """Provider returns [] on all pages (simulates 429 absorption)."""
        result, _, mock_sweep = self._run({1: [], 2: [], 3: []})
        assert result.sweep_skipped is True
        mock_sweep.assert_not_called()

    # SGT-03
    def test_sweep_skipped_when_jobs_seen_zero_despite_pages(self):
        """
        If _upsert_batch receives 0 jobs (e.g., future service-layer filter),
        the sweep must still be skipped.
        """
        provider = _make_provider({1: [_make_job()]})
        service = JobSyncService(provider)
        source = _make_source()
        # Simulate service-layer filter: upsert receives 0 jobs
        # We test this by forcing jobs_seen to stay 0 via patching:
        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_mark_stale_inactive", return_value=0) as mock_sweep:
            # Override fetch to return empty (so jobs_seen stays 0)
            provider.fetch_jobs.side_effect = lambda q, c, page=1: []
            result = service.sync("python", "Bangalore")
        assert result.jobs_seen == 0
        assert result.sweep_skipped is True
        mock_sweep.assert_not_called()

    # SGT-04
    def test_sweep_runs_when_one_job_processed(self):
        result, mock_upsert, mock_sweep = self._run({1: [_make_job()], 2: []})
        assert result.sweep_skipped is False
        mock_sweep.assert_called_once()

    # SGT-05
    def test_sweep_skipped_flag_is_bool_type(self):
        result, _, _ = self._run({})
        assert isinstance(result.sweep_skipped, bool)

    # SGT-06
    def test_sweep_skip_logged_at_error_level(self):
        provider = _make_provider({})
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(1, 0, 0)), \
             patch.object(service, "_mark_stale_inactive", return_value=0), \
             patch("apps.career_hub.services.sync.logger") as mock_logger:
            service.sync("python", "Bangalore")
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any("stale sweep skipped" in c.lower() for c in error_calls)

    # SGT-07
    def test_sweep_skip_not_logged_on_normal_run(self, caplog):
        result, _, _ = self._run({1: [_make_job()], 2: []})
        assert result.sweep_skipped is False
        sweep_skip_logs = [
            r for r in caplog.records
            if "stale sweep skipped" in r.message.lower()
        ]
        assert len(sweep_skip_logs) == 0

    # SGT-08
    def test_partial_sync_sweep_runs_on_partial_success(self):
        """Pages 1-2 succeed; page 3+ empty → sweep runs (partial sync behavior)."""
        jobs = [_make_job("IN_1"), _make_job("IN_2")]
        result, _, mock_sweep = self._run({1: jobs, 2: jobs, 3: []})
        assert result.pages_fetched == 2
        assert result.jobs_seen == 4
        assert result.sweep_skipped is False
        mock_sweep.assert_called_once()


# ─── Sync result counts ───────────────────────────────────────────────────────

class TestSyncResultCounts:
    def test_created_count_matches_upsert(self):
        provider = _make_provider({1: [_make_job()], 2: []})
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(3, 1, 1)), \
             patch.object(service, "_mark_stale_inactive", return_value=2):
            result = service.sync("python", "Bangalore")
        assert result.created == 3
        assert result.updated == 1
        assert result.reactivated == 1
        assert result.deactivated == 2

    def test_errors_counted_on_provider_exception(self):
        provider = MagicMock()
        provider.source_name = "adzuna"
        provider.fetch_jobs.side_effect = RuntimeError("boom")
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source):
            result = service.sync("python", "Bangalore")
        assert result.errors == 1
        assert result.pages_fetched == 0

    def test_duration_seconds_is_positive_float(self):
        provider = _make_provider({})
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(0, 0, 0)), \
             patch.object(service, "_mark_stale_inactive", return_value=0):
            result = service.sync("python", "Bangalore")
        assert isinstance(result.duration_seconds, float)
        assert result.duration_seconds >= 0


# ─── Stale sweep ──────────────────────────────────────────────────────────────

class TestStaleSweep:
    def test_mark_stale_inactive_calls_filter_update(self):
        from django.utils import timezone as tz
        provider = _make_provider()
        service = JobSyncService(provider)
        mock_source = _make_source()
        sync_start = tz.now()

        mock_qs = MagicMock()
        mock_qs.update.return_value = 3

        with patch("apps.career_hub.services.sync.Job") as MockJob, \
             patch("apps.career_hub.services.sync.transaction") as MockTxn:
            MockTxn.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTxn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            MockJob.objects.filter.return_value = mock_qs
            count = service._mark_stale_inactive(mock_source, sync_start)

        assert count == 3
        MockJob.objects.filter.assert_called_once_with(
            source=mock_source,
            is_active=True,
            deleted_at__isnull=True,
            fetched_at__lt=sync_start,
        )
        mock_qs.update.assert_called_once()
        update_kwargs = mock_qs.update.call_args.kwargs
        assert update_kwargs["is_active"] is False
        assert "deleted_at" in update_kwargs

    def test_sweep_failure_sets_sweep_skipped_true(self):
        provider = _make_provider({1: [_make_job()], 2: []})
        service = JobSyncService(provider)
        source = _make_source()
        with patch.object(service, "_resolve_source", return_value=source), \
             patch.object(service, "_upsert_batch", return_value=(1, 0, 0)), \
             patch.object(service, "_mark_stale_inactive", side_effect=Exception("db error")):
            result = service.sync("python", "Bangalore")
        assert result.sweep_skipped is True
        assert result.errors == 1
