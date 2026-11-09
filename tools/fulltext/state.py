"""The engine's :class:`~tools.fulltext.engine.state.State`, shared by every worker.

* Switch-offs, strike counts and per-source throttles live in Redis, so a
  Wiley quota stop seen by one Celery worker stops all of them, and two
  workers never ask arXiv inside the same 3-second window. The connection is
  this tool's own (a database number of the instance's Redis), not a platform
  cache alias, so the tool needs nothing outside its folder.
* Remembered definitive answers live in the database
  (:class:`~tools.fulltext.models.SourceVerdict`): they are permanent facts
  ("Unpaywall knows no open copy of this DOI"), not ephemeral state.

If Redis cannot be reached the switch-offs and throttles fall back to this
process's memory, with a warning: requests still work, they just stop being
coordinated across workers until Redis is back.
"""

from __future__ import annotations

import logging
import re
import time

from django.conf import settings
from django.db import IntegrityError

from .engine.state import MemoryState
from .models import SourceVerdict

log = logging.getLogger(__name__)

PREFIX = "mycelium:fulltext"
STRIKE_TTL = 24 * 3600  # a strike streak older than a day is forgotten
STATE_REDIS_DB = 7


def redis_url() -> str:
    """This tool's Redis: the configured URL, else the broker's host on db 7."""
    explicit = getattr(settings, "FULLTEXT_REDIS_URL", "")
    if explicit:
        return explicit
    broker = getattr(settings, "CELERY_BROKER_URL", "") or "redis://localhost:6379/0"
    if re.search(r"/\d+$", broker):
        return re.sub(r"/\d+$", f"/{STATE_REDIS_DB}", broker)
    return broker.rstrip("/") + f"/{STATE_REDIS_DB}"


class SharedState:
    """Redis for switch-offs/strikes/throttles, the database for verdicts."""

    def __init__(self, client) -> None:
        self.r = client

    # -- switch-offs ------------------------------------------------------- #
    def switched_off(self) -> dict[str, str]:
        out = {}
        for key in self.r.scan_iter(match=f"{PREFIX}:off:*"):
            key = key.decode() if isinstance(key, bytes) else key
            reason = self.r.get(key)
            if reason is not None:
                source = key.rsplit(":", 1)[-1]
                out[source] = reason.decode() if isinstance(reason, bytes) else reason
        return out

    def switch_off(self, source: str, reason: str, ttl: float) -> bool:
        return bool(
            self.r.set(
                f"{PREFIX}:off:{source}", reason, nx=True, px=max(1, int(ttl * 1000))
            )
        )

    def switch_on(self, source: str) -> None:
        self.r.delete(f"{PREFIX}:off:{source}", f"{PREFIX}:strike:{source}")

    def strike(self, source: str) -> int:
        key = f"{PREFIX}:strike:{source}"
        n = int(self.r.incr(key))
        self.r.expire(key, STRIKE_TTL)
        return n

    def clear_strikes(self, source: str) -> None:
        self.r.delete(f"{PREFIX}:strike:{source}")

    # -- throttle ---------------------------------------------------------- #
    def wait_turn(self, source: str, interval: float) -> None:
        """Claim the next slot for ``source``: a key that lives ``interval``
        seconds. Whoever sets it may go; everyone else waits for it to expire."""
        if interval <= 0:
            return
        key = f"{PREFIX}:slot:{source}"
        ms = max(1, int(interval * 1000))
        while not self.r.set(key, 1, nx=True, px=ms):
            remaining = self.r.pttl(key)
            time.sleep(
                max(remaining, 5) / 1000 if remaining and remaining > 0 else 0.01
            )

    # -- remembered answers ------------------------------------------------ #
    def remembered(self, key: str, source: str) -> str | None:
        row = SourceVerdict.objects.filter(key=key[:300], source=source).first()
        return row.outcome if row else None

    def remember(self, key: str, source: str, outcome: str) -> None:
        try:
            SourceVerdict.objects.update_or_create(
                key=key[:300], source=source, defaults={"outcome": outcome[:300]}
            )
        except IntegrityError:  # another worker recorded it first: same fact
            pass


class LocalState(MemoryState):
    """Redis unavailable: this process's memory, but verdicts still in the DB."""

    remembered = SharedState.remembered
    remember = SharedState.remember


def shared_state():
    """The state every request in this process should use."""
    try:
        import redis

        client = redis.Redis.from_url(
            redis_url(), socket_connect_timeout=2, socket_timeout=5
        )
        client.ping()
        return SharedState(client)
    except Exception as exc:  # any Redis failure: degrade, never stop requests
        log.warning(
            "full text: Redis at %s unavailable (%s); switch-offs and throttles "
            "are per-process until it is back",
            redis_url(),
            type(exc).__name__,
        )
        return LocalState()
