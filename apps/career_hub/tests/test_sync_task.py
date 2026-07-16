"""
Unit tests for career_hub Celery tasks.

All service and provider calls are mocked.
"""
import dataclasses
import logging
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.career_hub.services.sync import SyncResult


def _make_result(**kwargs) -> SyncResult:
    defaults = dict(
        provider="adzuna", query="software engineer", city="Bangalore",
        pages_fetched=1, jobs_seen=50, created=40, updated=8,
        reactivated=2, deactivated=3, errors=0,
        duration_seconds=1.23, sweep_skipped=False,
    )
    defaults.update(kwargs)
    return SyncResult(**defaults)


class TestSyncJobsTask:
    def _run_task(self, mock_result: SyncResult):
        """Run sync_jobs_task with the provider and service mocked."""
        from celery_app.tasks.career_hub_tasks import sync_jobs_task

        with patch("apps.career_hub.providers.adzuna.AdzunaProvider") as MockProvider, \
             patch("apps.career_hub.services.sync.JobSyncService") as MockService:
            mock_service_instance = MagicMock()
            mock_service_instance.sync.return_value = mock_result
            MockService.return_value = mock_service_instance
            MockProvider.return_value = MagicMock()

            return sync_jobs_task()

    # TT-01
    def test_task_calls_service_sync(self):
        mock_result = _make_result()
        with patch("apps.career_hub.providers.adzuna.AdzunaProvider") as MockProvider, \
             patch("apps.career_hub.services.sync.JobSyncService") as MockService:
            mock_service_instance = MagicMock()
            mock_service_instance.sync.return_value = mock_result
            MockService.return_value = mock_service_instance

            from celery_app.tasks.career_hub_tasks import sync_jobs_task
            sync_jobs_task()

        mock_service_instance.sync.assert_called_once_with(
            query="software engineer", city="Bangalore", max_pages=1
        )

    # TT-02
    def test_task_returns_dict(self):
        mock_result = _make_result()
        returned = self._run_task(mock_result)
        assert isinstance(returned, dict)
        assert returned["provider"] == "adzuna"
        assert returned["sweep_skipped"] is False
        assert returned["created"] == 40

    def test_task_returned_dict_matches_result(self):
        mock_result = _make_result(created=7, deactivated=2)
        returned = self._run_task(mock_result)
        expected = dataclasses.asdict(mock_result)
        assert returned == expected

    # TT-01 (sweep_skipped path)
    def test_task_logs_sweep_skipped_at_error_level(self, caplog):
        mock_result = _make_result(sweep_skipped=True, pages_fetched=0, jobs_seen=0)
        with caplog.at_level(logging.ERROR, logger="celery_app.tasks.career_hub_tasks"):
            self._run_task(mock_result)
        error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
        assert any("sweep_skipped=True" in m for m in error_messages)

    def test_task_does_not_raise_on_sweep_skipped(self):
        mock_result = _make_result(sweep_skipped=True, pages_fetched=0, jobs_seen=0)
        returned = self._run_task(mock_result)
        assert returned is not None
        assert returned["sweep_skipped"] is True
