"""The profile arms' plumbing contract. No collection, no Django, no model.

These do not check ranking quality — that is what the experiments are for. They
check the two things a wrong number would come from:

1. Each arm forwards the parameters it claims to forward. `slate_profile` differs
   from `clustered_profile` by exactly one production argument
   (`cluster_top_n`), and if that argument silently failed to arrive, the slate
   experiment would compare an arm against itself and report a null.
2. No arm contains ranking logic of its own — every one is a call into
   `apps.content.pipeline`.

`apps.content` is stubbed, so this runs offline and fast. The stub records the
kwargs it was handed; that is the whole point.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


@pytest.fixture
def pipeline_spy(monkeypatch):
    """Stub `apps.content.pipeline`, recording every call the arms make."""
    calls: list[dict] = []

    def fuse_interests_pool(interests, **kwargs):
        calls.append({"fn": "flat", "interests": interests, **kwargs})
        rows = [
            (_Item("a"), 0.9, {"n_matched": 2}),
            (_Item("b"), 0.4, {"n_matched": 1}),
        ]
        return [(item, score) for item, score, _ in rows], rows, 123

    def fuse_clusters_pool(interests, clusters, **kwargs):
        calls.append(
            {"fn": "clustered", "interests": interests, "clusters": clusters, **kwargs}
        )
        rows = [
            (_Item("a"), 0.9, {"per_cluster": {"c0": 0.9, "c1": 0.2}}),
            (_Item("b"), 0.4, {"per_cluster": {"c1": 0.4}}),
        ]
        return [(item, score) for item, score, _ in rows], rows, 123, []

    module = types.ModuleType("apps.content.pipeline")
    module.fuse_interests_pool = fuse_interests_pool
    module.fuse_clusters_pool = fuse_clusters_pool
    for name in ("apps", "apps.content"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "apps.content.pipeline", module)
    return calls


#: One shared stand-in for the vector index, so two arms' recorded calls compare
#: equal on it rather than on object identity.
_INDEX = object()


def _run(arm: str, spy, **kwargs) -> Any:
    return arms.PROFILE_ARMS[arm](
        [_Profile()], [], index=_INDEX, log=lambda _m: None, **kwargs
    )


def test_flat_arm_calls_the_flat_production_function(pipeline_spy) -> None:
    _run("flat_profile", pipeline_spy)
    assert [call["fn"] for call in pipeline_spy] == ["flat"]


def test_clustered_arm_passes_the_profile_clusters(pipeline_spy) -> None:
    _run("clustered_profile", pipeline_spy)
    assert pipeline_spy[0]["fn"] == "clustered"
    assert pipeline_spy[0]["clusters"] == ["c0", "c1"]


def test_clustered_arm_defaults_to_no_slate(pipeline_spy) -> None:
    """The global-ranking path — an individual's feed, and EXP-2026-08-003's arm."""
    _run("clustered_profile", pipeline_spy)
    assert pipeline_spy[0]["cluster_top_n"] == 0


def test_slate_arm_turns_the_slate_on(pipeline_spy) -> None:
    """The one argument that separates the lab path from the individual path.

    If this regressed to 0, the slate experiment would compare `clustered_profile`
    against itself and report a null — a false negative that would look exactly
    like a real finding.
    """
    _run("slate_profile", pipeline_spy)
    assert pipeline_spy[0]["cluster_top_n"] == arms.PROFILE_CLUSTER_TOP_N
    assert pipeline_spy[0]["cluster_top_n"] > 0


def test_slate_arm_is_otherwise_identical_to_the_clustered_arm(pipeline_spy) -> None:
    _run("clustered_profile", pipeline_spy, beta=0.3, surface_limit=30)
    _run("slate_profile", pipeline_spy, beta=0.3, surface_limit=30)
    clustered, slate = pipeline_spy
    differing = {
        key
        for key in set(clustered) | set(slate)
        # `emit` is a fresh closure per call by construction, never a difference
        # in behaviour — both arms pass the same no-op sink.
        if key != "emit" and clustered.get(key) != slate.get(key)
    }
    assert differing == {"cluster_top_n"}


@pytest.mark.parametrize("arm", ["flat_profile", "clustered_profile", "slate_profile"])
def test_surfacing_parameters_reach_production(arm, pipeline_spy) -> None:
    _run(arm, pipeline_spy, surface_limit=30, match_threshold=0.5, beta=0.25)
    call = pipeline_spy[0]
    assert call["surface_limit"] == 30
    assert call["match_threshold"] == 0.5
    assert call["beta"] == 0.25


@pytest.mark.parametrize("arm", ["flat_profile", "clustered_profile", "slate_profile"])
def test_every_arm_reports_what_it_surfaced(arm, pipeline_spy) -> None:
    """A slate buys coverage by surfacing more, so the size must always be visible."""
    result = _run(arm, pipeline_spy)
    assert result.diagnostics["surfacing"]["mean_surfaced"] == 2.0
    assert result.diagnostics["surfacing"]["mean_pool"] == 123.0


@pytest.mark.parametrize("arm", ["flat_profile", "clustered_profile", "slate_profile"])
def test_ranking_is_best_first_and_deterministic(arm, pipeline_spy) -> None:
    result = _run(arm, pipeline_spy)
    assert result.ranking["p0"] == [("a", 0.9), ("b", 0.4)]
