import logging
import hashlib
from decimal import Decimal
from typing import Optional

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, QuerySet

from apps.career_hub.models import Job

logger = logging.getLogger(__name__)

_SORT_MAP = {
    "newest": lambda qs: qs.order_by(F("posted_at").desc(nulls_last=True)),
    "oldest": lambda qs: qs.order_by(F("posted_at").asc(nulls_last=True)),
    "salary_high": lambda qs: qs.order_by(
        F("salary_max").desc(nulls_last=True), F("posted_at").desc(nulls_last=True)
    ),
    "salary_low": lambda qs: qs.order_by(
        F("salary_min").asc(nulls_last=True), F("posted_at").desc(nulls_last=True)
    ),
}


class JobSearchService:
    def search(
        self,
        *,
        q: str = "",
        city: str = "",
        work_type: Optional[str] = None,
        source: Optional[str] = None,
        salary_min: Optional[Decimal] = None,
        salary_max: Optional[Decimal] = None,
        sort: str = "newest",
    ) -> QuerySet:
        # Trigger background sync to avoid blocking the search request
        is_syncing = False
        if q or city:
            from django.core.cache import cache
            cache_key_raw = f"{q or 'Software'}_{city or 'India'}"
            cache_key = f"job_sync_{hashlib.md5(cache_key_raw.encode()).hexdigest()}"
            if not cache.get(cache_key):
                try:
                    from celery_app.tasks.career_hub_tasks import sync_jobs_task
                    sync_jobs_task.delay(query=q or "Software", city=city or "India")
                    cache.set(cache_key, True, timeout=90)
                    is_syncing = True
                except Exception as e:
                    logger.error(f"Failed to dispatch background sync task: {e}")
            else:
                is_syncing = True

        qs = Job.objects.filter(is_active=True, is_private=False, deleted_at__isnull=True)

        if q:
            sq = SearchQuery(q, config="english")
            qs = qs.annotate(rank=SearchRank(F("description_tsv"), sq)).filter(
                description_tsv=sq
            )

        if city:
            qs = qs.filter(city__icontains=city)

        if work_type is not None:
            qs = qs.filter(work_type=work_type)

        if source:
            qs = qs.filter(source__slug=source)

        if salary_min is not None:
            qs = qs.filter(salary_max__gte=salary_min)

        if salary_max is not None:
            qs = qs.filter(salary_min__lte=salary_max)

        sort_fn = _SORT_MAP.get(sort, _SORT_MAP["newest"])
        qs = sort_fn(qs)
        
        # Attach the flag so the view can read it
        qs._is_syncing = is_syncing
        return qs.select_related("source")
