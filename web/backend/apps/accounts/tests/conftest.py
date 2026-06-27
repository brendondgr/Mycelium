import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Reset DRF throttle counters between tests (kept in the default cache)."""
    cache.clear()
    yield
    cache.clear()
