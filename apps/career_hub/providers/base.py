from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional


@dataclass
class NormalizedJob:
    external_id: str
    title: str
    company: str
    description: str
    apply_url: str
    city: Optional[str] = None
    work_type: Literal["remote", "hybrid", "onsite"] = "hybrid"
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    salary_currency: str = "INR"
    posted_at: Optional[datetime] = None
    is_private: bool = False


class JobProvider(ABC):
    """Abstract interface for all job data source providers.

    Business logic (normalization, deduplication, FTS indexing) operates on
    NormalizedJob — never on raw provider response objects.
    """

    @abstractmethod
    def fetch_jobs(self, query: str, city: str, page: int = 1) -> List[NormalizedJob]:
        """Fetch a page of jobs matching query in city."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique slug identifying this provider (e.g. 'adzuna')."""
        ...

    @property
    @abstractmethod
    def supports_location_filter(self) -> bool:
        """True if the provider supports city-level location filtering."""
        ...

    @property
    @abstractmethod
    def supports_salary_filter(self) -> bool:
        """True if the provider reliably returns salary data."""
        ...
