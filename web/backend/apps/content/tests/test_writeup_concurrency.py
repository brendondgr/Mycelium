"""Parallel write-ups must produce exactly what the serial path produced.

The batches and the précis calls are independent by construction; these tests
pin the two properties a wrong number would come from — the prompts are the
same (same seeds, same batches) and every candidate still gets a write-up.
"""

from __future__ import annotations

import json
import threading

import pytest

from apps.content import cluster_fit, comprehension
from apps.content.clustering import Cluster


class _Item:
    def __init__(self, i: int) -> None:
        self.id = f"d{i}"
        self.metadata = {"title": f"Paper {i}", "abstract": "about graphs " * 20}


def _complete_factory(calls: list[str], *, lock: threading.Lock):
    def complete(prompt: str) -> str:
        with lock:
            calls.append(prompt)
        # Answer every candidate number the prompt lists, with the mandatory caveat.
        numbers = [
            int(line.split("]")[0][1:])
            for line in prompt.splitlines()
            if line.startswith("[") and "]" in line
        ]
        return json.dumps(
            {
                "items": [
                    {
                        "n": n,
                        "verdict": "skim",
                        "matters": "m",
                        "use": "u",
                        "take": "t",
                        "caveat": "c",
                        "bridge": "",
                        "differs": "",
                    }
                    for n in numbers
                ]
            }
        )

    return complete


def _candidates(n: int) -> list[cluster_fit.Candidate]:
    return [
        cluster_fit.Candidate(
            item=_Item(i), precis=None, evidence=cluster_fit.Evidence(position=i + 1)
        )
        for i in range(n)
    ]


@pytest.mark.parametrize("concurrency", [1, 8])
def test_parallel_batches_send_the_same_prompts_and_cover_every_candidate(
    settings, concurrency
):
    settings.CLUSTER_FIT_BATCH = 4
    cluster = Cluster(id="c1", label="Graphs", areas=["graphs"])
    lock = threading.Lock()
    calls: list[str] = []
    out = cluster_fit.write_cluster_fits(
        "reader",
        cluster,
        ["Other"],
        _candidates(10),
        depth=10,
        complete=_complete_factory(calls, lock=lock),
        seed=7,
        concurrency=concurrency,
    )
    assert len(out) == 10
    assert all(w["verdict"] == "skim" for w in out.values())
    assert len(calls) == 3  # 10 candidates in batches of 4
    assert sorted(calls) == sorted(set(calls))  # three distinct prompts, no repeats


def test_serial_and_parallel_write_identical_prompts(settings):
    settings.CLUSTER_FIT_BATCH = 3
    cluster = Cluster(id="c1", label="Graphs", areas=["graphs"])
    prompts = {}
    for concurrency in (1, 6):
        lock = threading.Lock()
        calls: list[str] = []
        cluster_fit.write_cluster_fits(
            "reader",
            cluster,
            [],
            _candidates(9),
            depth=9,
            complete=_complete_factory(calls, lock=lock),
            seed=3,
            concurrency=concurrency,
        )
        prompts[concurrency] = sorted(calls)
    assert prompts[1] == prompts[6]


def test_precis_extraction_runs_in_parallel_and_keys_by_id(settings, monkeypatch):
    settings.WRITEUP_LLM_CONCURRENCY = 8
    seen: list[str] = []
    lock = threading.Lock()

    def fake_one(item, ask):
        with lock:
            seen.append(item.id)
        return {"summary": item.id}

    monkeypatch.setattr(comprehension, "_one", fake_one)
    items = [_Item(i) for i in range(12)]
    out = comprehension.extract_many(items, complete=lambda p: "")
    assert set(out) == {f"d{i}" for i in range(12)}
    assert sorted(seen) == sorted(f"d{i}" for i in range(12))


def test_budget_setting_is_read(settings):
    settings.WRITEUP_LLM_CONCURRENCY = 32
    assert comprehension.writeup_concurrency() == 32
    assert cluster_fit.writeup_concurrency() == 32
