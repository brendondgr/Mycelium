"""Configuration for Mylo, read from ``.env-mylo`` at the repository root.

The file carries the bot token (``DISCORD_API_KEY``) and the error channel id
(``ERROR_CHANNEL``). Optional settings: a separate summary channel, a dev guild
for instant slash-command syncing, and owner ids for owner-only commands.

Two consumers with different failure tolerance:

- The error reporter (:mod:`mylo.reporting`) must NEVER crash the daily run, so
  it treats missing credentials as "reporting disabled" and only logs a warning.
- The gateway bot (:mod:`mylo.bot`) must fail fast — a bot with no token is
  useless — so it calls :meth:`MyloConfig.require_bot`.

Parsing is dependency-free on purpose: the reporter has to work in the bare root
runner environment without importing anything beyond the standard library.
Values already present in ``os.environ`` win over the file, so a systemd unit or
a shell can override any setting.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

#: ``.env-mylo`` lives next to ``.env`` at the repository root (one level up).
ENV_FILE = Path(__file__).resolve().parent.parent / ".env-mylo"


class ConfigError(RuntimeError):
    """Raised when required Mylo configuration is missing or malformed."""


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` env file. No third-party dependency.

    Blank lines and ``#`` comments are ignored; surrounding single/double quotes
    are stripped. A missing or unreadable file yields an empty mapping — the
    caller decides whether that is fatal.
    """
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = raw_value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True, slots=True)
class MyloConfig:
    """Resolved Mylo settings. Fields may be empty when ``.env-mylo`` is absent."""

    token: str
    error_channel_id: int | None
    summary_channel_id: int | None = None
    dev_guild_id: int | None = None
    owner_ids: frozenset[int] = field(default_factory=frozenset)
    #: Stage B — server-wide listening. Off unless this is set **and** the
    #: Message Content privileged intent is granted in the Developer Portal.
    #: Without the intent Discord sends empty message bodies, so setting this
    #: alone changes nothing; both halves are required on purpose, so a portal
    #: toggle nobody flipped shows up as "off" rather than as an empty ledger.
    listen_enabled: bool = False

    @property
    def reporting_enabled(self) -> bool:
        """True when the reporter has both a token and a destination channel."""
        return bool(self.token) and self.error_channel_id is not None

    @property
    def is_dev(self) -> bool:
        """Dev mode syncs slash commands to a test guild instead of globally."""
        return self.dev_guild_id is not None

    def require_bot(self) -> MyloConfig:
        """Assert the settings the gateway bot needs, or raise :class:`ConfigError`."""
        if not self.token:
            raise ConfigError(
                "DISCORD_API_KEY is not set in .env-mylo. Add the bot token from "
                "the Discord Developer Portal (Bot -> Reset Token)."
            )
        if self.error_channel_id is None:
            raise ConfigError(
                "ERROR_CHANNEL is not set in .env-mylo. Add the numeric id of the "
                "channel Mylo should post to."
            )
        return self


def _as_bool(value: str | None) -> bool:
    """Parse an optional on/off setting. Anything unrecognised reads as off.

    Deliberately not strict: a malformed value for a switch that decides
    whether Mylo reads a server's conversation should fail closed, not raise
    and leave the operator guessing which half of their config broke.
    """
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, name: str) -> int | None:
    """Parse an optional snowflake/channel id, raising a clear error on garbage."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a numeric id, got {value!r}") from exc


def load_config(overrides: dict[str, str] | None = None) -> MyloConfig:
    """Load Mylo config from ``.env-mylo``.

    Precedence (highest first): explicit ``overrides`` (tests), the process
    environment, then the ``.env-mylo`` file. ``overrides`` lets tests supply a
    full config without touching disk or the ambient environment.
    """
    file_values = _load_env_file(ENV_FILE)

    def get(key: str) -> str:
        if overrides is not None and key in overrides:
            return overrides[key]
        return os.environ.get(key) or file_values.get(key, "")

    raw_owners = get("DISCORD_OWNER_IDS").strip()
    try:
        owner_ids = frozenset(
            int(part) for part in raw_owners.split(",") if part.strip()
        )
    except ValueError as exc:
        raise ConfigError(
            f"DISCORD_OWNER_IDS must be comma-separated ids, got {raw_owners!r}"
        ) from exc

    return MyloConfig(
        token=get("DISCORD_API_KEY").strip(),
        error_channel_id=_as_int(get("ERROR_CHANNEL").strip() or None, "ERROR_CHANNEL"),
        summary_channel_id=_as_int(
            get("SUMMARY_CHANNEL").strip() or None, "SUMMARY_CHANNEL"
        ),
        dev_guild_id=_as_int(
            get("DISCORD_DEV_GUILD_ID").strip() or None, "DISCORD_DEV_GUILD_ID"
        ),
        owner_ids=owner_ids,
        listen_enabled=_as_bool(get("MYLO_LISTEN_ENABLED")),
    )
