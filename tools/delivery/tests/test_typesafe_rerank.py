"""The RERANK_METHOD switch: what moves, what never does, and what is reused.

Offline. A fake client answers with fixed probabilities; no network, no SDK.
Each test names the failure it exists to catch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from tools.recommendation import typesafe_rerank as ts
from tools.recommendation.clustering import Cluster


@dataclass
class _Item:
    id: str
    metadata: dict = field(default_factory=dict)


class _Client:
    """Answers ``worth`` per item title; raises for titles in ``broken``."""

    def __init__(self, worth: dict[str, float], broken: set[str] = frozenset()):
        self.worth = worth
        self.broken = broken
        self.calls: list[dict] = []

    def ask(self, state, questions, *, model=None):
        title = state["opportunity"]["title"]
        self.calls.append({"title": title, "strand": state["strand"]["label"]})
        if title in self.broken:
            raise RuntimeError("boom")
        w = self.worth[title]
        return SimpleNamespace(
            model="jev-1.13.0",
            answers_as_dicts=lambda: {
                "worth": {"noul": w},
                "fit": {
                    "score": 3 * w,
                    "confidence": 0.5,
                    "probabilities": {"0": 1 - w, "1": 0.0, "2": 0.0, "3": w},
                },
            },
        )


CLUSTERS = [
    Cluster(id="c1", label="Theme One", areas=["graphs"]),
    Cluster(id="c2", label="Theme Two", areas=["edge llms"]),
]


def _items(n: int) -> dict[str, _Item]:
    return {
        f"d{i}": _Item(f"d{i}", {"title": f"d{i}", "abstract": "x"}) for i in range(n)
    }


@pytest.fixture(autouse=True)
def _typesafe_on(settings):
    settings.RERANK_METHOD = "typesafe"
    settings.TYPESAFE_API_KEY = "k"
    settings.TYPESAFE_MODEL = "jev-1.13.0"
    settings.TYPESAFE_RERANK_WINDOW = 3
    settings.TYPESAFE_RERANK_CONTENT_TYPES = [
        "paper",
        "grant",
        "conference",
        "fellowship",
    ]


def _run(groups, client, items=None, prior=None):
    return ts.reorder_id_groups(
        groups,
        items_by_id=items or _items(6),
        interests={"statement": "s", "areas": ["graphs", "edge llms"]},
        profile_meta={},
        clusters=CLUSTERS,
        content_type="paper",
        prior=prior,
        emit=lambda m: None,
        client=client,
    )


def test_head_sorted_by_worth_ties_by_fused_order_tail_untouched():
    client = _Client({"d0": 0.2, "d1": 0.9, "d2": 0.9, "d3": 0.1, "d4": 0.5})
    groups, judgements = _run({"c1": ["d0", "d1", "d2", "d3", "d4"]}, client)
    # window 3: d1 and d2 tie -> fused order; d0 last of the head; d3, d4 untouched
    assert groups["c1"] == ["d1", "d2", "d0", "d3", "d4"]
    assert len(client.calls) == 3
    assert judgements["d1"]["c1"]["worth"] == 0.9
    assert judgements["d1"]["c1"]["verdict"] == "read"
    assert judgements["d0"]["c1"]["verdict"] == "skip"
    assert judgements["d1"]["c1"]["reused"] is False


def test_a_failed_call_leaves_that_theme_in_fused_order_but_not_the_others():
    client = _Client(
        {"d0": 0.1, "d1": 0.9, "d2": 0.5, "d3": 0.3, "d4": 0.8}, broken={"d1"}
    )
    groups, _ = _run({"c1": ["d0", "d1", "d2"], "c2": ["d3", "d4"]}, client)
    assert groups["c1"] == ["d0", "d1", "d2"]  # untouched: one head item unjudged
    assert groups["c2"] == ["d4", "d3"]


def test_a_matching_fingerprint_is_reused_without_a_call():
    client = _Client({"d0": 0.1, "d1": 0.9})
    _, first = _run({"c1": ["d0", "d1"]}, client)
    calls_after_first = len(client.calls)
    client2 = _Client({"d0": 0.1, "d1": 0.9})
    groups, second = _run({"c1": ["d0", "d1"]}, client2, prior=first)
    assert client2.calls == []
    assert calls_after_first == 2
    assert groups["c1"] == ["d1", "d0"]
    assert all(j["reused"] for per in second.values() for j in per.values())


def test_a_changed_profile_invalidates_the_stored_judgement():
    client = _Client({"d0": 0.1, "d1": 0.9})
    _, first = _run({"c1": ["d0", "d1"]}, client)
    client2 = _Client({"d0": 0.1, "d1": 0.9})
    ts.reorder_id_groups(
        {"c1": ["d0", "d1"]},
        items_by_id=_items(2),
        interests={"statement": "a different reader", "areas": ["graphs"]},
        profile_meta={},
        clusters=CLUSTERS,
        content_type="paper",
        prior=first,
        emit=lambda m: None,
        client=client2,
    )
    assert len(client2.calls) == 2


def test_each_theme_asks_about_its_own_strand():
    client = _Client({"d0": 0.5, "d1": 0.5})
    _run({"c1": ["d0"], "c2": ["d1"]}, client)
    assert {c["strand"] for c in client.calls} == {"Theme One", "Theme Two"}


def test_slate_groups_wrapper_keeps_hits_and_scores():
    client = _Client({"d0": 0.1, "d1": 0.9})
    items = _items(2)
    hits = {"c1": [(items["d0"], 0.7), (items["d1"], 0.6)]}
    groups, judgements = ts.reorder_slate_groups(
        hits,
        interests={"areas": ["graphs"]},
        profile_meta={},
        clusters=CLUSTERS,
        content_type="paper",
        prior=None,
        emit=lambda m: None,
        client=client,
    )
    assert [(h[0].id, h[1]) for h in groups["c1"]] == [("d1", 0.6), ("d0", 0.7)]
    rows = [(items["d0"], 0.7, {}), (items["d1"], 0.6, {})]
    ts.attach(rows, judgements)
    assert rows[1][2]["typesafe"]["c1"]["worth"] == 0.9


def test_switch_off_key_missing_or_type_unlisted_disables(settings):
    assert ts.enabled_for("paper") is True
    settings.RERANK_METHOD = "local"
    assert ts.enabled_for("paper") is False
    settings.RERANK_METHOD = "typesafe"
    settings.TYPESAFE_API_KEY = ""
    assert ts.enabled_for("paper") is False
    settings.TYPESAFE_API_KEY = "k"
    settings.TYPESAFE_RERANK_CONTENT_TYPES = ["grant"]
    assert ts.enabled_for("paper") is False
    assert ts.enabled_for("grant") is True


def test_unknown_method_is_local():
    from django.test import override_settings

    with override_settings(RERANK_METHOD="banana"):
        assert ts.method() == "local"


def test_head_ids_accepts_hits_or_ids():
    items = _items(3)
    assert ts.head_ids({"c1": [(items["d0"], 1.0), (items["d1"], 0.5)]}, size=1) == [
        "d0"
    ]
    assert ts.head_ids({"c1": ["d0", "d1", "d2"]}, size=2) == ["d0", "d1"]


@pytest.mark.django_db
def test_free_tier_is_not_entitled_when_enforcing(settings):
    from apps.billing import entitlements
    from django.contrib.auth.models import User

    user = User.objects.create(username="free-reader")
    settings.BILLING_ENFORCE_ENTITLEMENTS = True
    if not entitlements.enforcing():
        pytest.skip("enforcement flag is not read from settings at call time")
    assert ts.enabled_for("paper", {"target_user": user}) is False
    assert ts.enabled_for("paper") is True
