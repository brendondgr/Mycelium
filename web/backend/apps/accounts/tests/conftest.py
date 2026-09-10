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


def verified(user):
    """Mark a test user's account activated, and return it.

    Verifying an email is what activates an account, and an unactivated one is
    refused by every endpoint that stands up an organization — creating a lab,
    editing a lab or department profile, sending an invitation. Tests about *those*
    rules should not be re-testing the activation gate, which has its own file
    (``test_email_verification.py``), so they say so here in one call.
    """
    profile = user.profile
    profile.is_verified = True
    profile.save(update_fields=["is_verified"])
    return user
