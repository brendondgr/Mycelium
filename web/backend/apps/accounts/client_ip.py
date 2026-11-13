"""The one rule for "which address is this request from".

Every per-client control — DRF throttles, the sign-in lockout, the sign-up
code's shadow ban, the demo's per-visitor cap — keys on the client's address,
so they must all read it the same way, and none of them may read a header the
client wrote.

The stack puts exactly one proxy in front of Django: nginx, which resolves any
trusted front proxy itself and then *sets* ``X-Forwarded-For: $remote_addr``.
So the right-most hop is the address nginx saw, and everything to its left (if
anything) is whatever the client claimed. DRF's ``NUM_PROXIES = 1`` reads the
same hop; this module is that rule for the code that is not a DRF throttle.
``CF-Connecting-IP`` is not read: nginx strips it, and a header a tunnel adds is
a header anyone can add when the tunnel is not there.
"""

from __future__ import annotations

from rest_framework.settings import api_settings


def client_ip(request) -> str:
    """The client address, as the proxy chain in front of Django saw it."""
    meta = getattr(request, "META", {}) or {}
    remote = (meta.get("REMOTE_ADDR") or "").strip()
    forwarded = meta.get("HTTP_X_FORWARDED_FOR") or ""
    proxies = api_settings.NUM_PROXIES
    if forwarded and proxies:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-min(int(proxies), len(hops))]
    return remote or "unknown"
