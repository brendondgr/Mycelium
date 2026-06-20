"""Discovery / liveness: which graphs are actually running right now.

The planner must reflect reality at planning time, not registry intent
(briefing 2). Three things make a source "live":

* it answers at all (briefing 2.1 — a down source is excluded, not fatal),
* it answers fast enough (briefing 2.3 — each probe has its own short timeout,
  enforced here with a thread guard so a hung backend cannot stall planning),
* and it actually holds the expected data (briefing 2.2 — a *content* probe
  confirms expected labels exist and node count is non-trivial, not a bare
  socket open).

The live-source view is re-probed per request and cached for only a few
seconds (briefing 2.4), so it tracks current state instead of startup state.
The Neo4j transport lives behind the :class:`GraphInspector` seam; the planner
logic depends only on that protocol, so it is fully testable offline.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .cards import CardRegistry, SourceCard


class ProbeUnreachable(Exception):
    """The backend could not be reached (down, refused, auth failure)."""


class ProbeTimeout(Exception):
    """The backend did not answer within the probe's own short timeout."""


@dataclass(frozen=True)
class GraphSnapshot:
    """What an inspector observed about a source's content."""

    present_labels: frozenset[str]
    node_count: int


class GraphInspector(Protocol):
    """Transport seam: ask a graph what labels and how many nodes it holds.

    Implementations must honor ``timeout`` and raise :class:`ProbeUnreachable`
    or :class:`ProbeTimeout` rather than block indefinitely. The probe also
    guards the call with its own timeout, so a misbehaving inspector still
    cannot stall planning.
    """

    def inspect(self, card: SourceCard, *, timeout: float) -> GraphSnapshot: ...


@dataclass(frozen=True)
class ProbeResult:
    """The outcome of probing one source for one live-source view."""

    source: str
    live: bool
    reason: str
    observed_labels: frozenset[str] = frozenset()
    observed_node_count: int = 0


class LiveSourceView:
    """The set of sources that are live right now, with per-source detail.

    Any source not proven live is treated as not live; the planner marks the
    parts that needed it unsupported (briefing 1.3, 2.1).
    """

    def __init__(self, results: Iterable[ProbeResult]):
        self._results: dict[str, ProbeResult] = {r.source: r for r in results}

    def __contains__(self, name: object) -> bool:
        return self.is_live(name)  # type: ignore[arg-type]

    def is_live(self, name: str) -> bool:
        result = self._results.get(name)
        return result is not None and result.live

    def live_names(self) -> frozenset[str]:
        return frozenset(
            name for name, result in self._results.items() if result.live
        )

    def result(self, name: str) -> ProbeResult | None:
        return self._results.get(name)

    def results(self) -> tuple[ProbeResult, ...]:
        return tuple(self._results.values())


def _inspect_with_timeout(
    inspector: GraphInspector, card: SourceCard, timeout: float
) -> GraphSnapshot:
    """Run an inspection bounded by ``timeout``, regardless of inspector behavior.

    The inspector is asked to honor the timeout, but we also run it on a daemon
    thread and stop waiting once the timeout elapses, so a hung backend is
    treated as down rather than waited on (briefing 2.3).
    """

    box: dict[str, object] = {}

    def run() -> None:
        try:
            box["snapshot"] = inspector.inspect(card, timeout=timeout)
        except Exception as exc:  # surfaced on the calling thread below
            box["error"] = exc

    worker = threading.Thread(target=run, name=f"probe-{card.name}", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise ProbeTimeout(f"probe for '{card.name}' exceeded {timeout:g}s")
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["snapshot"]  # type: ignore[return-value]


def probe_source(
    card: SourceCard, inspector: GraphInspector, *, timeout: float
) -> ProbeResult:
    """Content-probe a single source and decide whether it is live."""

    try:
        snapshot = _inspect_with_timeout(inspector, card, timeout)
    except ProbeTimeout as exc:
        return ProbeResult(card.name, live=False, reason=str(exc))
    except ProbeUnreachable as exc:
        return ProbeResult(card.name, live=False, reason=f"unreachable: {exc}")
    except Exception as exc:  # any inspector failure means "not proven live"
        return ProbeResult(card.name, live=False, reason=f"probe error: {exc}")

    missing = card.probe.expected_labels - snapshot.present_labels
    if missing:
        return ProbeResult(
            card.name,
            live=False,
            reason=f"missing expected labels: {sorted(missing)}",
            observed_labels=snapshot.present_labels,
            observed_node_count=snapshot.node_count,
        )
    if snapshot.node_count < card.probe.min_node_count:
        return ProbeResult(
            card.name,
            live=False,
            reason=(
                f"node count {snapshot.node_count} below minimum "
                f"{card.probe.min_node_count}"
            ),
            observed_labels=snapshot.present_labels,
            observed_node_count=snapshot.node_count,
        )
    return ProbeResult(
        card.name,
        live=True,
        reason="ok",
        observed_labels=snapshot.present_labels,
        observed_node_count=snapshot.node_count,
    )


@dataclass
class _CacheEntry:
    at: float
    view: LiveSourceView


class SourceProber:
    """Builds a live-source view by content-probing every registered card.

    Re-probes per request, but caches the result for ``cache_ttl`` seconds so a
    burst of requests does not hammer the backends (briefing 2.4). Each probe is
    bounded by ``timeout`` (briefing 2.3).
    """

    def __init__(
        self,
        registry: CardRegistry,
        inspector: GraphInspector,
        *,
        timeout: float = 2.0,
        cache_ttl: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if timeout <= 0:
            raise ValueError("probe timeout must be positive")
        if cache_ttl < 0:
            raise ValueError("cache_ttl must be non-negative")
        self._registry = registry
        self._inspector = inspector
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._clock = clock
        self._cache: _CacheEntry | None = None

    def live_view(self, *, force: bool = False) -> LiveSourceView:
        now = self._clock()
        cache = self._cache
        if (
            not force
            and cache is not None
            and now - cache.at < self._cache_ttl
        ):
            return cache.view

        results = [
            probe_source(card, self._inspector, timeout=self._timeout)
            for card in self._registry
        ]
        view = LiveSourceView(results)
        self._cache = _CacheEntry(at=now, view=view)
        return view


class StaticInspector:
    """In-memory inspector for tests and offline planning.

    Each source maps to a :class:`GraphSnapshot` (live), an exception instance
    (raised to simulate down/timeout backends), or a callable taking
    ``(card, timeout)`` (to simulate slow or hanging probes).
    """

    def __init__(
        self,
        snapshots: Mapping[
            str,
            GraphSnapshot
            | Exception
            | Callable[[SourceCard, float], GraphSnapshot],
        ],
    ):
        self._snapshots = dict(snapshots)
        self.calls: dict[str, int] = {}

    def inspect(self, card: SourceCard, *, timeout: float) -> GraphSnapshot:
        self.calls[card.name] = self.calls.get(card.name, 0) + 1
        entry = self._snapshots.get(card.name)
        if entry is None:
            raise ProbeUnreachable(f"no backend registered for '{card.name}'")
        if isinstance(entry, Exception):
            raise entry
        if callable(entry):
            return entry(card, timeout)
        return entry


class Neo4jInspector:
    """Production inspector that content-probes a Neo4j source.

    Integration seam only — it requires a live Neo4j and is exercised in
    production wiring, not unit tests. ``driver_for`` resolves a configured
    driver for a source name (sources may live on different backends).
    """

    def __init__(
        self,
        driver_for: Callable[[str], object],
        database: str | None = None,
    ):
        self._driver_for = driver_for
        self._database = database

    def inspect(self, card: SourceCard, *, timeout: float) -> GraphSnapshot:
        try:
            from neo4j.exceptions import Neo4jError, ServiceUnavailable
        except ImportError as exc:  # pragma: no cover - driver always present in prod
            raise ProbeUnreachable(f"neo4j driver unavailable: {exc}") from exc

        driver = self._driver_for(card.name)
        try:
            with driver.session(database=self._database) as session:  # type: ignore[attr-defined]
                present = frozenset(
                    session.run("CALL db.labels() YIELD label RETURN label").value()
                )
                count = session.run(
                    "MATCH (n) RETURN count(n) AS c", timeout=timeout
                ).single()["c"]
        except ServiceUnavailable as exc:
            raise ProbeUnreachable(str(exc)) from exc
        except Neo4jError as exc:  # pragma: no cover - backend-specific
            raise ProbeUnreachable(str(exc)) from exc
        return GraphSnapshot(present_labels=present, node_count=int(count))


@dataclass
class FixedClock:
    """A manually advanced monotonic clock for deterministic cache tests."""

    now: float = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
