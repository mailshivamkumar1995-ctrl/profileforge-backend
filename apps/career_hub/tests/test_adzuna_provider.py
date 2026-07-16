"""
Unit tests for AdzunaProvider and its helpers.

All HTTP calls are mocked — no network access, no database access.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests

from apps.career_hub.providers.adzuna import (
    AdzunaProvider,
    _map_work_type,
    _parse_datetime,
    _parse_salary,
)
from apps.career_hub.providers.base import NormalizedJob


# ─── Fixtures ─────────────────────────────────────────────────────────────────

VALID_JOB = {
    "__CLASS__": "Job",
    "id": "4678990100",
    "title": "Senior Python Developer",
    "company": {"display_name": "TechCorp Pvt Ltd"},
    "description": "We are looking for a senior Python developer to build scalable APIs.",
    "redirect_url": "https://www.adzuna.in/details/jobs/4678990100",
    "location": {"display_name": "Bangalore"},
    "salary_min": 800000.0,
    "salary_max": 1200000.0,
    "created": "2026-06-01T10:00:00Z",
}

VALID_RESPONSE = {
    "__CLASS__": "SearchResults",
    "results": [VALID_JOB],
    "count": 1,
    "mean": 1000000,
}

EMPTY_RESPONSE = {
    "__CLASS__": "SearchResults",
    "results": [],
    "count": 0,
    "mean": 0,
}


def _make_mock_response(status_code: int, json_data: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


# ─── Provider properties ──────────────────────────────────────────────────────

class TestAdzunaProviderProperties:
    def test_source_name(self):
        assert AdzunaProvider().source_name == "adzuna"

    def test_supports_location_filter(self):
        assert AdzunaProvider().supports_location_filter is True

    def test_supports_salary_filter(self):
        assert AdzunaProvider().supports_salary_filter is False


# ─── fetch_jobs ───────────────────────────────────────────────────────────────

class TestFetchJobs:
    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_successful_fetch_returns_normalized_jobs(self, mock_get):
        mock_get.return_value = _make_mock_response(200, VALID_RESPONSE)
        jobs = AdzunaProvider().fetch_jobs("python developer", "Bangalore", page=1)
        assert len(jobs) == 1
        job = jobs[0]
        assert isinstance(job, NormalizedJob)
        assert job.external_id == "IN_4678990100"
        assert job.title == "Senior Python Developer"
        assert job.company == "TechCorp Pvt Ltd"
        assert job.city == "Bangalore"
        assert job.is_private is False

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_empty_results_returns_empty_list(self, mock_get):
        mock_get.return_value = _make_mock_response(200, EMPTY_RESPONSE)
        jobs = AdzunaProvider().fetch_jobs("python developer", "Bangalore")
        assert jobs == []

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_429_rate_limit_returns_empty_list(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        jobs = AdzunaProvider().fetch_jobs("python", "Delhi")
        assert jobs == []

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_http_500_returns_empty_list(self, mock_get):
        mock_get.return_value = _make_mock_response(500, {})
        jobs = AdzunaProvider().fetch_jobs("python", "Mumbai")
        assert jobs == []

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_timeout_returns_empty_list(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout()
        jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert jobs == []

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_connection_error_returns_empty_list(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError()
        jobs = AdzunaProvider().fetch_jobs("python", "Hyderabad")
        assert jobs == []

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_malformed_job_is_skipped_others_returned(self, mock_get):
        malformed = {"id": None, "redirect_url": None}
        response = {"results": [malformed, VALID_JOB], "count": 2}
        mock_get.return_value = _make_mock_response(200, response)
        jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert len(jobs) == 1
        assert jobs[0].external_id == "IN_4678990100"

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_page_2_uses_correct_url(self, mock_get):
        mock_get.return_value = _make_mock_response(200, EMPTY_RESPONSE)
        AdzunaProvider().fetch_jobs("python", "Bangalore", page=2)
        call_args = mock_get.call_args
        assert call_args[0][0].endswith("/2")

    @patch("apps.career_hub.providers.adzuna.requests.get")
    def test_multiple_jobs_all_returned(self, mock_get):
        job2 = dict(VALID_JOB, id="999", title="Backend Engineer")
        response = {"results": [VALID_JOB, job2], "count": 2}
        mock_get.return_value = _make_mock_response(200, response)
        jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert len(jobs) == 2

    def test_missing_credentials_returns_empty_list(self):
        from django.test import override_settings
        with override_settings(ADZUNA_APP_ID="", ADZUNA_APP_KEY=""):
            jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert jobs == []

    def test_missing_app_id_only_returns_empty_list(self):
        from django.test import override_settings
        with override_settings(ADZUNA_APP_ID="", ADZUNA_APP_KEY="some-key"):
            jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert jobs == []


# ─── _normalize (via fetch_jobs) ──────────────────────────────────────────────

class TestNormalize:
    def _fetch_single(self, raw_job: dict) -> NormalizedJob:
        response = {"results": [raw_job], "count": 1}
        with patch("apps.career_hub.providers.adzuna.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200, response)
            jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert len(jobs) == 1
        return jobs[0]

    def test_external_id_prefixed_with_IN(self):
        job = self._fetch_single(VALID_JOB)
        assert job.external_id == "IN_4678990100"

    def test_is_private_always_false(self):
        job = self._fetch_single(VALID_JOB)
        assert job.is_private is False

    def test_title_truncated_to_200_chars(self):
        long_title = "A" * 300
        raw = dict(VALID_JOB, title=long_title)
        job = self._fetch_single(raw)
        assert len(job.title) == 200

    def test_company_truncated_to_200_chars(self):
        raw = dict(VALID_JOB, company={"display_name": "B" * 300})
        job = self._fetch_single(raw)
        assert len(job.company) == 200

    def test_description_truncated_to_2000_chars(self):
        raw = dict(VALID_JOB, description="D" * 2500)
        job = self._fetch_single(raw)
        assert len(job.description) == 2000

    def test_salary_zero_normalized_to_none(self):
        raw = dict(VALID_JOB, salary_min=0.0, salary_max=0.0)
        job = self._fetch_single(raw)
        assert job.salary_min is None
        assert job.salary_max is None

    def test_salary_absent_is_none(self):
        raw = {k: v for k, v in VALID_JOB.items() if k not in ("salary_min", "salary_max")}
        job = self._fetch_single(raw)
        assert job.salary_min is None
        assert job.salary_max is None

    def test_salary_valid_positive_values(self):
        raw = dict(VALID_JOB, salary_min=500000.0, salary_max=900000.0)
        job = self._fetch_single(raw)
        assert job.salary_min == Decimal("500000.0")
        assert job.salary_max == Decimal("900000.0")

    def test_currency_defaults_to_inr(self):
        raw = {k: v for k, v in VALID_JOB.items() if k != "salary_currency"}
        job = self._fetch_single(raw)
        assert job.salary_currency == "INR"

    def test_missing_redirect_url_skips_job(self):
        raw = dict(VALID_JOB, redirect_url="")
        response = {"results": [raw], "count": 1}
        with patch("apps.career_hub.providers.adzuna.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200, response)
            jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert jobs == []

    def test_missing_id_skips_job(self):
        raw = {k: v for k, v in VALID_JOB.items() if k != "id"}
        response = {"results": [raw], "count": 1}
        with patch("apps.career_hub.providers.adzuna.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200, response)
            jobs = AdzunaProvider().fetch_jobs("python", "Bangalore")
        assert jobs == []

    def test_missing_location_city_is_none(self):
        raw = {k: v for k, v in VALID_JOB.items() if k != "location"}
        job = self._fetch_single(raw)
        assert job.city is None


# ─── _map_work_type ───────────────────────────────────────────────────────────

class TestMapWorkType:
    def test_remote_keyword_in_title(self):
        raw = {"title": "Remote Python Developer", "description": ""}
        assert _map_work_type(raw) == "remote"

    def test_work_from_home_in_description(self):
        raw = {"title": "Python Developer", "description": "This is a work from home position."}
        assert _map_work_type(raw) == "remote"

    def test_wfh_abbreviation(self):
        raw = {"title": "Backend Engineer - WFH", "description": ""}
        assert _map_work_type(raw) == "remote"

    def test_fully_remote_phrase(self):
        raw = {"title": "Fully Remote Senior Engineer", "description": ""}
        assert _map_work_type(raw) == "remote"

    def test_hybrid_in_description(self):
        raw = {"title": "Python Developer", "description": "Hybrid work model — 3 days office."}
        assert _map_work_type(raw) == "hybrid"

    def test_onsite_in_title(self):
        raw = {"title": "On-site Java Developer", "description": ""}
        assert _map_work_type(raw) == "onsite"

    def test_in_office_in_description(self):
        raw = {"title": "Engineer", "description": "Must work in office 5 days a week."}
        assert _map_work_type(raw) == "onsite"

    def test_default_is_hybrid(self):
        raw = {"title": "Software Engineer", "description": "Exciting opportunity at a fast-growing startup."}
        assert _map_work_type(raw) == "hybrid"

    def test_remote_takes_priority_over_onsite(self):
        raw = {"title": "Remote Engineer", "description": "Initially onsite then remote."}
        assert _map_work_type(raw) == "remote"

    def test_none_title_and_description(self):
        raw = {"title": None, "description": None}
        assert _map_work_type(raw) == "hybrid"


# ─── _parse_salary ────────────────────────────────────────────────────────────

class TestParseSalary:
    def test_valid_float(self):
        assert _parse_salary(800000.0) == Decimal("800000.0")

    def test_valid_integer(self):
        assert _parse_salary(500000) == Decimal("500000")

    def test_zero_returns_none(self):
        assert _parse_salary(0.0) is None

    def test_zero_int_returns_none(self):
        assert _parse_salary(0) is None

    def test_none_returns_none(self):
        assert _parse_salary(None) is None

    def test_negative_returns_none(self):
        assert _parse_salary(-1000) is None

    def test_invalid_string_returns_none(self):
        assert _parse_salary("not-a-number") is None

    def test_valid_string_number(self):
        assert _parse_salary("750000") == Decimal("750000")


# ─── _parse_datetime ──────────────────────────────────────────────────────────

class TestParseDatetime:
    def test_valid_iso_with_z_suffix(self):
        result = _parse_datetime("2026-06-01T10:00:00Z")
        assert result == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_valid_iso_with_offset(self):
        result = _parse_datetime("2026-06-01T10:00:00+05:30")
        assert result is not None
        assert result.year == 2026

    def test_none_returns_none(self):
        assert _parse_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_datetime("") is None

    def test_invalid_format_returns_none(self):
        assert _parse_datetime("01-06-2026") is None

    def test_garbage_string_returns_none(self):
        assert _parse_datetime("not-a-date") is None
