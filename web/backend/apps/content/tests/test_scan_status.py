"""The sign-up background-scan flag (`tools.recommendation.scan_status`) and its
surface.

The flag normally lives in a Redis-backed cache so the web process and the Celery
worker share it; here we point every cache alias at LocMemCache so the round-trip
is exercised without a running Redis.
"""

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient
from tools.recommendation.scan_status import (
    clear_paper_scan_inflight,
    is_paper_scan_inflight,
    mark_paper_scan_inflight,
    trigger_paper_scan,
)

_LOCMEM = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "search": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "scan": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=_LOCMEM)
@pytest.mark.django_db
def test_flag_set_read_clear_roundtrip() -> None:
    user = User.objects.create_user("flag", password="x")
    assert is_paper_scan_inflight(user) is False
    mark_paper_scan_inflight(user)
    assert is_paper_scan_inflight(user) is True
    clear_paper_scan_inflight(user)
    assert is_paper_scan_inflight(user) is False


@override_settings(CACHES=_LOCMEM)
@pytest.mark.django_db
def test_trigger_sets_flag_and_enqueues() -> None:
    user = User.objects.create_user("trig", password="x")
    calls: list[str] = []
    assert trigger_paper_scan(user, enqueue=calls.append) is True
    assert calls == ["trig"]
    assert is_paper_scan_inflight(user) is True


@override_settings(CACHES=_LOCMEM)
@pytest.mark.django_db
def test_trigger_clears_flag_when_enqueue_fails() -> None:
    """A broken hand-off (no broker) must not leave the page wedged on "scanning"."""
    user = User.objects.create_user("fail", password="x")

    def boom(_username: str) -> None:
        raise RuntimeError("no broker")

    assert trigger_paper_scan(user, enqueue=boom) is False
    assert is_paper_scan_inflight(user) is False


@override_settings(CACHES=_LOCMEM)
@pytest.mark.django_db
def test_daily_report_exposes_scanning_flag() -> None:
    user = User.objects.create_user("dr", password="x")
    client = APIClient()
    client.force_authenticate(user)

    assert client.get("/api/daily-report/").data["scanning"] is False
    mark_paper_scan_inflight(user)
    assert client.get("/api/daily-report/").data["scanning"] is True


@pytest.mark.django_db
def test_flag_helpers_degrade_when_cache_unavailable(settings) -> None:
    """A Redis outage (here: a bad "scan" backend) degrades to no scanning state."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "scan": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://127.0.0.1:6390/0",  # nothing listening
        },
    }
    user = User.objects.create_user("down", password="x")
    # None of these raise; the flag simply reads as not-in-flight.
    mark_paper_scan_inflight(user)
    assert is_paper_scan_inflight(user) is False
    clear_paper_scan_inflight(user)