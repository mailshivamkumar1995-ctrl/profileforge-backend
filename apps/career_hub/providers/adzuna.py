import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

import requests
from django.conf import settings

from apps.career_hub.providers.base import JobProvider, NormalizedJob

logger = logging.getLogger(__name__)

_ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs/in/search"
_RESULTS_PER_PAGE = 50
_REQUEST_TIMEOUT = 10  # seconds

_REMOTE_KEYWORDS = ("remote", "work from home", "wfh", "fully remote")
_HYBRID_KEYWORDS = ("hybrid",)
_ONSITE_KEYWORDS = ("on-site", "onsite", "in office", "in-office", "office only")


class AdzunaProvider(JobProvider):
    """Adzuna India job data provider.

    Credentials are read from settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY.
    Returns an empty list on any API failure — callers must tolerate empty results.
    """

    @property
    def source_name(self) -> str:
        return "adzuna"

    @property
    def supports_location_filter(self) -> bool:
        return True

    @property
    def supports_salary_filter(self) -> bool:
        # PRE-01: 0% salary coverage verified for Bangalore; treat salary data as advisory.
        return False

    def fetch_jobs(self, query: str, city: str, page: int = 1) -> List[NormalizedJob]:
        app_id = getattr(settings, "ADZUNA_APP_ID", "")
        app_key = getattr(settings, "ADZUNA_APP_KEY", "")

        if not app_id or not app_key:
            logger.error("AdzunaProvider: ADZUNA_APP_ID or ADZUNA_APP_KEY not configured")
            return []

        try:
            payload = self._call_api(app_id, app_key, query, city, page)
        except requests.exceptions.Timeout:
            logger.warning(
                "AdzunaProvider: request timed out (query=%r city=%r page=%d)",
                query, city, page,
            )
            return []
        except requests.exceptions.RequestException as exc:
            logger.error(
                "AdzunaProvider: request failed (query=%r city=%r page=%d): %s",
                query, city, page, exc,
            )
            return []

        raw_results = payload.get("results") or []
        if not raw_results:
            return []

        jobs: List[NormalizedJob] = []
        for raw in raw_results:
            try:
                job = self._normalize(raw)
                if job is not None:
                    jobs.append(job)
            except Exception as exc:
                logger.warning(
                    "AdzunaProvider: failed to normalize job id=%r: %s",
                    raw.get("id"), exc,
                )
        return jobs

    def _call_api(self, app_id: str, app_key: str, query: str, city: str, page: int) -> dict:
        url = f"{_ADZUNA_BASE_URL}/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "where": city,
            "results_per_page": _RESULTS_PER_PAGE,
            "content-type": "application/json",
        }
        response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)

        if response.status_code == 429:
            logger.warning("AdzunaProvider: rate limit hit (429) for page=%d", page)
            return {"results": []}

        response.raise_for_status()
        return response.json()

    def _normalize(self, raw: dict) -> Optional[NormalizedJob]:
        job_id = raw.get("id")
        if not job_id:
            logger.warning("AdzunaProvider: job missing 'id' field, skipping")
            return None

        apply_url = (raw.get("redirect_url") or "").strip()
        if not apply_url:
            logger.warning("AdzunaProvider: job %r missing redirect_url, skipping", job_id)
            return None

        salary_min = _parse_salary(raw.get("salary_min"))
        salary_max = _parse_salary(raw.get("salary_max"))

        return NormalizedJob(
            external_id=f"IN_{job_id}",
            title=(raw.get("title") or "")[:200],
            company=((raw.get("company") or {}).get("display_name") or "")[:200],
            description=(raw.get("description") or "")[:2000],
            apply_url=apply_url[:500],
            city=((raw.get("location") or {}).get("display_name") or None),
            work_type=_map_work_type(raw),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=(raw.get("salary_currency") or "INR")[:3],
            posted_at=_parse_datetime(raw.get("created")),
            is_private=False,
        )


def _map_work_type(raw: dict) -> str:
    """Infer work_type from job title and description text.

    Adzuna India does not expose a structured work-location field.
    Keyword scanning is a best-effort heuristic; default is 'hybrid'.
    """
    title = (raw.get("title") or "").lower()
    description = (raw.get("description") or "").lower()
    text = f"{title} {description}"

    if any(kw in text for kw in _REMOTE_KEYWORDS):
        return "remote"
    if any(kw in text for kw in _ONSITE_KEYWORDS):
        return "onsite"
    if any(kw in text for kw in _HYBRID_KEYWORDS):
        return "hybrid"
    return "hybrid"


def _parse_salary(value) -> Optional[Decimal]:
    """Parse salary value; return None when absent, zero, or unparseable.

    Adzuna returns 0.0 when salary is not available (PRE-01: 0% coverage in Bangalore).
    """
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        return d if d > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse Adzuna ISO 8601 datetime string (e.g. '2026-06-01T10:00:00Z')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
