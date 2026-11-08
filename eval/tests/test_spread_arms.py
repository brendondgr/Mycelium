"""The theme-spread arms' plumbing contract (`EXP-2026-08-005`).

Same discipline as `test_profile_arms.py`, and for the same reason: thirteen arms
that differ from the `clustered_profile` baseline by exactly one production
argument each. If that argument silently failed to arrive, every one of them
would compare the baseline against itself and report a null that looks
indistinguishable from a real negative result.

What these check:

1. Every named policy reaches `fuse_clusters_pool` as `spread=`, and nothing else
   about the call changes.
2. `spread_identity` — the null policy — produces the same *ordering* as the
   untouched `clustered_profile` arm, so the position-scored run-file conversion
   introduces nothing on its own.
3. The slate is never on under a spread policy, since the policy is itself the
   theme protection and having both would confound the measurement.

`apps.content` is stubbed, so this runs offline and fast. The stubbed
`SpreadPolicy` mirrors the real dataclass field-for-field; the real one is pinned
by `apps/content/tests/test_fusion_spread.py`, which runs against Django.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import arms  # noqa: E402


@dataclass
class _Item:
    id: str


@dataclass
class _Profile:
    id: str = "p0"
    _interests: list = field(default_factory=lambda: ["i0", "i1"])
    _clusters: list = field(default_factory=lambda: ["c0", "c1"])

    def interests(self):
        return self._interests

    def clusters(self):
        return self._clusters


@dataclass(frozen=True)
class _SpreadPolicy:
    """Field-for-field stand-in for `tools.recommendation.fusion.SpreadPolicy`."""

    merge: str = "max"
    select: str | None = None
    alpha: float = 0.5
    lam: float = 0.5
    admit: str = "global"
    admit_frac: float = 0.5
    rrf_k: int = 60


@pytest.fixture
def pipeline_spy(monkeypatch):
    """Stub `apps.content.{pipeline,fusion}`, recording every call the arms make."""
    calls: list[dict] = []

    def fuse_clusters_pool(interests, clusters, **kwargs):
        calls.append(
            {"fn": "clustered", "interests": interests, "clusters": clusters, **kwargs}
        )
        # Returned in surfaced order, best first — what production guarantees.
        rows = [
            (_Item("a"), 0.9, {"per_cluster": {"c0": 0.9, "c1": 0.2}}),
            (_Item("b"), 0.4, {"per_cluster": {"c1": 0.4}}),
        ]
        return [(item, score) for item, score, _ in rows], rows, 123, []

    pipeline = types.ModuleType("tools.recommendation.pipeline")
    pipeline.fuse_clusters_pool = fuse_clusters_pool
    fusion = types.ModuleType("tools.recommendation.fusion")
    fusion.SpreadPolicy = _SpreadPolicy

    for name in ("apps", "apps.content"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "tools.recommendation.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "tools.recommendation.fusion", fusion)
    return calls


_INDEX = object()


def _run(arm: str, **kwargs):
    return arms.PROFILE_ARMS[arm](
        [_Profile()], [], index=_INDEX, log=lambda _m: None, **kwargs
    )


def test_every_declared_spread_arm_is_registered() -> None:
    for name in arms.SPREAD_ARM_NAMES:
        assert name in arms.PROFILE_ARMS


def test_the_query_arms_never_pick_up_a_profile_arm() -> None:
    """`--all` sweeps `ARMS`; a profile arm there would run against bare queries."""
    assert not set(arms.ARMS) & set(arms.PROFILE_ARMS)


@pytest.mark.parametrize("name", arms.SPREAD_ARM_NAMES)
def test_each_arm_forwards_its_policy_to_production(name, pipeline_spy) -> None:
    _run(name)
    assert pipeline_spy[0]["fn"] == "clustered"
    assert pipeline_spy[0]["spread"] is not None


@pytest.mark.parametrize("name", arms.SPREAD_ARM_NAMES)
def test_no_spread_arm_also_turns_the_slate_on(name, pipeline_spy) -> None:
    """Both mechanisms at once would confound what the spread policy is doing."""
    _run(name, cluster_top_n=arms.PROFILE_CLUSTER_TOP_N)
    assert pipeline_spy[0].get("cluster_top_n", 0) == 0


@pytest.mark.parametrize("name", arms.SPREAD_ARM_NAMES)
def test_a_spread_arm_differs_from_the_baseline_only_in_spread(
    name, pipeline_spy
) -> None:
    _run("clustered_profile", beta=0.3, surface_limit=30, match_threshold=0.5)
    _run(name, beta=0.3, surface_limit=30, match_threshold=0.5)
    baseline, spread = pipeline_spy
    differing = {
        key
        for key in set(baseline) | set(spread)
        # `emit` is a fresh closure per call by construction, not a behaviour
        # difference — both arms pass the same no-op sink.
        if key != "emit" and baseline.get(key) != spread.get(key)
    }
    assert differing == {"spread"}


def test_the_policies_are_all_distinct(pipeline_spy) -> None:
    """A copy-paste slip between two policies would silently duplicate an arm."""
    _run("spread_identity")  # force the lazy import through the stub
    seen = {}
    for name in arms.SPREAD_ARM_NAMES:
        pipeline_spy.clear()
        _run(name)
        policy = pipeline_spy[0]["spread"]
        assert policy not in seen, f"{name} duplicates {seen.get(policy)}"
        seen[policy] = name


def test_the_identity_policy_really_is_the_default(pipeline_spy) -> None:
    _run("spread_identity")
    assert pipeline_spy[0]["spread"] == _SpreadPolicy()


def test_identity_reproduces_the_baseline_ordering(pipeline_spy) -> None:
    """Falsifier 4: the spread path must add nothing when the policy is null.

    The run-file *scores* differ by construction — a spread arm scores by position
    (`_positional_hits`) because its order, not its score, is the result. Only the
    ordering is compared, which is all any ranking metric reads.
    """
    baseline = _run("clustered_profile")
    identity = _run("spread_identity")
    assert [doc for doc, _ in identity.ranking["p0"]] == [
        doc for doc, _ in baseline.ranking["p0"]
    ]


def test_positional_scores_are_strictly_decreasing(pipeline_spy) -> None:
    """The property that stops a downstream sort from undoing the policy."""
    result = _run("spread_interleave")
    scores = [score for _doc, score in result.ranking["p0"]]
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)


def test_spread_arms_still_report_what_they_surfaced(pipeline_spy) -> None:
    """Falsifier 2 needs this: a gain bought with extra slots is not a gain."""
    result = _run("spread_interleave")
    assert result.diagnostics["surfacing"]["mean_surfaced"] == 2.0
    assert result.diagnostics["surfacing"]["mean_pool"] == 123.0
