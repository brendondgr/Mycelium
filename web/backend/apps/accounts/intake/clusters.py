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

#: Default thinking-token budget for cluster composition (a harder reasoning task
#: than a plain grouping). Overridable via ``settings.LLM_THINKING_BUDGET``.
COMPOSE_THINKING_BUDGET = 512

#: Cap on the source-text the composer reads (mirrors extract.py's ``_MAX_TEXT``).
_COMPOSE_MAX_CORPUS = 12000

# The composer's contract: a cluster is a THEME whose members are the broad
# research topics Mylo will follow. This is the single reasoning shared by the
# initial profile build (grounded in a source corpus) and the "instruct Mylo" box
# (grounded in a free-text description) — same shape, same theme→topic model, so
# a profile reads identically however it was created.
#
# Breadth is the whole point of the wording below. An earlier version asked for
# "concrete, searchable sub-topics", which made the model restate résumé bullets
# ("nanoscale morphology-ionic conductivity relationships") — technically true of
# the researcher, but so narrow that almost no paper matches. Topics must be the
# names of fields peers would recognise, kept honest by the qualifier the
# researcher actually works under.
_COMPOSE_SYSTEM_PROMPT = (
    "You are Mylo, a research librarian, organising a researcher's interests into "
    "clusters. A cluster is a THEME (a short umbrella label) holding a few BROAD "
    "RESEARCH TOPICS — the recognisable topics Mylo will follow in the "
    "literature. For example:\n"
    '  {"label": "AI & Healthcare", "areas": ["AI agents in healthcare", '
    '"medical imaging", "clinical NLP"]}\n'
    '  {"label": "Robotics", "areas": ["vision-language-action models", '
    '"surgical robotics", "robot learning"]}\n'
    "Rules:\n"
    "- Produce 2 to {max_clusters} clusters; prefer a few sharp themes over many "
    "tiny ones.\n"
    "- Each cluster holds 2-6 topics. Keep every topic BROAD: the name of a "
    "field, sub-field, or method area that many groups work on, usually 2-5 "
    "words — never a sentence and never a project description.\n"
    "- Generalise up from the source material. A single project, technique, "
    "instrument, dataset, or paper title is NOT a topic — name the topic it "
    'belongs to. "Agentic querying over MITRE ATT&CK and CAPEC frameworks" '
    'becomes "AI agents" or "AI for threat intelligence"; "U-Net segmentation of '
    'TEM micrographs" becomes "deep learning for microscopy"; "nanoscale '
    'morphology-ionic conductivity relationships" becomes "solid-state '
    'electrolytes".\n'
    "- Stay broad but stay on target: keep the qualifier that names what the "
    "researcher actually works on. Someone doing agentic AI for healthcare gets "
    '"AI agents in healthcare" — not the bare field "artificial intelligence", '
    'and not "multi-agent triage over EHR FHIR bundles".\n'
    "- Ground every theme and topic in what the researcher told you or the "
    "supplied source text. You MAY add a closely-related topic the researcher "
    "clearly implies, but never drift into unrelated fields or invent "
    "affiliations or accomplishments.\n"
    "- When existing clusters are supplied, KEEP a theme's exact label when it "
    "still fits, so it is recognised as the same cluster; refine or add only "
    "where the new description calls for it.\n"
    "Return ONLY one JSON object, no prose and no markdown fences:\n"
    '  {"clusters": [{"label": <theme>, "areas": [<topic>, ...]}]}'
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


def compose_clusters(
    *,
    instruction: str = "",
    corpus: str = "",
    areas: Sequence[str] = (),
    keywords: Sequence[str] = (),
    statement: str = "",
    existing_clusters: Sequence[dict] = (),
    watch_topics: Sequence[str] = (),
    max_clusters: int = MAX_CLUSTERS,
    max_areas_per_cluster: int | None = None,
    complete: CompleteFn | None = None,
) -> tuple[list[dict], str]:
    """Compose theme→sub-topic clusters from a description and/or a source corpus.

    The single reasoning shared by the initial profile build (``corpus`` = the
    gathered author/résumé text) and the "instruct Mylo" box (``instruction`` =
    the researcher's free-text description). Unlike :func:`propose_clusters` — a
    pure *partition* of already-declared areas — this may **invent** topics
    grounded in the input: each cluster's ``label`` is a theme and its ``areas``
    are the broad research topics Mylo will search on (deliberately generalised
    up from project-level detail, so the feed is not starved).

    ``existing_clusters`` / ``areas`` / ``keywords`` / ``statement`` /
    ``watch_topics`` are the researcher's *current* profile, passed as context so
    the model refines rather than blindly replaces (a persisting theme keeps its
    id via label match). Returns ``(clusters, source)`` with ``source`` one of
    ``"llm"`` or ``"fallback"``. The caller derives the widened area list as the
    union of ``clusters[].areas``; the result is always a valid stable-id
    partition of that union (every sub-topic in exactly one cluster).
    """
    prior = _normalize_clusters(existing_clusters)
    proposal = _llm_compose(
        instruction=instruction,
        corpus=corpus,
        areas=_clean_list(areas),
        keywords=_clean_list(keywords),
        statement=statement,
        existing=prior,
        watch_topics=_clean_list(watch_topics),
        max_clusters=max_clusters,
        complete=complete,
    )
    if proposal is not None:
        composed = _finalize_composed(
            proposal, prior, max_clusters, max_areas_per_cluster
        )
        if composed:
            return composed, "llm"

    # LLM unavailable/unusable: never invent offline. Keep the current grouping
    # when there is one; else group whatever declared areas exist; else nothing.
    if prior:
        return _clamp_composed(prior, max_clusters, max_areas_per_cluster), "fallback"
    declared = _clean_list(areas)
    if declared:
        grouped, _src = propose_clusters(declared, max_clusters=max_clusters)
        return _clamp_composed(grouped, max_clusters, max_areas_per_cluster), "fallback"
    return [], "fallback"


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


# -- LLM compose ------------------------------------------------------------


def _llm_compose(
    *,
    instruction: str,
    corpus: str,
    areas: list[str],
    keywords: list[str],
    statement: str,
    existing: list[dict],
    watch_topics: list[str],
    max_clusters: int,
    complete: CompleteFn | None,
) -> list[dict] | None:
    """Ask the model for theme→sub-topic clusters; ``None`` on any failure.

    Returns raw ``[{label, areas}]`` rows (unvalidated) or ``None`` when the model
    is unreachable or the response has no parseable clusters — the caller then
    degrades deterministically.
    """
    if not (instruction.strip() or corpus.strip() or areas or existing):
        return None  # nothing to reason over
    ask = complete if complete is not None else _compose_complete
    # Plain replace (not str.format): the prompt's JSON examples contain literal
    # braces that would break format's field parsing.
    system = _COMPOSE_SYSTEM_PROMPT.replace("{max_clusters}", str(max_clusters))
    prompt = _build_compose_prompt(
        instruction=instruction,
        corpus=corpus,
        areas=areas,
        keywords=keywords,
        statement=statement,
        existing=existing,
        watch_topics=watch_topics,
        max_clusters=max_clusters,
    )
    try:
        raw = ask(f"{system}\n\n{prompt}")
    except Exception as exc:  # unreachable model → deterministic fallback
        logger.warning("cluster composition LLM unavailable (%s).", exc)
        return None
    return _parse_composed(raw)


def _build_compose_prompt(
    *,
    instruction: str,
    corpus: str,
    areas: list[str],
    keywords: list[str],
    statement: str,
    existing: list[dict],
    watch_topics: list[str],
    max_clusters: int,
) -> str:
    parts: list[str] = []
    if instruction.strip():
        parts.append(
            "The researcher describes what they want to research:\n"
            + instruction.strip()
        )
    if statement.strip():
        parts.append(f"Current research statement: {statement.strip()}")
    if existing:
        parts.append(
            "Their current clusters (keep a theme's label when it still fits):"
        )
        for cluster in existing:
            parts.append(f"- {cluster['label']}: {', '.join(cluster['areas'])}")
    if areas:
        parts.append("Current research areas: " + ", ".join(areas))
    if keywords:
        parts.append("Keywords: " + ", ".join(keywords))
    if watch_topics:
        parts.append("Currently watched topics: " + ", ".join(watch_topics))
    if corpus.strip():
        parts.append(
            "Source text about the researcher "
            "(papers, declared interests, résumé):"
        )
        parts.append(corpus.strip()[:_COMPOSE_MAX_CORPUS])
    parts.append(
        f"\nOrganise this into 2-{max_clusters} theme clusters, each with a few "
        "broad, recognisable research topics — the field names a peer would use, "
        "not restatements of individual projects, methods, or paper titles."
    )
    return "\n".join(parts)


def _parse_composed(raw: str | None) -> list[dict] | None:
    """Pull ``[{label, areas}]`` rows out of the model's JSON — invented areas OK."""
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


def _normalize_clusters(clusters: Sequence[dict]) -> list[dict]:
    """Coerce caller-supplied clusters to ``[{id, label, areas}]`` with valid ids.

    Keeps a supplied id when present (so an existing cluster's identity survives),
    mints a stable one otherwise, and de-duplicates areas across the whole set so
    the result is a partition. Used to normalise ``existing_clusters`` context and
    the offline fallback.
    """
    used_ids: list[str] = []
    assigned: set[str] = set()
    out: list[dict] = []
    for entry in clusters:
        if not isinstance(entry, dict):
            continue
        label = " ".join(str(entry.get("label") or "").split())
        members: list[str] = []
        for area in _clean_list(entry.get("areas")):
            key = area.casefold()
            if key not in assigned:
                assigned.add(key)
                members.append(area)
        if not (label and members):
            continue
        cid = str(entry.get("id") or "").strip() or make_cluster_id(label, used_ids)
        if cid in used_ids:
            cid = make_cluster_id(label, used_ids)
        used_ids.append(cid)
        out.append({"id": cid, "label": label, "areas": members})
    return out


def _finalize_composed(
    proposal: list[dict],
    existing: list[dict],
    max_clusters: int,
    max_areas_per_cluster: int | None,
) -> list[dict]:
    """Turn a raw compose proposal into a valid stable-id partition of its areas.

    Sub-topics are the model's own (invented) strings, not a fixed declared set,
    so — unlike :func:`_finalize` — there is no canonical vocabulary to map back
    to. Areas are de-duplicated across clusters (first wins), each cluster keeps
    the id of an existing cluster whose label matches (case-insensitive) so a
    persisting theme survives a refine, and everything is clamped to the caps.
    """
    prior_ids = {c["label"].casefold(): c["id"] for c in existing}
    used_ids: list[str] = []
    assigned: set[str] = set()
    clusters: list[dict] = []
    for row in proposal:
        label = row["label"]
        members: list[str] = []
        for area in row["areas"]:
            key = area.casefold()
            if key not in assigned:
                assigned.add(key)
                members.append(area)
        if not members:
            continue
        cid = prior_ids.get(label.casefold())
        if not cid or cid in used_ids:
            cid = make_cluster_id(label, used_ids)
        used_ids.append(cid)
        clusters.append({"id": cid, "label": label, "areas": members})
    return _clamp_composed(clusters, max_clusters, max_areas_per_cluster)


def _clamp_composed(
    clusters: list[dict], max_clusters: int, max_areas_per_cluster: int | None
) -> list[dict]:
    """Keep at most ``max_clusters`` clusters, each with at most N sub-topics."""
    limit = max(1, max_clusters)
    out = [dict(c) for c in clusters[:limit]]
    if max_areas_per_cluster is not None:
        for cluster in out:
            cluster["areas"] = cluster["areas"][:max_areas_per_cluster]
    return [c for c in out if c["areas"]]


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

    client = build_llm_client(component="intake.clusters")
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    return response.content


def _compose_complete(prompt: str) -> str | None:
    """Default LLM seam for cluster composition.

    Composition reasons harder than a plain grouping (it invents and themes
    sub-topics), so it asks for ``high`` reasoning and a thinking-token budget —
    the server reads ``thinking_token_budget`` out of ``extra_body`` (default
    :data:`COMPOSE_THINKING_BUDGET`, overridable via ``settings.LLM_THINKING_BUDGET``).
    ``prompt`` already carries the system contract, so it is sent as one message.
    """
    from django.conf import settings

    from apps.core.llm import LLMMessage, ReasoningLevel, build_llm_client

    budget = int(getattr(settings, "LLM_THINKING_BUDGET", COMPOSE_THINKING_BUDGET))
    client = build_llm_client(component="intake.compose_clusters")
    response = client.complete(
        [LLMMessage("user", prompt)],
        reasoning=ReasoningLevel.HIGH,
        extra_body={"thinking_token_budget": budget},
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
