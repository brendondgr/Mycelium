"""The TypeSafe arms' plumbing contract. No collection, no network, no SDK.

Checks the things a wrong number would come from: the window is sorted by the
model's value with the base rank breaking ties, a failed pair keeps its base
position at the bottom of the window, the tail beyond the window is untouched,
every answer is dumped, and an alias model is refused before any call.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "web" / "backend"))

from harness import typesafe_rerank as ts  # noqa: E402


@dataclass
class _Doc:
    id: str
    metadata: dict = field(default_factory=dict)


class _Client:
    """Answers a fixed value per doc id; raises for ids in `broken`."""

    def __init__(self, values: dict[str, float], broken: set[str] = frozenset()):
        self.values = values
        self.broken = broken
        self.calls: list[dict] = []

    def ask(self, state, questions, *, model=None):
        self.calls.append({"state": state, "model": model})
        doc_title = state["candidate"]["title"]
        if doc_title in self.broken:
            raise RuntimeError("boom")
        return SimpleNamespace(
            answers={"relevance": SimpleNamespace(noul=self.values[doc_title])},
            usage={"input_tokens": 100, "output_tokens": 5},
            answers_as_dicts=lambda: {"relevance": {"noul": self.values[doc_title]}},
        )


@pytest.fixture
def plumbing(monkeypatch, tmp_path):
    docs = [_Doc(f"d{i}", {"title": f"d{i}", "abstract": "x"}) for i in range(6)]
    base = {"q1": [(f"d{i}", 1.0 / (1 + i)) for i in range(6)]}
    monkeypatch.setattr(ts, "base_ranking", lambda *a, **k: base)
    monkeypatch.setattr(ts, "noul_question", lambda: "q")
    monkeypatch.setattr(ts, "DUMP_DIR", tmp_path)
    return docs


def test_window_sorted_by_value_ties_by_base_rank_tail_untouched(
    plumbing, monkeypatch
):
    client = _Client({"d0": 0.2, "d1": 0.9, "d2": 0.9, "d3": 0.1})
    monkeypatch.setattr(ts, "_client", lambda component: client)
    ranking = ts.typesafe_noul(
        [("q1", "query")], plumbing, index=None,
        params={"window": 4, "model": "jev-1.13.0"}, log=lambda m: None,
    )
    order = [doc_id for doc_id, _ in ranking["q1"]]
    # d1 and d2 tie at 0.9 -> base order (d1 first); d0 then d3; tail d4, d5 untouched.
    assert order == ["d1", "d2", "d0", "d3", "d4", "d5"]
    assert all(c["model"] == "jev-1.13.0" for c in client.calls)
    assert len(client.calls) == 4


def test_failed_pair_sinks_to_the_bottom_of_the_window_and_is_dumped(
    plumbing, monkeypatch, tmp_path
):
    client = _Client({"d0": 0.5, "d1": 0.7, "d2": 0.6}, broken={"d1"})
    monkeypatch.setattr(ts, "_client", lambda component: client)
    ranking = ts.typesafe_noul(
        [("q1", "query")], plumbing, index=None,
        params={"window": 3, "model": "jev-1.13.0"}, log=lambda m: None,
    )
    order = [doc_id for doc_id, _ in ranking["q1"]]
    assert order == ["d2", "d0", "d1", "d3", "d4", "d5"]
    dump = json.loads((tmp_path / "typesafe_noul_answers.json").read_text())
    assert dump["answered"] == 2 and dump["failed"] == 1
    rows = {r["doc_id"]: r for r in dump["answers"]["q1"]}
    assert rows["d1"]["error"] == "RuntimeError" and rows["d1"]["value"] is None
    assert rows["d2"]["noul"] == 0.6 and dump["input_tokens"] == 200


def test_alias_model_is_refused_before_any_call(plumbing, monkeypatch):
    client = _Client({})
    monkeypatch.setattr(ts, "_client", lambda component: client)
    with pytest.raises(ValueError, match="alias"):
        ts.typesafe_noul(
            [("q1", "query")], plumbing, index=None,
            params={"model": "jev-latest"}, log=lambda m: None,
        )
    assert client.calls == []


def test_state_carries_query_title_and_truncated_abstract():
    doc = _Doc("d", {"title": " T ", "abstract": "a " * 1000})
    state = ts._state("q", doc)
    assert state["query"] == "q" and state["candidate"]["title"] == "T"
    assert len(state["candidate"]["abstract"]) <= ts.ABSTRACT_CHARS


def test_arms_are_registered_and_vectorless_over_a_lexical_base():
    from harness import arms

    assert {"typesafe_noul", "typesafe_score"} <= set(arms.ARMS)
    assert {"typesafe_noul", "typesafe_score"} <= arms.VECTORLESS_OVER_LEXICAL_BASE
