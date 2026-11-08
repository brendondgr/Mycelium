"""Stage one of the model pipeline: read one item, once, for everybody.

Prompt A. A careful reader produces a structured précis of a single item for
later use by someone whose interests are unknown. No audience, no relevance
judgement, no enthusiasm — the reader is *deliberately* absent from the input,
because that is what lets one extraction serve every user and every theme
indefinitely.

Two things follow from being profile-blind, and they are the whole reason the
stage exists:

* **Depth.** The fit stage that follows reads a real précis instead of six
  hundred truncated characters of abstract. Shallow write-ups were a shallow
  *input* problem, not a prompting one.
* **Cost.** One call per item, ever, against one call per (item, reader, theme)
  otherwise. On a corpus shared by every reader that is the largest saving in
  the system, and getting the key wrong in the other direction — keying the
  précis on the pair — evaporates it.

Reuse is the default (plan §19). :func:`comprehend` serves from store unless the
prompt version moved or the item's own source text changed; nothing else
invalidates, and in particular time alone never does.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from tools.retrieval.models import ContentItem, ItemComprehension

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]

#: Stamped on every stored précis. **Bump this whenever the prompt below
#: changes.** Without the stamp a rubric change leaves the store silently mixing
#: two rubrics, which is unreadable in the output and undebuggable in the eval
#: harness; with it, the mixed rows simply refresh on their next visit.
PROMPT_VERSION = "a1"

_SYSTEM_PROMPT = (
    "You are a careful reader producing a structured précis of one research "
    "item for later use by someone whose interests you do not know.\n"
    "Return ONLY one JSON object with exactly these keys:\n"
    '  {"problem": <the problem addressed>, "method": <the method or '
    'approach>, "setting": <the data, cohort, or setting>, "claim": <the '
    'headline claim>, "limitations": <limitations the authors themselves '
    'state>, "reusable": <what an outside researcher could concretely reuse — '
    "a method, a dataset, a baseline, a negative result, an evaluation "
    'protocol>, "thin": <true only if the source text is too sparse to '
    "support a précis>}\n"
    "Rules: no audience, no relevance judgement, no enthusiasm, no "
    "recommendation. Ground every field in the text you are given; leave a "
    "field as an empty string rather than inferring it. If the text is too "
    'thin to support a précis, set "thin" to true and leave the fields empty '
    "— that is a valid answer and is better than a fabrication. No prose "
    "outside the JSON, no markdown fences."
)

_FIELDS = ("problem", "method", "setting", "claim", "limitations", "reusable")


def source_fingerprint(item: ContentItem) -> str:
    """A stable digest of the text a précis is built from.

    Only the fields the prompt actually reads. An abstract backfilled after an
    empty first pass changes this, which correctly invalidates the précis (and
    cascades to the write-ups built on it); a metadata edit that changes nothing
    the model saw does not.
    """
    meta = item.metadata or {}
    payload = "␟".join(
        str(meta.get(key) or "")
        for key in ("title", "name", "abstract", "summary", "description", "venue")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def is_current(row: ItemComprehension, item: ContentItem) -> bool:
    """Whether a stored précis still answers the question it was asked."""
    return (
        row.prompt_version == PROMPT_VERSION
        and row.source_fingerprint == source_fingerprint(item)
    )


def load_comprehensions(
    items: Iterable[ContentItem],
) -> dict[str, ItemComprehension]:
    """Stored précis for ``items``, keyed by content id — current ones only.

    One query. A stale row is left out rather than returned, so a caller either
    gets something it can use or knows it must compute.
    """
    by_id = {str(item.id): item for item in items}
    if not by_id:
        return {}
    out: dict[str, ItemComprehension] = {}
    for row in ItemComprehension.objects.filter(content_id__in=list(by_id)):
        item = by_id.get(str(row.content_id))
        if item is not None and is_current(row, item):
            out[str(row.content_id)] = row
    return out


def extract_many(
    items: Sequence[ContentItem], *, complete: CompleteFn | None = None
) -> dict[str, dict]:
    """Call the model for each item and return the parsed fields, keyed by id.

    **Pure** with respect to the database — no reads, no writes — so it is safe to
    run in a worker thread alongside other targets' scoring. The DB halves are
    :func:`load_comprehensions` before it and :func:`store_comprehensions` after.

    Never raises. A model that is unreachable or unparseable simply yields no
    entry for that item, and the fit stage downstream degrades to the abstract.
    """
    ask = complete if complete is not None else _settings_complete
    out: dict[str, dict] = {}
    if not items:
        return out
    # Items are independent, so the calls run side by side up to
    # ``WRITEUP_LLM_CONCURRENCY``; vLLM batches concurrent requests. The result
    # is keyed by id, so completion order is irrelevant.
    workers = max(1, min(writeup_concurrency(), len(items)))
    if workers == 1:
        results = [(item, _one(item, ask)) for item in items]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(
                zip(items, pool.map(lambda it: _one(it, ask), items), strict=True)
            )
    for item, parsed in results:
        if parsed is not None:
            out[str(item.id)] = parsed
    return out


def writeup_concurrency() -> int:
    """How many write-up / précis calls may be in flight for one target."""
    from django.conf import settings

    return max(1, int(getattr(settings, "WRITEUP_LLM_CONCURRENCY", 12)))


def store_comprehensions(
    items: Sequence[ContentItem], parsed: Mapping[str, dict]
) -> dict[str, ItemComprehension]:
    """Persist the extracted fields and return the stored rows, keyed by id."""
    by_id = {str(item.id): item for item in items}
    out: dict[str, ItemComprehension] = {}
    for cid, fields in parsed.items():
        item = by_id.get(cid)
        if item is None:
            continue
        row, _created = ItemComprehension.objects.update_or_create(
            content=item,
            defaults={
                **fields,
                "prompt_version": PROMPT_VERSION,
                "source_fingerprint": source_fingerprint(item),
            },
        )
        out[cid] = row
    return out


def comprehend(
    items: Sequence[ContentItem],
    *,
    complete: CompleteFn | None = None,
    limit: int | None = None,
) -> dict[str, ItemComprehension]:
    """Return a current précis for every item in ``items``, computing what is missing.

    The all-in-one convenience wrapper — read, extract, store — for callers that
    are already on a database thread. Serves from store first, so only items with
    no current row cost a call; ``limit`` caps how many of those a single run pays
    for, and the rest keep their place and are read next time.
    """
    cached = load_comprehensions(items)
    missing = [item for item in items if str(item.id) not in cached]
    if limit is not None:
        missing = missing[: max(0, limit)]
    if not missing:
        return cached
    cached.update(
        store_comprehensions(missing, extract_many(missing, complete=complete))
    )
    return cached


def _one(item: ContentItem, ask: CompleteFn) -> dict | None:
    try:
        raw = ask(build_prompt(item))
    except Exception as exc:  # noqa: BLE001 — any model failure degrades, never raises
        logger.warning("comprehension unavailable for %s (%s)", item.id, exc)
        return None
    return parse(raw)


# -- prompt ------------------------------------------------------------------


def build_prompt(item: ContentItem) -> str:
    """The item as the reader sees it — the **full** abstract, never truncated.

    Truncating here is exactly the input starvation this stage exists to remove,
    and it costs nothing to avoid: the call happens once per item for the whole
    user base.
    """
    meta = item.metadata or {}
    title = _clean(meta.get("title") or meta.get("name")) or "(untitled)"
    body = _clean(
        meta.get("abstract") or meta.get("summary") or meta.get("description")
    )
    lines = [f"Title: {title}"]
    venue = _clean(meta.get("venue"))
    if venue:
        lines.append(f"Venue: {venue}")
    year = meta.get("year")
    if year:
        lines.append(f"Year: {year}")
    authors = meta.get("authors")
    if isinstance(authors, list) and authors:
        lines.append(f"Authors: {', '.join(_clean(a) for a in authors[:12] if a)}")
    lines.append("")
    lines.append(f"Text:\n{body or '(no abstract available)'}")
    return "\n".join(lines)


# -- parsing -----------------------------------------------------------------


def parse(raw: str | None) -> dict | None:
    """The model's JSON as storable fields, or ``None`` when it is unusable."""
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # A JSON object that names none of the précis fields is not a thin précis —
    # it is a different answer altogether (a mis-routed prompt, a wrapper the
    # model invented). Storing it as an empty row would mask the failure and then
    # be served forever as though the item had been read.
    if not any(key in data for key in _FIELDS):
        return None
    out: dict[str, Any] = {key: _clean(data.get(key)) for key in _FIELDS}
    out["thin"] = bool(data.get("thin")) or not any(
        out[key] for key in ("problem", "method", "claim", "reusable")
    )
    return out


def fallback_block(item: ContentItem) -> str:
    """What the fit stage reads when no précis exists — the raw text, honestly.

    Not a fabricated précis. A missing extraction should look missing to the
    stage downstream, which then reasons over the abstract as it always did,
    rather than reasoning over an invented structure.
    """
    meta = item.metadata or {}
    body = _clean(
        meta.get("abstract") or meta.get("summary") or meta.get("description")
    )
    return f"    Abstract (no précis available): {body}" if body else ""


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value else ""


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="comprehension")
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    return response.content
