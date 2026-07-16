"""
Tests for CareerHubSearchThrottle on JobListView.

Strategy:
- Structural tests: verify throttle is wired to the view, inherits _FailClosedMixin,
  and uses the correct scope — no cache required.
- Functional tests: override the cache backend to LocMemCache (no Redis needed) and
  patch the throttle rate directly via CareerHubSearchThrottle.rate (bypasses the
  settings lookup in SimpleRateThrottle.__init__) to set a 2/minute ceiling.
  Cache is cleared before each test to isolate throttle counter state.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.throttling import UserRateThrottle

from apps.career_hub.views import JobListView
from core.throttles import CareerHubSearchThrottle, _FailClosedMixin
from rest_framework.test import APIRequestFactory, force_authenticate


factory = APIRequestFactory()

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


def _make_user(pk=None):
    user = MagicMock()
    user.is_authenticated = True
    # pk must be a concrete value — UserRateThrottle uses str(user.pk) as cache key
    user.pk = pk or uuid.uuid4()
    return user


def _job_list_get(user):
    """Make a single GET /jobs/ request as the given user."""
    with patch("apps.career_hub.views.JobSearchService") as MockSvc:
        MockSvc.return_value.search.return_value = []
        request = factory.get("/api/v1/career-hub/jobs/")
        force_authenticate(request, user=user)
        return JobListView.as_view()(request)


# ─── Structural tests ─────────────────────────────────────────────────────────

class TestCareerHubSearchThrottleStructure:
    def test_throttle_class_is_configured_on_job_list_view(self):
        assert CareerHubSearchThrottle in JobListView.throttle_classes

    def test_throttle_is_only_throttle_on_job_list_view(self):
        assert JobListView.throttle_classes == [CareerHubSearchThrottle]

    def test_throttle_inherits_fail_closed_mixin(self):
        assert issubclass(CareerHubSearchThrottle, _FailClosedMixin)

    def test_throttle_scope_is_career_hub_search(self):
        assert CareerHubSearchThrottle.scope == "career_hub_search"

    def test_throttle_is_user_scoped(self):
        assert issubclass(CareerHubSearchThrottle, UserRateThrottle)


# ─── Settings tests ───────────────────────────────────────────────────────────

class TestCareerHubSearchThrottleSettings:
    def test_career_hub_search_rate_is_in_throttle_rates(self):
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        assert "career_hub_search" in rates

    def test_career_hub_search_rate_default_is_60_per_minute(self):
        from django.conf import settings
        rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["career_hub_search"]
        assert rate == "60/minute"


# ─── Functional tests ─────────────────────────────────────────────────────────
# override_settings as a class decorator only works on SimpleTestCase subclasses.
# We use it as a context manager inside each test method instead.
# The throttle rate is patched at the class level via patch.object so that
# SimpleRateThrottle.__init__ uses the patched rate directly (bypassing settings).

class TestCareerHubSearchThrottleFunctional:
    def setup_method(self):
        cache.clear()

    def test_first_request_returns_200(self):
        with (
            override_settings(CACHES=LOCMEM_CACHE),
            patch.object(CareerHubSearchThrottle, "rate", "2/minute", create=True),
        ):
            cache.clear()
            response = _job_list_get(_make_user())
        assert response.status_code == 200

    def test_request_within_limit_returns_200(self):
        user = _make_user()
        with (
            override_settings(CACHES=LOCMEM_CACHE),
            patch.object(CareerHubSearchThrottle, "rate", "2/minute", create=True),
        ):
            cache.clear()
            _job_list_get(user)
            response = _job_list_get(user)
        assert response.status_code == 200

    def test_request_exceeding_limit_returns_429(self):
        user = _make_user()
        with (
            override_settings(CACHES=LOCMEM_CACHE),
            patch.object(CareerHubSearchThrottle, "rate", "2/minute", create=True),
        ):
            cache.clear()
            _job_list_get(user)
            _job_list_get(user)
            response = _job_list_get(user)
        assert response.status_code == 429

    def test_different_users_have_independent_limits(self):
        user_a = _make_user()
        user_b = _make_user()
        with (
            override_settings(CACHES=LOCMEM_CACHE),
            patch.object(CareerHubSearchThrottle, "rate", "2/minute", create=True),
        ):
            cache.clear()
            _job_list_get(user_a)
            _job_list_get(user_a)
            _job_list_get(user_a)  # user_a exhausted
            response = _job_list_get(user_b)  # user_b unaffected
        assert response.status_code == 200

    def test_throttle_fail_closed_on_cache_error(self):
        """_FailClosedMixin returns False when the underlying allow_request raises."""
        class _BrokenBase:
            def allow_request(self, request, view):
                raise Exception("Redis down")

        class _TestThrottle(_FailClosedMixin, _BrokenBase):
            pass

        request = MagicMock()
        view = MagicMock()
        broken = _TestThrottle()
        assert broken.allow_request(request, view) is False
