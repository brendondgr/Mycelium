"""Which rows are the demo world, and how the rest of the instance leaves them out.

Demo people are ordinary users, recognised by one mark: an address under
:data:`DOMAIN`. ``.invalid`` is reserved by RFC 2606, so no mail the product
sends can ever reach anyone, and the domain is distinct from ``seed_demo``'s
(``demo.mycelium.test``) and ``seed_fsu_sc``'s, so no command's teardown
touches another's rows.
"""

from __future__ import annotations

import time

from django.conf import settings

#: Every demo person's address ends in ``@`` + this.
DOMAIN = "showcase.mycelium.invalid"

_CACHE_SECONDS = 30
_cache: dict[str, object] = {"at": 0.0, "world": None}


def is_enabled() -> bool:
    return bool(getattr(settings, "DEMO_ENABLED", False))


def current_world(*, fresh: bool = False):
    """The built :class:`~apps.demo.models.DemoWorld`, or ``None``.

    Read on every demo request, so it is held for a few seconds per process;
    ``demo build`` and ``demo delete`` clear it in their own process, and other
    processes see the change within :data:`_CACHE_SECONDS`.
    """
    from .models import DemoWorld

    now = time.monotonic()
    if not fresh and now - float(_cache["at"]) < _CACHE_SECONDS:
        return _cache["world"]
    world = (
        DemoWorld.objects.select_related("viewer", "lab", "department")
        .filter(key="default")
        .first()
    )
    _cache.update(at=now, world=world)
    return world


def forget() -> None:
    """Drop the cached world (after a build or delete)."""
    _cache.update(at=0.0, world=None)


def is_demo_email(email: str) -> bool:
    return (email or "").lower().endswith("@" + DOMAIN)


def is_demo_user(user) -> bool:
    return bool(user is not None and is_demo_email(getattr(user, "email", "")))


def exclude_demo_users(queryset, field: str = "email"):
    """``queryset`` without demo people; ``field`` is the path to their email
    (``"email"`` for users, ``"user__email"`` for profiles and memberships)."""
    return queryset.exclude(**{f"{field}__iendswith": "@" + DOMAIN})
