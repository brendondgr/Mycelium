"""Audit logging for the Discord path — a thin wrapper over the accounts audit log.

Reuses ``apps.accounts.services.record_audit_event`` (no new table, per the plan
§3.1). Two rules this wrapper enforces so the audit trail never leaks a reachable
identifier:

* ``discord_user_id`` is never stored raw — only its sha256 (``hash_discord_id``).
* metadata carries no plaintext codes or tokens (callers must not pass them).
"""

from __future__ import annotations

import hashlib
from typing import Any

from apps.accounts.services import record_audit_event


def hash_discord_id(discord_user_id: str | int | None) -> str:
    """Stable, non-reversible tag for a snowflake, safe to store/emit."""
    if not discord_user_id:
        return ""
    return hashlib.sha256(str(discord_user_id).encode("utf-8")).hexdigest()


def discord_audit(
    *,
    action: str,
    actor=None,
    discord_user_id: str | int | None = None,
    guild_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record one Discord audit event with the snowflake hashed."""
    meta: dict[str, Any] = dict(metadata or {})
    if discord_user_id:
        meta["discord_user_hash"] = hash_discord_id(discord_user_id)
    if guild_id:
        meta["guild_id"] = str(guild_id)
    record_audit_event(
        actor=actor,
        action=action,
        target_type="discord",
        target_id=meta.get("guild_id", ""),
        metadata=meta,
    )
