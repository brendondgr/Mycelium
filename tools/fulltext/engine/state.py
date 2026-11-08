"""State the fetcher shares across threads, and across processes when asked to.

PubMedExtraction kept three things on its one long-lived ``Fetcher``: which
sources were switched off at runtime (a quota stop, 25 refusals in a row), the
per-source request throttle, and the remembered definitive "no" answers
(``attempts.json``). Mycelium runs several Celery workers, so a Wiley quota
stop seen by one worker must stop all of them, and no two workers may race on
one JSON file. The fetcher therefore talks to a :class:`State`.

:class:`MemoryState` is the in-process implementation used by the engine's
tests and by one-off command-line runs. The Django side of the tool provides a
shared one (Redis for switch-offs and throttles, the database for remembered
answers) behind the same methods.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol


class State(Protocol):
    def switched_off(self) -> dict[str, str]:
        """{source: reason} for every source switched off and not yet expired."""

    def switch_off(self, source: str, reason: str, ttl: float) -> bool:
        """Switch ``source`` off for ``ttl`` seconds. True if it was on."""

    def switch_on(self, source: str) -> None:
        """Clear a switch-off (and the strike count) for ``source``."""

    def strike(self, source: str) -> int:
        """Record one entitlement refusal; return the consecutive count."""

    def clear_strikes(self, source: str) -> None:
        """A success resets the consecutive-refusal count."""

    def wait_turn(self, source: str, interval: float) -> None:
        """Block until ``source`` may be asked again, then claim the slot."""

    def remembered(self, key: str, source: str) -> str | None:
        """A definitive earlier answer for (article key, source), if any."""

    def remember(self, key: str, source: str, outcome: str) -> None:
        """Record a definitive answer so it is never asked again."""


class MemoryState:
    """Thread-safe, single-process :class:`State`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._off: dict[str, tuple[str, float]] = {}  # source -> (reason, until)
        self._strikes: dict[str, int] = {}
        self._last: dict[str, float] = {}
        self._source_locks: dict[str, threading.Lock] = {}
        self._answers: dict[tuple[str, str], str] = {}

    def switched_off(self) -> dict[str, str]:
        now = time.time()
        with self._lock:
            for source in [s for s, (_, until) in self._off.items() if until <= now]:
                del self._off[source]
                self._strikes.pop(source, None)
            return {s: reason for s, (reason, _) in self._off.items()}

    def switch_off(self, source: str, reason: str, ttl: float) -> bool:
        self.switched_off()  # expire first, so an old stop does not mask a new one
        with self._lock:
            if source in self._off:
                return False
            self._off[source] = (reason, time.time() + ttl)
            return True

    def switch_on(self, source: str) -> None:
        with self._lock:
            self._off.pop(source, None)
            self._strikes.pop(source, None)

    def strike(self, source: str) -> int:
        with self._lock:
            self._strikes[source] = self._strikes.get(source, 0) + 1
            return self._strikes[source]

    def clear_strikes(self, source: str) -> None:
        with self._lock:
            self._strikes.pop(source, None)

    def wait_turn(self, source: str, interval: float) -> None:
        with self._lock:
            lock = self._source_locks.setdefault(source, threading.Lock())
        with lock:
            wait = interval - (time.time() - self._last.get(source, 0.0))
            if wait > 0:
                time.sleep(wait)
            self._last[source] = time.time()

    def remembered(self, key: str, source: str) -> str | None:
        with self._lock:
            return self._answers.get((key, source))

    def remember(self, key: str, source: str, outcome: str) -> None:
        with self._lock:
            self._answers[(key, source)] = outcome
