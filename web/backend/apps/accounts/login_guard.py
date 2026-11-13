"""A guessing budget for passwords, on every door that checks one.

Two counters, both in the shared ``signup`` cache (Redis in production, so
every web process sees the same numbers and a restart does not reset them):

* **Per account and address** — ``LOGIN_MAX_FAILURES`` wrong passwords for one
  normalised username from one client address lock that pair for
  ``LOGIN_LOCKOUT_SECONDS``. This is the brute-force control: one machine
  grinding one account.
* **Per address** — ``LOGIN_MAX_FAILURES_PER_IP`` wrong passwords from one
  address, across any usernames, lock that address. This is the spraying
  control: one machine trying a common password against many accounts.

Deliberately *not* a lock on the account alone. Keyed on the username by itself,
anyone could lock any user out of their own account by typing their name
wrong thirty times from anywhere.

It covers both the app's ``/api/auth/login`` and Django admin's login, because
the check lives in :class:`LoginThrottleBackend`, an authentication backend
that runs before the real one: every ``authenticate()`` call made with a request
passes through it. Failures are counted from Django's ``user_login_failed``
signal and a success clears its pair, so the two doors share one budget.

Unlike the sign-up gate this **fails open**: a cache outage must not lock every
user out of signing in. nginx's ``limit_req`` on ``/api/auth/`` and
``/admin/`` is the backstop for that window.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver

from .client_ip import client_ip

#: What a locked-out caller is told — the same whether the password was right.
LOCKED_MESSAGE = "Too many sign-in attempts. Wait a few minutes before trying again."


def _cache():
    return caches["signup"]


def _setting(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def normalise(username: str) -> str:
    return str(username or "").strip().casefold()


def _pair_key(username: str, ip: str) -> str:
    digest = hashlib.sha256(f"{normalise(username)}|{ip}".encode()).hexdigest()[:32]
    return f"login_fail:pair:{digest}"


def _ip_key(ip: str) -> str:
    digest = hashlib.sha256(ip.encode()).hexdigest()[:32]
    return f"login_fail:ip:{digest}"


def is_locked(username: str, request) -> bool:
    """Whether this username from this client may not try a password right now."""
    if request is None:
        return False
    ip = client_ip(request)
    try:
        pair = int(_cache().get(_pair_key(username, ip)) or 0)
        by_ip = int(_cache().get(_ip_key(ip)) or 0)
    except Exception:
        return False  # fail open — see the module docstring
    return pair >= _setting("LOGIN_MAX_FAILURES", 10) or by_ip >= _setting(
        "LOGIN_MAX_FAILURES_PER_IP", 50
    )


def _bump(key: str, window: int) -> None:
    cache = _cache()
    try:
        cache.incr(key)
    except ValueError:
        # No counter yet — `add` so two concurrent first failures cannot each
        # install a fresh window.
        if not cache.add(key, 1, timeout=window):
            cache.incr(key)


def record_failure(username: str, request) -> None:
    if request is None:
        return
    ip = client_ip(request)
    window = _setting("LOGIN_LOCKOUT_SECONDS", 900)
    try:
        _bump(_pair_key(username, ip), window)
        _bump(_ip_key(ip), window)
    except Exception:
        pass  # a lost count is the price of failing open


def clear(username: str, request) -> None:
    """A correct password resets that pair's streak (not the address's)."""
    if request is None:
        return
    try:
        _cache().delete(_pair_key(username, client_ip(request)))
    except Exception:
        pass


class LoginThrottleBackend:
    """Refuses every password check while the caller is locked out.

    Listed first in ``AUTHENTICATION_BACKENDS``. It never authenticates anyone;
    raising ``PermissionDenied`` stops Django trying the real backends at all, so
    a correct password during a lockout is refused exactly like a wrong one and
    the attacker learns nothing from it.

    Deliberately not a ``BaseBackend``: it has no ``get_user``, so Django never
    picks it as the backend a session is restored through (``force_login`` and
    friends choose the first backend that has one).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if (
            request is not None
            and username is not None
            and is_locked(username, request)
        ):
            raise PermissionDenied(LOCKED_MESSAGE)
        return None


@receiver(user_login_failed)
def _count_failure(sender, credentials, request=None, **kwargs):
    record_failure((credentials or {}).get("username", ""), request)


@receiver(user_logged_in)
def _clear_on_success(sender, request, user, **kwargs):
    clear(user.get_username(), request)
