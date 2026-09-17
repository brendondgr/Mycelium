"""The TypeSafe rung: one calibrated probability per (query, document) pair.

As with :mod:`.llm_rerank`, the first sentence of the record about these arms is
**production does not do this.** They measure a counterfactual: what would
happen if a decision model were allowed to reorder the first stage's window.

Two arms, both pointwise — each candidate judged alone against the query, so
input order cannot bias it (C-015 is the reason listwise is not offered):

* `typesafe_noul` — one yes/no question per pair, TypeSafe's own re-ranking
  cookbook shape. The answer is a probability in [0, 1]; the window is sorted
  by it, base rank breaking ties.
* `typesafe_score` — one four-level Score per pair whose level texts are the
  0–3 rubric `llm_rerank._rubric_prompt` uses, so C-016 is re-tested like for
  like: the answer is a probability-weighted mean on 0–3 instead of an emitted
  integer, which is the specific mechanism that collapsed the LLM rubric to
  1.99 distinct values per window.

Both arms dump every raw answer next to the run file
(`eval/runs/typesafe_<arm>_answers.json`), because the ranking alone cannot say
whether the model separates relevant from irrelevant at all. Token usage from
the API's own `usage` block is summed and logged; the experiment copies it.

The model is **pinned**: an arm refuses to run against `jev-latest`, because a
number in the record has to name the thing that produced it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .ladder import DEPTH, _docs_by_id, _positional, base_ranking
from .llm_rerank import ABSTRACT_CHARS, CONCURRENCY, DEFAULT_WINDOW

#: Where the raw answers land, next to the TREC run files.
DUMP_DIR = Path(__file__).resolve().parent.parent / "runs"

#: The four rubric levels, low to high — the same words `_rubric_prompt` uses.
SCORE_LEVELS = (
    "Off topic: the paper does not address the query's subject.",
    "Loosely related: shares the field or a term, but does not address the query.",
    "Clearly on topic: addresses the query's subject, if not its specific question.",
    "Directly addresses the query: the paper is about what the query asks for.",
)


def _client(component: str):
    from apps.core.systemone import build_systemone_client

    return build_systemone_client(component=component)


def _pinned_model(params: dict) -> str:
    from apps.core.systemone import is_pinned
    from django.conf import settings

    model = params.get("model") or settings.TYPESAFE_MODEL
    if not is_pinned(model):
        raise ValueError(
            f"typesafe arms refuse alias {model!r}; set params.model to a version"
        )
    return str(model)


def _state(query_text: str, doc: Any) -> dict:
    meta = doc.metadata or {}
    return {
        "query": query_text,
        "candidate": {
            "title": (meta.get("title") or "(untitled)").strip(),
            "abstract": " ".join((meta.get("abstract") or "").split())[:ABSTRACT_CHARS],
        },
    }


def noul_question():
    from apps.core.systemone import noul

    return noul(
        "Is this scientific paper relevant to the query? Judge only topical "
        "relevance of the paper to what the query asks for.",
        true="The paper addresses the subject the query asks about.",
        false=(
            "The paper is on a different subject, or shares only a word or a "
            "broad field with the query."
        ),
    )


def score_question():
    from apps.core.systemone import score

    return score(
        "Score one scientific paper for its relevance to the query.",
        SCORE_LEVELS,
    )


def _value(answer: Any) -> float | None:
    for name in ("noul", "score"):
        value = getattr(answer, name, None)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _pointwise(
    queries,
    docs,
    *,
    index,
    pool_per_interest,
    params,
    collection,
    log: Callable[[str], None],
    arm_name: str,
    question_factory: Callable[[], Any],
) -> dict[str, list[tuple[str, float]]]:
    params = params or {}
    window = int(params.get("window", DEFAULT_WINDOW))
    base_name = params.get("base", "bm25_only")
    model = _pinned_model(params)

    by_id = _docs_by_id(docs)
    base = base_ranking(
        base_name, queries, docs, index=index,
        pool_per_interest=pool_per_interest, log=log, collection=collection,
    )
    client = _client(f"eval-{arm_name}")
    log(
        f"TypeSafe pointwise ({arm_name}, {model}) over top-{window} "
        f"from '{base_name}' …"
    )

    pairs: list[tuple[str, str, str, int]] = []
    for query_id, query_text in queries:
        candidates = [doc_id for doc_id, _ in base.get(query_id, [])]
        for rank, doc_id in enumerate(candidates[:window]):
            if doc_id in by_id:
                pairs.append((query_id, query_text, doc_id, rank))
    log(f"  {len(pairs)} (query, document) pairs to score")

    def one(pair):
        query_id, query_text, doc_id, rank = pair
        try:
            result = client.ask(
                _state(query_text, by_id[doc_id]),
                {"relevance": question_factory()},
                model=model,
            )
        except Exception as exc:  # noqa: BLE001 — a failed pair is a recorded pair
            return query_id, doc_id, rank, None, None, f"{type(exc).__name__}"
        answer = result.answers.get("relevance")
        return query_id, doc_id, rank, _value(answer), result, None

    scored: dict[str, list[tuple[str, float, int]]] = {}
    dump: dict[str, list[dict]] = {}
    answered = failed = 0
    input_tokens = output_tokens = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        results = enumerate(pool.map(one, pairs), start=1)
        for n, (query_id, doc_id, rank, value, result, error) in results:
            if value is None:
                failed += 1
            else:
                answered += 1
                input_tokens += result.usage["input_tokens"]
                output_tokens += result.usage["output_tokens"]
            usable = value if value is not None else -1.0
            scored.setdefault(query_id, []).append((doc_id, usable, rank))
            row = {"doc_id": doc_id, "base_rank": rank, "value": value}
            if result is not None:
                row.update(result.answers_as_dicts().get("relevance", {}))
                row["input_tokens"] = result.usage["input_tokens"]
            if error:
                row["error"] = error
            dump.setdefault(query_id, []).append(row)
            if n % 250 == 0:
                log(f"  scored {n}/{len(pairs)} pairs")
    log(
        f"TypeSafe {arm_name}: {answered}/{len(pairs)} pairs answered, "
        f"{failed} failed; "
        f"{input_tokens} input / {output_tokens} output tokens"
    )

    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    dump_path = DUMP_DIR / f"typesafe_{arm_name}_answers.json"
    dump_path.write_text(
        json.dumps(
            {
                "arm": arm_name,
                "model": model,
                "base": base_name,
                "window": window,
                "pairs": len(pairs),
                "answered": answered,
                "failed": failed,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "answers": dump,
            },
            indent=1,
            sort_keys=True,
        )
    )
    log(f"answers written: {dump_path}")

    ranking: dict[str, list[tuple[str, float]]] = {}
    for query_id, _query_text in queries:
        candidates = [doc_id for doc_id, _ in base.get(query_id, [])]
        head = scored.get(query_id, [])
        # Sort by the model's value desc, then by the base rank the model never saw.
        head.sort(key=lambda row: (-row[1], row[2]))
        ordering = [doc_id for doc_id, _, _ in head] + candidates[window:]
        ranking[query_id] = _positional(ordering, DEPTH)
    return ranking


def typesafe_noul(
    queries, docs, *, index, pool_per_interest=100, params=None, collection=None,
    log: Callable[[str], None] = print, **_: Any,
):
    """One yes/no probability per pair; the window sorted by it."""
    return _pointwise(
        queries, docs, index=index, pool_per_interest=pool_per_interest,
        params=params, collection=collection, log=log,
        arm_name="noul", question_factory=noul_question,
    )


def typesafe_score(
    queries, docs, *, index, pool_per_interest=100, params=None, collection=None,
    log: Callable[[str], None] = print, **_: Any,
):
    """One four-level rubric Score per pair — the LLM rubric's scale, continuous."""
    return _pointwise(
        queries, docs, index=index, pool_per_interest=pool_per_interest,
        params=params, collection=collection, log=log,
        arm_name="score", question_factory=score_question,
    )


TYPESAFE_ARMS: dict[str, Callable[..., Any]] = {
    "typesafe_noul": typesafe_noul,
    "typesafe_score": typesafe_score,
}
