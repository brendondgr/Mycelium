"""The LLM rung: listwise reranking, its position bias, and a pointwise rubric.

Three things are measured here, and the first sentence of the record about any of
them has to be this: **production does not do this.** `apps.content.suggest`
deliberately does *not* reorder — "the returned order is the fused order", and a
model verdict only annotates the item it is about. So these arms measure a
counterfactual: what *would* happen if the model were allowed to rank.

That makes them worth running anyway, for two reasons. The listwise arm is the
one outstanding piece of the audit's W6 ablation, previously blocked on internal
judgments that LongEval already supplies. And the reversed arm answers a question
the record currently answers with speculation: whether the model's output depends
on the order it was handed.

The three arms:

* `llm_rerank` — listwise. The model sees K candidates and returns an ordering.
* `llm_rerank_reversed` — byte-identical prompt construction, candidates presented
  bottom-to-top. Any difference in the resulting ranking is position bias and
  nothing else, because the candidate *set* is unchanged.
* `llm_rubric` — pointwise. Each candidate is scored alone against a fixed rubric,
  so there is no order to be biased by. Slower (one call per pair) and the arm the
  literature expects to be more reliable.

Temperature is pinned to 0 everywhere; a reranker that is not reproducible is not
measurable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .ladder import DEPTH, _docs_by_id, _positional, base_ranking

#: How many candidates the listwise arms show the model at once. Deep enough to
#: be a real reranking task, shallow enough that the model can attend to the whole
#: list — the literature's usual window.
DEFAULT_WINDOW = 20

#: Characters of abstract per candidate. Matches `suggest._ABSTRACT_CHARS`'s
#: intent: enough to judge, not enough to blow the context.
ABSTRACT_CHARS = 600

#: Parallel LLM calls. Mirrors `OPPORTUNITY_LLM_CONCURRENCY`.
CONCURRENCY = 12

#: Where the rubric's raw per-pair verdicts land, next to the TREC run files.
RUBRIC_DUMP_DIR = Path(__file__).resolve().parent.parent / "runs"


def _client(component: str):
    from apps.core.llm import build_llm_client

    return build_llm_client(component=component)


def _brief(index: int, doc: Any) -> str:
    meta = doc.metadata or {}
    title = (meta.get("title") or "(untitled)").strip()
    abstract = " ".join((meta.get("abstract") or "").split())[:ABSTRACT_CHARS]
    line = f"[{index}] {title}"
    if abstract:
        line += f"\n    {abstract}"
    return line


def _listwise_prompt(query_text: str, briefs: Sequence[str]) -> str:
    return "\n".join(
        [
            "You are ranking scientific papers for a researcher's query.",
            "",
            f"Query: {query_text}",
            "",
            "Candidate papers:",
            *briefs,
            "",
            f"Rank ALL {len(briefs)} candidates from most to least relevant to the "
            "query. Judge only topical relevance to the query.",
            'Return JSON only, of the form {"ranking": [3, 1, 7, ...]}, listing '
            "every candidate number exactly once, best first.",
        ]
    )


def _rubric_prompt(query_text: str, doc: Any) -> str:
    meta = doc.metadata or {}
    title = (meta.get("title") or "(untitled)").strip()
    abstract = " ".join((meta.get("abstract") or "").split())[:ABSTRACT_CHARS]
    return "\n".join(
        [
            "Score one scientific paper for its relevance to a query.",
            "",
            f"Query: {query_text}",
            "",
            f"Paper: {title}",
            f"Abstract: {abstract}" if abstract else "Abstract: (none)",
            "",
            "Score 0-3, where 3 means the paper directly addresses the query, "
            "2 means it is clearly on topic, 1 means it is loosely related, and "
            "0 means it is off topic.",
            'Return JSON only, of the form {"score": 2}.',
        ]
    )


def _parse_ranking(raw: str | None, count: int) -> list[int] | None:
    """`[0-based positions]` from the model's JSON, or `None` if unusable.

    Defensive by design: a reranker that silently falls back to a partial parse
    would report the base ranking's numbers under the reranker's name. Anything
    unparseable returns `None` and the caller keeps the base order for that query,
    which is recorded rather than hidden.
    """
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    values = payload.get("ranking")
    if not isinstance(values, list):
        return None
    seen: list[int] = []
    for value in values:
        try:
            position = int(value) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= position < count and position not in seen:
            seen.append(position)
    # Anything the model dropped keeps its original relative order at the tail.
    seen.extend(i for i in range(count) if i not in seen)
    return seen if seen else None


def _parse_score(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    value = payload.get("score")
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 3.0 else None


def _listwise(
    queries,
    docs,
    *,
    index,
    pool_per_interest,
    params,
    collection,
    log,
    reverse: bool,
) -> dict[str, list[tuple[str, float]]]:
    params = params or {}
    window = int(params.get("window", DEFAULT_WINDOW))
    base_name = params.get("base", "fusion_union_pool")
    model = params.get("llm_model") or None

    by_id = _docs_by_id(docs)
    base = base_ranking(
        base_name, queries, docs, index=index,
        pool_per_interest=pool_per_interest, log=log, collection=collection,
    )
    client = _client("eval-llm-rerank")
    direction = "reversed" if reverse else "as-ranked"
    log(f"LLM listwise rerank ({direction}) of top-{window} from '{base_name}' …")

    def one(item):
        query_id, query_text = item
        candidates = [doc_id for doc_id, _ in base.get(query_id, [])]
        head, tail = candidates[:window], candidates[window:]
        shown = list(reversed(head)) if reverse else list(head)
        briefs = [
            _brief(i, by_id[doc_id])
            for i, doc_id in enumerate(shown, start=1)
            if doc_id in by_id
        ]
        present = [doc_id for doc_id in shown if doc_id in by_id]
        if not present:
            return query_id, head + tail, False
        try:
            response = client.complete(
                _listwise_prompt(query_text, briefs),
                temperature=0.0,
                max_tokens=1024,
                model=model,
            )
        except Exception as exc:  # noqa: BLE001 - a failed call must not kill the run
            log(
                f"  query {query_id}: LLM call failed "
                f"({type(exc).__name__}); base order kept"
            )
            return query_id, head + tail, False
        order = _parse_ranking(response.content, len(present))
        if order is None:
            log(f"  query {query_id}: unparseable verdict; base order kept")
            return query_id, head + tail, False
        return query_id, [present[i] for i in order] + tail, True

    ranking: dict[str, list[tuple[str, float]]] = {}
    ok = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        results = enumerate(pool.map(one, queries), start=1)
        for n, (query_id, ordering, parsed) in results:
            ranking[query_id] = _positional(ordering, DEPTH)
            ok += int(parsed)
            if n % 25 == 0:
                log(f"  reranked {n}/{len(queries)} queries")
    log(f"LLM listwise: {ok}/{len(queries)} queries reranked from a parsed verdict")
    return ranking


def llm_rerank(
    queries, docs, *, index, pool_per_interest=100, params=None, collection=None,
    log: Callable[[str], None] = print, **_: Any,
):
    """Listwise LLM reranking of the base ranking's top window."""
    return _listwise(
        queries, docs, index=index, pool_per_interest=pool_per_interest,
        params=params, collection=collection, log=log, reverse=False,
    )


def llm_rerank_reversed(
    queries, docs, *, index, pool_per_interest=100, params=None, collection=None,
    log: Callable[[str], None] = print, **_: Any,
):
    """The same call with the candidate list presented bottom-to-top.

    The diagnostic. The candidate *set* is identical, so any gap between this
    arm's metrics and `llm_rerank`'s is caused by input order alone. A model free
    of position bias would score the same either way.
    """
    return _listwise(
        queries, docs, index=index, pool_per_interest=pool_per_interest,
        params=params, collection=collection, log=log, reverse=True,
    )


def llm_rubric(
    queries, docs, *, index, pool_per_interest=100, params=None, collection=None,
    log: Callable[[str], None] = print, **_: Any,
):
    """Pointwise rubric scoring — each candidate judged alone, so order cannot bias it.

    Ties are broken by the base ranking's position, which is the honest default: a
    0-3 rubric cannot separate twenty candidates on its own, and pretending
    otherwise would let `ir_measures` invent an order.
    """
    params = params or {}
    window = int(params.get("window", DEFAULT_WINDOW))
    base_name = params.get("base", "fusion_union_pool")
    model = params.get("llm_model") or None

    by_id = _docs_by_id(docs)
    base = base_ranking(
        base_name, queries, docs, index=index,
        pool_per_interest=pool_per_interest, log=log, collection=collection,
    )
    client = _client("eval-llm-rubric")
    log(f"LLM pointwise rubric over top-{window} from '{base_name}' …")

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
            response = client.complete(
                _rubric_prompt(query_text, by_id[doc_id]),
                temperature=0.0,
                max_tokens=128,
                model=model,
            )
        except Exception:  # noqa: BLE001
            return query_id, doc_id, rank, None
        return query_id, doc_id, rank, _parse_score(response.content)

    scored: dict[str, list[tuple[str, float, int]]] = {}
    parsed = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        results = enumerate(pool.map(one, pairs), start=1)
        for n, (query_id, doc_id, rank, score) in results:
            parsed += int(score is not None)
            usable = score if score is not None else -1.0
            scored.setdefault(query_id, []).append((doc_id, usable, rank))
            if n % 250 == 0:
                log(f"  scored {n}/{len(pairs)} pairs")
    log(f"LLM rubric: {parsed}/{len(pairs)} pairs returned a usable score")

    # Persist the raw verdicts. The ranking alone cannot answer the question the
    # rubric exists to answer — whether the model can separate relevant from
    # irrelevant at all — because a 0-3 scale over a 20-item window produces heavy
    # ties that the base rank then breaks. Without the scores, an arm that ties
    # everything and an arm that judges perfectly are indistinguishable from their
    # run file. Written next to the run files; regenerable, gitignored.
    dump = RUBRIC_DUMP_DIR / "llm_rubric_scores.json"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(
        json.dumps(
            {
                qid: [
                    {"doc_id": doc_id, "score": score, "base_rank": rank}
                    for doc_id, score, rank in rows
                ]
                for qid, rows in scored.items()
            },
            indent=1,
            sort_keys=True,
        )
    )
    log(f"rubric verdicts written: {dump}")

    ranking: dict[str, list[tuple[str, float]]] = {}
    for query_id, _query_text in queries:
        candidates = [doc_id for doc_id, _ in base.get(query_id, [])]
        head = scored.get(query_id, [])
        # Sort by rubric score desc, then by the base rank the model never saw.
        head.sort(key=lambda row: (-row[1], row[2]))
        ordering = [doc_id for doc_id, _, _ in head] + candidates[window:]
        ranking[query_id] = _positional(ordering, DEPTH)
    return ranking


LLM_ARMS: dict[str, Callable[..., Any]] = {
    "llm_rerank": llm_rerank,
    "llm_rerank_reversed": llm_rerank_reversed,
    "llm_rubric": llm_rubric,
}
