"""Propose interest **clusters** at intake — LLM grouping with a geometric fallback.

When Mylo has drafted a researcher's ``areas`` (or after an author import), it
proposes an organisation of those areas into a few named clusters that the user
then adjusts freely (drag / rename / merge / split). Open Decision D-C1: the
language model proposes the grouping *and* the labels; when the model is
unavailable we degrade to a deterministic geometric agglomerative grouping with
generic labels — the same degrade-to-status convention as the rest of intake.

Everything is pure over plain data (an injectable ``complete`` LLM seam and an
injectable ``embed`` seam) so the proposer runs offline in tests. The output is
always a **valid partition**: every input area lands in exactly one cluster with
a stable id (:func:`apps.content.clustering.make_cluster_id`), so the result can
be written straight into the v2 interests contract.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence

from apps.content.clustering import MAX_CLUSTERS, make_cluster_id

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]
EmbedFn = Callable[[list[str]], list[list[float]] | None]

_SYSTEM_PROMPT = (
    "You are Mylo, a research librarian. Given a researcher's list of research "
    "areas, group them into a small number (2 to 6) of coherent, well-named "
    "clusters — each a distinct strand of their work (e.g. \"Medical AI Agents\", "
    "\"Oceanography & Data Assimilation\"). Every area must go in exactly one "
    "cluster; do not invent, drop, split, or reword areas. Prefer fewer, "
    "meaningful clusters over many tiny ones. Return ONLY one JSON object:\n"
    '  {"clusters": [{"label": <short name>, "areas": [<verbatim area>, ...]}]}\n'
    "No prose outside the JSON, no markdown fences."
)


def propose_clusters(
    areas: Sequence[str],
    *,
    keywords: Sequence[str] | None = None,
    statement: str = "",
    complete: CompleteFn | None = None,
    embed: EmbedFn | None = None,
    max_clusters: int = MAX_CLUSTERS,
) -> tuple[list[dict], str]:
    """Propose ``[{id, label, areas}]`` clusters over ``areas`` + the source used.

    Returns ``(clusters, source)`` where ``source`` is ``"llm"``, ``"geometric"``,
    or ``"single"``. Always a valid partition of the (cleaned) areas. With 0/1
    areas there is nothing to organise — one cluster (or none).
    """
    clean = _clean_list(areas)
    if not clean:
        return [], "single"
    if len(clean) == 1:
        return [_cluster(clean[0], clean)], "single"

    proposal = _llm_propose(clean, keywords, statement, complete)
    if proposal is not None:
        return _finalize(proposal, clean), "llm"

    groups = _geometric_groups(clean, embed=embed, max_clusters=max_clusters)
    labelled = [{"label": f"Group {i + 1}", "areas": g} for i, g in enumerate(groups)]
    return _finalize(labelled, clean), "geometric"


def sort_into_clusters(
    existing: Sequence[dict],
    new_areas: Sequence[str],
    *,
    embed: EmbedFn | None = None,
) -> list[dict]:
    """Place ``new_areas`` into the nearest ``existing`` cluster (one-click sort).

    The "Mylo, sort these" affordance for the profile-edit organiser: existing
    cluster **ids are preserved** (never regenerated), and each new area is routed
    to the geometrically-nearest cluster (mean cosine to its areas), or the first
    cluster when no embedder is available. Returns the updated cluster list.
    """
    clusters = [
        {"id": c["id"], "label": c["label"], "areas": _clean_list(c.get("areas"))}
        for c in existing
        if c.get("id") and c.get("label")
    ]
    fresh = [a for a in _clean_list(new_areas) if not _already_in(a, clusters)]
    if not clusters:
        proposed, _src = propose_clusters(fresh, embed=embed)
        return proposed
    if not fresh:
        return clusters

    embedder = embed or _default_embed
    vectors = embedder([*_all_areas(clusters), *fresh]) if fresh else None
    if not vectors:
        clusters[0]["areas"].extend(fresh)  # no embedder → dump into the first
        return clusters

    index = _vector_index([*_all_areas(clusters), *fresh], vectors)
    for area in fresh:
        vec = index.get(area)
        best = max(
            clusters,
            key=lambda c: _mean_cosine(vec, [index.get(a) for a in c["areas"]]),
        )
        best["areas"].append(area)
    return clusters


# -- LLM --------------------------------------------------------------------


def _llm_propose(
    areas: list[str],
    keywords: Sequence[str] | None,
    statement: str,
    complete: CompleteFn | None,
) -> list[dict] | None:
    ask = complete if complete is not None else _default_complete
    try:
        raw = ask(_build_prompt(areas, keywords, statement))
    except Exception as exc:  # unreachable model → geometric fallback
        logger.warning("cluster proposal LLM unavailable (%s); using geometry.", exc)
        return None
    return _parse(raw, areas)


def _build_prompt(
    areas: list[str], keywords: Sequence[str] | None, statement: str
) -> str:
    parts = []
    if statement.strip():
        parts.append(f"Researcher statement: {statement.strip()}")
    kw = _clean_list(keywords)
    if kw:
        parts.append(f"Keywords: {', '.join(kw)}")
    parts.append("Research areas:")
    parts.extend(f"- {area}" for area in areas)
    parts.append(f"\nGroup these {len(areas)} areas into 2-{MAX_CLUSTERS} clusters.")
    return "\n".join(parts)


def _parse(raw: str | None, areas: list[str]) -> list[dict] | None:
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    rows = data.get("clusters") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = " ".join(str(row.get("label") or "").split())
        members = _clean_list(row.get("areas"))
        if label and members:
            out.append({"label": label, "areas": members})
    return out or None


# -- geometric fallback -----------------------------------------------------


def _geometric_groups(
    areas: list[str], *, embed: EmbedFn | None, max_clusters: int
) -> list[list[str]]:
    """Average-link agglomerative grouping of areas by embedding cosine.

    Merges the two most similar clusters until the count reaches a modest target
    (``ceil(n/3)``, clamped to ``[2, max_clusters]``). With no embedder every area
    becomes its own cluster up to the target, then the tail is folded into the
    last — a crude but deterministic and never-crashing partition.
    """
    target = max(2, min(max_clusters, -(-len(areas) // 3)))
    embedder = embed or _default_embed
    vectors = embedder(areas)
    if not vectors:
        # No embeddings: chunk in order into ``target`` groups.
        return _chunk(areas, target)

    index = _vector_index(areas, vectors)
    groups: list[list[str]] = [[a] for a in areas]
    while len(groups) > target:
        best_pair = None
        best_sim = -2.0
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                sim = _group_sim(groups[i], groups[j], index)
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (i, j)
        if best_pair is None:
            break
        i, j = best_pair
        groups[i].extend(groups[j])
        del groups[j]
    return groups


def _group_sim(a: list[str], b: list[str], index: dict) -> float:
    sims = [
        _cosine(index.get(x), index.get(y))
        for x in a
        for y in b
        if index.get(x) is not None and index.get(y) is not None
    ]
    return sum(sims) / len(sims) if sims else 0.0


def _chunk(items: list[str], parts: int) -> list[list[str]]:
    parts = max(1, min(parts, len(items)))
    size = -(-len(items) // parts)
    return [items[i : i + size] for i in range(0, len(items), size)]


# -- partition finalize -----------------------------------------------------


def _finalize(proposal: list[dict], areas: list[str]) -> list[dict]:
    """Coerce a raw proposal into a valid, stable-id partition of ``areas``.

    Maps each proposed area back to the canonical declared spelling, drops
    phantoms, keeps the first cluster to claim a duplicated area, and sweeps any
    unassigned area into a trailing "More" cluster so nothing is lost. Assigns a
    fresh stable id per cluster.
    """
    canonical = {a.casefold(): a for a in areas}
    used_ids: list[str] = []
    assigned: set[str] = set()
    clusters: list[dict] = []
    for row in proposal[:MAX_CLUSTERS]:
        members: list[str] = []
        for candidate in row.get("areas", []):
            area = canonical.get(str(candidate).casefold())
            if area is not None and area not in assigned:
                assigned.add(area)
                members.append(area)
        if not members:
            continue
        cid = make_cluster_id(row["label"], used_ids)
        used_ids.append(cid)
        clusters.append({"id": cid, "label": row["label"], "areas": members})

    orphans = [a for a in areas if a not in assigned]
    if orphans:
        if clusters and len(clusters) >= MAX_CLUSTERS:
            clusters[-1]["areas"].extend(orphans)  # respect the cap
        elif clusters and len(orphans) == 1:
            clusters[-1]["areas"].extend(orphans)
        else:
            cid = make_cluster_id("More", used_ids)
            clusters.append({"id": cid, "label": "More", "areas": orphans})
    if not clusters:
        return [_cluster("All interests", areas)]
    return clusters


def _cluster(label: str, areas: list[str]) -> dict:
    return {"id": make_cluster_id(label), "label": label, "areas": list(areas)}


# -- vector helpers ---------------------------------------------------------


def _vector_index(areas: list[str], vectors: list[list[float]]) -> dict:
    return {area: vec for area, vec in zip(areas, vectors, strict=False)}


def _mean_cosine(vec, others: list) -> float:
    sims = [_cosine(vec, o) for o in others if o is not None]
    return sum(sims) / len(sims) if sims else 0.0


def _cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _all_areas(clusters: list[dict]) -> list[str]:
    return [a for c in clusters for a in c["areas"]]


def _already_in(area: str, clusters: list[dict]) -> bool:
    fold = area.casefold()
    return any(a.casefold() == fold for c in clusters for a in c["areas"])


# -- default seams ----------------------------------------------------------


def _default_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client()
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    return response.content


def _default_embed(texts: list[str]) -> list[list[float]] | None:
    from apps.content.embeddings import embed_texts

    return embed_texts(texts)


def _clean_list(value: Sequence[str] | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out
