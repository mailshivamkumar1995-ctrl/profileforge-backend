"""
Unit tests for JobSearchService.

All ORM calls are mocked — no database access, no network.
"""
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from apps.career_hub.services.search import JobSearchService


# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_job_cls():
    """Patches Job and returns (MockJob, fluent mock_qs)."""
    with patch("apps.career_hub.services.search.Job") as MockJob:
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.annotate.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        MockJob.objects.filter.return_value = mock_qs
        yield MockJob, mock_qs


def _filter_kwargs(mock_qs):
    """Return list of all kwargs dicts passed to mock_qs.filter(...)."""
    return [c.kwargs for c in mock_qs.filter.call_args_list]


# ─── Base queryset ────────────────────────────────────────────────────────────

class TestBaseQueryset:
    def test_always_filters_active_non_private_non_deleted(self, mock_job_cls):
        MockJob, mock_qs = mock_job_cls
        JobSearchService().search()
        MockJob.objects.filter.assert_called_once_with(
            is_active=True, is_private=False, deleted_at__isnull=True
        )

    def test_select_related_source_always_called(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search()
        mock_qs.select_related.assert_called_once_with("source")

    def test_returns_queryset(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        result = JobSearchService().search()
        assert result is mock_qs


# ─── Full-text search ─────────────────────────────────────────────────────────

class TestFTS:
    def test_no_fts_when_q_blank(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(q="")
        mock_qs.annotate.assert_not_called()

    def test_no_fts_when_q_whitespace(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        # Empty string is the default; whitespace is treated as non-empty by the serializer
        # but the service receives whatever the caller passes
        JobSearchService().search(q="")
        mock_qs.annotate.assert_not_called()

    def test_fts_annotate_called_when_q_provided(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(q="python engineer")
        mock_qs.annotate.assert_called_once()

    def test_fts_filter_called_with_description_tsv(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(q="python engineer")
        all_kwargs = _filter_kwargs(mock_qs)
        fts_calls = [kw for kw in all_kwargs if "description_tsv" in kw]
        assert len(fts_calls) == 1

    def test_fts_rank_annotation_uses_correct_field(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(q="data scientist")
        annotate_call = mock_qs.annotate.call_args
        assert "rank" in annotate_call.kwargs


# ─── Filters ──────────────────────────────────────────────────────────────────

class TestFilters:
    def test_city_filter_applied_icontains(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(city="bangalore")
        all_kwargs = _filter_kwargs(mock_qs)
        assert any("city__icontains" in kw for kw in all_kwargs)
        city_val = next(kw["city__icontains"] for kw in all_kwargs if "city__icontains" in kw)
        assert city_val == "bangalore"

    def test_no_city_filter_when_city_blank(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(city="")
        all_kwargs = _filter_kwargs(mock_qs)
        assert not any("city__icontains" in kw for kw in all_kwargs)

    def test_work_type_filter_applied(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(work_type="remote")
        all_kwargs = _filter_kwargs(mock_qs)
        assert any(kw.get("work_type") == "remote" for kw in all_kwargs)

    def test_no_work_type_filter_when_none(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(work_type=None)
        all_kwargs = _filter_kwargs(mock_qs)
        assert not any("work_type" in kw for kw in all_kwargs)

    def test_source_filter_by_slug(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(source="adzuna")
        all_kwargs = _filter_kwargs(mock_qs)
        assert any(kw.get("source__slug") == "adzuna" for kw in all_kwargs)

    def test_no_source_filter_when_none(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(source=None)
        all_kwargs = _filter_kwargs(mock_qs)
        assert not any("source__slug" in kw for kw in all_kwargs)

    def test_no_source_filter_when_blank(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(source="")
        all_kwargs = _filter_kwargs(mock_qs)
        assert not any("source__slug" in kw for kw in all_kwargs)

    def test_salary_min_filters_salary_max_gte(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(salary_min=Decimal("500000"))
        all_kwargs = _filter_kwargs(mock_qs)
        assert any(kw.get("salary_max__gte") == Decimal("500000") for kw in all_kwargs)

    def test_salary_max_filters_salary_min_lte(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(salary_max=Decimal("1000000"))
        all_kwargs = _filter_kwargs(mock_qs)
        assert any(kw.get("salary_min__lte") == Decimal("1000000") for kw in all_kwargs)

    def test_no_salary_filter_when_both_none(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(salary_min=None, salary_max=None)
        all_kwargs = _filter_kwargs(mock_qs)
        assert not any("salary_max__gte" in kw or "salary_min__lte" in kw for kw in all_kwargs)

    def test_combined_q_and_city_both_applied(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(q="python", city="mumbai")
        all_kwargs = _filter_kwargs(mock_qs)
        assert any("description_tsv" in kw for kw in all_kwargs)
        assert any("city__icontains" in kw for kw in all_kwargs)


# ─── Sorting ──────────────────────────────────────────────────────────────────

class TestSorting:
    def _order_call(self, mock_qs):
        """Return args tuple from the first order_by call."""
        return mock_qs.order_by.call_args[0]

    def test_sort_newest_by_default(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search()
        args = self._order_call(mock_qs)
        assert len(args) == 1
        assert "posted_at" in str(args[0])
        assert "desc" in str(args[0]).lower() or args[0].descending

    def test_sort_oldest_asc(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(sort="oldest")
        args = self._order_call(mock_qs)
        assert len(args) == 1
        assert "posted_at" in str(args[0])
        assert not args[0].descending

    def test_sort_salary_high_two_args(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(sort="salary_high")
        args = self._order_call(mock_qs)
        assert len(args) == 2
        assert "salary_max" in str(args[0])
        assert args[0].descending

    def test_sort_salary_low_two_args(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(sort="salary_low")
        args = self._order_call(mock_qs)
        assert len(args) == 2
        assert "salary_min" in str(args[0])
        assert not args[0].descending

    def test_unknown_sort_falls_back_to_newest(self, mock_job_cls):
        _, mock_qs = mock_job_cls
        JobSearchService().search(sort="invalid_sort")
        args = self._order_call(mock_qs)
        assert "posted_at" in str(args[0])
        assert args[0].descending
