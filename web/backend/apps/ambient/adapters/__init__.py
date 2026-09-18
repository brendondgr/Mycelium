"""Platform adapters over one shared ledger.

The registry exists so a caller can find the adapter for a platform without
importing it — Plan 02's ingest endpoint names a platform, not a class. Discord
registers itself there; Slack, Teams and transcripts will register the same way.
"""

from __future__ import annotations

from .base import Adapter, PlatformEvent

_REGISTRY: dict[str, Adapter] = {}


def register(adapter: Adapter) -> Adapter:
    """Make ``adapter`` the adapter for its platform. Re-registering replaces."""
    _REGISTRY[adapter.platform] = adapter
    return adapter


def adapter_for(platform: str) -> Adapter | None:
    """The registered adapter for ``platform``, or None if nothing speaks it."""
    return _REGISTRY.get(platform)


def registered() -> dict[str, Adapter]:
    """Every registered adapter, keyed by platform. A copy; edit the registry
    through :func:`register`."""
    return dict(_REGISTRY)


__all__ = ["Adapter", "PlatformEvent", "adapter_for", "register", "registered"]
