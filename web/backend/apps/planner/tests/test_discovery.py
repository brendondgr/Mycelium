"""Tests for discovery/liveness: content probe, timeout guard, re-probe cache."""

import threading

from apps.planner.discovery import (
    FixedClock,
    GraphSnapshot,
    LiveSourceView,
    ProbeResult,
    ProbeUnreachable,
    SourceProber,
    StaticInspector,
)
from apps.planner.fixtures import default_registry


def _healthy_snapshots():
    """A snapshot for each built-in card that satisfies its content probe."""

    registry = default_registry()
    snapshots = {}
    for card in registry:
        snapshots[card.name] = GraphSnapshot(
            present_labels=card.node_labels,
            node_count=card.probe.min_node_count + 5,
        )
    return registry, snapshots


def test_all_sources_live_when_content_probe_passes():
    registry, snapshots = _healthy_snapshots()
    prober = SourceProber(registry, StaticInspector(snapshots), timeout=1.0)

    view = prober.live_view()

    assert view.live_names() == {"lab_graph", "evidence_graph", "opportunity_graph"}
    assert view.is_live("lab_graph")
    assert "evidence_graph" in view


def test_down_source_is_excluded_not_fatal():
    registry, snapshots = _healthy_snapshots()
    snapshots["opportunity_graph"] = ProbeUnreachable("connection refused")
    prober = SourceProber(registry, StaticInspector(snapshots), timeout=1.0)

    view = prober.live_view()

    assert view.live_names() == {"lab_graph", "evidence_graph"}
    assert not view.is_live("opportunity_graph")
    assert "unreachable" in view.result("opportunity_graph").reason


def test_up_but_empty_graph_is_not_live_by_node_count():
    registry, snapshots = _healthy_snapshots()
    card = registry.require("evidence_graph")
    # Transport answers, expected labels exist, but the graph is nearly empty.
    snapshots["evidence_graph"] = GraphSnapshot(
        present_labels=card.node_labels,
        node_count=card.probe.min_node_count - 1,
    )
    prober = SourceProber(registry, StaticInspector(snapshots), timeout=1.0)

    view = prober.live_view()

    assert not view.is_live("evidence_graph")
    assert "node count" in view.result("evidence_graph").reason


def test_up_but_missing_expected_labels_is_not_live():
    registry, snapshots = _healthy_snapshots()
    # Plenty of nodes, but the expected labels are absent (wrong graph loaded).
    snapshots["lab_graph"] = GraphSnapshot(
        present_labels=frozenset({"Something", "Else"}),
        node_count=10_000,
    )
    prober = SourceProber(registry, StaticInspector(snapshots), timeout=1.0)

    view = prober.live_view()

    assert not view.is_live("lab_graph")
    assert "missing expected labels" in view.result("lab_graph").reason


def test_hanging_probe_times_out_and_is_treated_as_down():
    registry, snapshots = _healthy_snapshots()
    started = threading.Event()

    def hang(card, timeout):
        started.set()
        # Block well past the probe timeout; bounded so the daemon thread exits.
        threading.Event().wait(1.0)
        return GraphSnapshot(present_labels=card.node_labels, node_count=100)

    snapshots["lab_graph"] = hang
    prober = SourceProber(registry, StaticInspector(snapshots), timeout=0.05)

    view = prober.live_view()

    assert started.is_set()
    assert not view.is_live("lab_graph")
    assert "exceeded" in view.result("lab_graph").reason
    # The other sources still planned around fine.
    assert view.is_live("evidence_graph")


def test_live_view_is_cached_then_reprobed_after_ttl():
    registry, snapshots = _healthy_snapshots()
    inspector = StaticInspector(snapshots)
    clock = FixedClock()
    prober = SourceProber(
        registry, inspector, timeout=1.0, cache_ttl=3.0, clock=clock
    )

    prober.live_view()
    assert inspector.calls["lab_graph"] == 1

    # Within the TTL: served from cache, no new probing.
    clock.advance(1.0)
    prober.live_view()
    assert inspector.calls["lab_graph"] == 1

    # Past the TTL: re-probed (briefing 2.4).
    clock.advance(3.0)
    prober.live_view()
    assert inspector.calls["lab_graph"] == 2

    # force bypasses the cache.
    prober.live_view(force=True)
    assert inspector.calls["lab_graph"] == 3


def test_live_source_view_unknown_source_is_not_live():
    view = LiveSourceView([ProbeResult("a", live=True, reason="ok")])

    assert view.is_live("a")
    assert not view.is_live("ghost")
    assert "ghost" not in view
