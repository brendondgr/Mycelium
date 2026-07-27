import pytest
from django.core.cache import cache, caches
from django.test import override_settings

# The real ``signup`` cache (sign-up code failures / shadow bans) is Redis, and
# ``signup_gate`` fails closed — so without a broker every registration test would
# read as "banned". Swap it for LocMem, the same trick the Discord tests use.
_TEST_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "signup": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-signup",
    },
}


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Reset DRF throttle counters and sign-up gate state between tests."""
    with override_settings(CACHES=_TEST_CACHES):
        cache.clear()
        caches["signup"].clear()
        yield
        cache.clear()
        caches["signup"].clear()
