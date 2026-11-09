"""The ``corpus`` group: search the shared corpus, and read one item.
Instance-wide output: the corpus is the same for everyone on the instance."""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, Result

from . import common

TYPES = ("paper", "grant", "fellowship", "conference")


def corpus_search(caller, query, types=None, limit=8):
    from tools.retrieval.read import SearchFilters, embed_query, run_search
    from tools.retrieval.search import normalize_query

    types = tuple(t for t in (types or ()) if t in TYPES)
    limit = max(1, min(int(limit or 8), 20))
    vector = None
    try:
        vector = embed_query(normalize_query(query))
    except Exception:  # lexical channels still answer
        vector = None
    result = run_search(
        query, filters=SearchFilters(types=types), limit=limit, query_vector=vector
    )
    if not result.items:
        return Result(content=f"Nothing in the corpus matches “{query}”.")
    refs, lines = [], []
    for item in result.items:
        info = common.item_info(item)
        refs.append(info)
        meta = item.metadata or {}
        extra = meta.get("year") or meta.get("deadline") or ""
        lines.append(
            f"- {{ref:{info.ref}}} [{item.type}] {common.item_title(item)}"
            + (f" ({extra})" if extra else "")
        )
    note = " Few strong matches; say so." if result.confidence == "low" else ""
    return Result(
        content=f"{result.count} matches; the best {len(lines)}:{note}\n"
        + "\n".join(lines),
        refs=refs,
    )


def corpus_item(caller, item):
    from django.utils import timezone

    from tools.recommendation.read import ItemComprehension
    from tools.retrieval.read import ContentDeadline, ContentItem, is_live

    row = ContentItem.objects.filter(pk=common.ref_key(item)).first()
    if row is None:
        raise FunctionError("not_found", "That item is no longer in the corpus.")
    meta = row.metadata or {}
    info = common.item_info(row)
    lines = [f"{{ref:{info.ref}}} [{row.type}] {common.item_title(row)}"]
    for key in (
        "authors",
        "venue",
        "year",
        "sponsor",
        "agency",
        "amount",
        "location",
        "start_date",
        "end_date",
        "deadline",
    ):
        value = meta.get(key)
        if value:
            if isinstance(value, list):
                value = ", ".join(map(str, value[:8]))
            lines.append(f"{key.replace('_', ' ').title()}: {common.clip(value, 300)}")
    if row.source_url:
        lines.append(f"Link: {row.source_url}")
    live = is_live(row.type, meta, timezone.localdate().isoformat())
    lines.append("Still open/current: " + ("yes" if live else "no (past or expired)"))
    for d in ContentDeadline.objects.filter(content=row)[:6]:
        when = getattr(d, "due_date", None) or ""
        lines.append(f"Deadline ({d.kind}): {when}")
    comp = ItemComprehension.objects.filter(content=row).first()
    if comp is not None:
        for field in ("problem", "method", "setting"):
            value = getattr(comp, field, "")
            if value:
                lines.append(
                    f"{field.title()} (Mycelium's reading): {common.clip(value, 300)}"
                )
    abstract = (
        meta.get("abstract") or meta.get("summary") or meta.get("description") or ""
    )
    if abstract:
        lines.append("Abstract:\n" + str(abstract)[:4000])
    return Result(content="\n".join(lines), refs=[info], untrusted=True)
