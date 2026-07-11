"""Configuration: fail fast, never hardcode a secret.

Reference for the `discord-bot` skill. discord.py 2.7.1.

The token is a full credential for the bot account. It belongs in the
environment and nowhere else -- not in code, not in a commit, not in a log line.
If one leaks, reset it in the Developer Portal immediately.

    # .env  (gitignored)
    DISCORD_BOT_TOKEN=...        # Developer Portal -> Bot -> Reset Token
    DISCORD_DEV_GUILD_ID=...     # optional: a test server for instant syncing
    DISCORD_OWNER_IDS=1,2        # optional: who may run owner-only commands
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    dev_guild_id: int | None = None
    owner_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def is_dev(self) -> bool:
        """Dev mode = a test guild is configured, so we sync there instead of globally."""
        return self.dev_guild_id is not None


def load_settings() -> Settings:
    """Read and validate configuration. Raises before the bot ever connects."""
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "DISCORD_BOT_TOKEN is not set. Get it from the Discord Developer "
            "Portal -> your application -> Bot -> Reset Token, and put it in .env."
        )

    raw_guild = os.environ.get("DISCORD_DEV_GUILD_ID", "").strip()
    dev_guild_id: int | None = None
    if raw_guild:
        try:
            dev_guild_id = int(raw_guild)
        except ValueError as exc:
            raise ConfigError(f"DISCORD_DEV_GUILD_ID must be a snowflake id, got {raw_guild!r}") from exc

    raw_owners = os.environ.get("DISCORD_OWNER_IDS", "").strip()
    try:
        owner_ids = frozenset(int(part) for part in raw_owners.split(",") if part.strip())
    except ValueError as exc:
        raise ConfigError(f"DISCORD_OWNER_IDS must be comma-separated ids, got {raw_owners!r}") from exc

    return Settings(token=token, dev_guild_id=dev_guild_id, owner_ids=owner_ids)


# Never do this:
#     TOKEN = "MTIzNDU2Nzg5.GaBcDe.f0oB4rB4z"   # <-- instant compromise
#
# Never log this:
#     log.info("starting with token %s", settings.token)
#
# If you print the token to debug, treat it as leaked and reset it.
