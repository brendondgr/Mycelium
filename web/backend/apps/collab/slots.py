"""What a funding call needs, as requirement slots (plan CN-03).

A slot is one distinct thing a call asks a team to bring: a problem it wants
solved, a method it requires, the data or setting it wants worked in, or a
**role** — a kind of partner that is not expertise ("a border authority", "a
minority-serving institution"). Slots drive the search from structure rather
than prose (design §6: "Slots, not prose"); coverage marks which ones the
reader and their lab already have.

``required`` separates what the call says a team **must** include from what it
is merely about. Silence in the call means no required slot — never an unknown
one — which is the rule the team-gap matcher already keeps.

Read once per call text, with its own prompt version and fingerprint, apart
from the call's verified extraction (``metadata["ai_fields"]``): reading slots
must not rewrite the summaries or the text that is embedded for search. The
extractor follows the pattern the codebase trusts — a fixed schema, a grounding
check against the call's own text, one repair naming what failed, then refusal
per slot.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from django.conf import settings

from apps.content.embeddings import embed_texts
from apps.research.state_extract import grounding_failures

from .models import RequirementSlots, SlotFacet

logger = logging.getLogger(__name__)

COMPONENT = "requirement_slots"
#: Bump whenever the prompt changes; only rows read under an older one re-read.
PROMPT_VERSION = "s1"
MAX_ATTEMPTS = 2
MAX_SLOTS = 6
MAX_SLOT_WORDS = 10
MAX_SLOT_CHARS = 90
MAX_SOURCE_CHARS = 12_000
#: Below this many content words there is nothing to read slots out of.
MIN_SOURCE_WORDS = 20

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the and for with that this from are was were our its into than then they "
    "them their there which while will would can could has have had not but all "
    "any use used using new also may these those such been more most other some "
    "when of in on to a an by as at or is be it we".split()
)

SYSTEM = (
    "You read one funding call and report what it asks an applicant team to "
    "bring. You report only what the call says, in its own words where you can, "
    "and you return an empty list rather than guess. Reply with one JSON object "
    "and nothing else."
)

PROMPT = """Read the funding call below and list what it asks a team to bring.

Reply as {{"slots": [...], "thin": false}} where each slot is
  {{"facet": "problem" | "method" | "data" | "role",
    "text": a short phrase of at most {max_words} words, in the call's words,
    "required": true only if the call says a team MUST include it}}

  problem — a problem the call wants solved.
  method  — a technique, method, or kind of expertise it asks for.
  data    — data, a cohort, an instrument, or a setting it wants worked in.
  role    — a kind of partner or organisation it requires that is not
            expertise (e.g. "a local authority as a partner").

At most {max_slots} slots, most important first. What the call is merely about
is not required; what it says applicants must include is. Use [] if the call
names nothing a team could bring. Do not invent anything the call does not say.

CALL
----
{source}
"""

REPAIR = """Your previous answer had these problems:
{failures}

Answer again in the same shape. Drop anything the call does not support rather
than rewording it to pass."""

CompleteFn = Callable[[str, str], str | None]


def _text(value) -> str:
    if isinstance(value, list | tuple):
        value = ", ".join(str(item) for item in value if item)
    return " ".join(str(value or "").split())


def source_text(item) -> str:
    """The call as the model reads it: the same fields the verified extraction
    reads, from what the collector stored."""
    meta = item.metadata or {}
    return (
        f"Title: {_text(meta.get('title'))}\n"
        f"Funder: {_text(meta.get('funder'))}\n"
        f"Categories: {_text(meta.get('categories'))}\n\n"
        f"{_text(meta.get('description'))}\n\n"
        f"Eligibility: {_text(meta.get('eligibility'))}"
    )[:MAX_SOURCE_CHARS]


def source_fingerprint(item) -> str:
    return hashlib.sha256(source_text(item).encode("utf-8")).hexdigest()[:32]


def is_current(row: RequirementSlots | None, item) -> bool:
    return (
        row is not None
        and row.prompt_version == PROMPT_VERSION
        and row.source_fingerprint == source_fingerprint(item)
    )


def _content_words(text: str) -> set[str]:
    return {
        w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 2
    }


@dataclass
class SlotOutcome:
    slots: list[dict] = field(default_factory=list)
    thin: bool = False
    refused: list[str] = field(default_factory=list)
    attempts: int = 0


def _parse(raw: str | None) -> dict | None:
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def validate(payload: dict, source: str) -> tuple[SlotOutcome, list[str]]:
    outcome = SlotOutcome()
    failures: list[str] = []
    raw = payload.get("slots")
    if not isinstance(raw, list):
        return SlotOutcome(thin=True), ["slots is not a list"]
    seen: set[str] = set()
    source_words = _content_words(source)
    for entry in raw:
        if not isinstance(entry, dict):
            failures.append("a slot is not an object")
            continue
        facet = str(entry.get("facet") or "").strip().lower()
        text = " ".join(str(entry.get("text") or "").split())
        if facet not in SlotFacet.values:
            failures.append(f"unknown facet {facet!r} for {text[:40]!r}")
            continue
        if not text:
            continue
        if len(text.split()) > MAX_SLOT_WORDS or len(text) > MAX_SLOT_CHARS:
            failures.append(f"slot too long: {text[:60]!r}")
            continue
        if not (_content_words(text) & source_words):
            failures.append(f"slot not in the call: {text!r}")
            continue
        invented = grounding_failures(text, source)
        if invented:
            failures.append(invented[0])
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        outcome.slots.append(
            {"facet": facet, "text": text, "required": bool(entry.get("required"))}
        )
    if len(outcome.slots) > MAX_SLOTS:
        failures.append(f"more than {MAX_SLOTS} slots")
        outcome.slots = outcome.slots[:MAX_SLOTS]
    outcome.thin = bool(payload.get("thin")) and not outcome.slots
    return outcome, failures


def _settings_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component=COMPONENT)
    return client.complete(
        [LLMMessage("system", system), LLMMessage("user", user)]
    ).content


def extract(item, *, complete: CompleteFn | None = None) -> SlotOutcome | None:
    """One call into slots. ``None`` means the model was unreachable: try again
    on the next run. Never raises."""
    source = source_text(item)
    if len(_content_words(source)) < MIN_SOURCE_WORDS:
        return SlotOutcome(thin=True, refused=["too little text to read"])
    ask = complete if complete is not None else _settings_complete
    prompt = PROMPT.format(max_words=MAX_SLOT_WORDS, max_slots=MAX_SLOTS, source=source)
    best: SlotOutcome | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = ask(SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001 - unavailable, not broken
            logger.warning("requirement slots unavailable for %s (%s)", item.pk, exc)
            if best is None:
                return None
            break
        payload = _parse(raw)
        if payload is None:
            outcome, failures = SlotOutcome(thin=True), ["the reply was not JSON"]
        else:
            outcome, failures = validate(payload, source)
        outcome.attempts = attempt
        outcome.refused = failures
        best = outcome
        if not failures:
            break
        prompt = (
            PROMPT.format(max_words=MAX_SLOT_WORDS, max_slots=MAX_SLOTS, source=source)
            + "\n"
            + REPAIR.format(failures="\n".join(f"- {f}" for f in failures))
        )
    return best


def extract_many(items: Sequence, *, complete: CompleteFn | None = None) -> dict:
    """Pure with respect to the database; threaded like the précis stage."""
    if not items:
        return {}
    workers = max(1, min(int(settings.WRITEUP_LLM_CONCURRENCY), len(items)))
    if workers == 1:
        results = [(item, extract(item, complete=complete)) for item in items]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(
                zip(
                    items,
                    pool.map(lambda i: extract(i, complete=complete), items),
                    strict=True,
                )
            )
    return {item.pk: outcome for item, outcome in results if outcome is not None}


def _embed(slots: list[dict]) -> None:
    """A vector for every slot that can be matched (not a role)."""
    wanted = [s for s in slots if s["facet"] != SlotFacet.ROLE and not s.get("vector")]
    if not wanted:
        return
    vectors = embed_texts([s["text"] for s in wanted])
    if not vectors:
        return
    for slot, vector in zip(wanted, vectors, strict=True):
        slot["vector"] = [round(float(v), 6) for v in vector]


def store(item, outcome: SlotOutcome) -> RequirementSlots:
    _embed(outcome.slots)
    if outcome.thin:
        status = RequirementSlots.Status.THIN
    elif outcome.slots:
        status = RequirementSlots.Status.OK
    else:
        status = RequirementSlots.Status.NONE
    row, _ = RequirementSlots.objects.update_or_create(
        content=item,
        defaults={
            "slots": outcome.slots,
            "status": status,
            "refused": outcome.refused,
            "prompt_version": PROMPT_VERSION,
            "source_fingerprint": source_fingerprint(item),
        },
    )
    return row


def fill_vectors(rows: Iterable[RequirementSlots]) -> int:
    """Embed slots stored while the embedder was down."""
    filled = 0
    for row in rows:
        missing = [
            s for s in row.slots if s["facet"] != SlotFacet.ROLE and not s.get("vector")
        ]
        if not missing:
            continue
        _embed(row.slots)
        if all(s.get("vector") for s in missing):
            row.save(update_fields=["slots", "updated_at"])
            filled += len(missing)
    return filled


def pending(items: Iterable) -> list:
    items = list(items)
    rows = {
        row.content_id: row
        for row in RequirementSlots.objects.filter(content__in=[i.pk for i in items])
    }
    return [item for item in items if not is_current(rows.get(item.pk), item)]


@dataclass
class SlotsRun:
    read: int = 0
    with_slots: int = 0
    unavailable: int = 0
    vectors: int = 0

    def as_dict(self) -> dict:
        return {
            "read": self.read,
            "with_slots": self.with_slots,
            "unavailable": self.unavailable,
            "vectors": self.vectors,
        }


def read_calls(items: Iterable, *, limit: int | None = None, complete=None) -> SlotsRun:
    """Read the slots of every call in ``items`` that needs it, within ``limit``."""
    out = SlotsRun()
    todo = pending(items)
    if limit is not None:
        todo = todo[: max(0, limit)]
    outcomes = extract_many(todo, complete=complete)
    out.unavailable = len(todo) - len(outcomes)
    by_pk = {item.pk: item for item in todo}
    for pk, outcome in outcomes.items():
        row = store(by_pk[pk], outcome)
        out.read += 1
        out.with_slots += int(bool(row.slots))
    out.vectors = fill_vectors(
        RequirementSlots.objects.filter(status=RequirementSlots.Status.OK)
    )
    return out


def grants():
    """Every call a slot line could appear on: grants, newest first."""
    from apps.content.models import ContentItem

    return ContentItem.objects.filter(type="grant").order_by("-created_at", "pk")


def slots_for(content_ids: Iterable) -> dict[str, RequirementSlots]:
    """Stored slots for these calls, keyed by content id (current or not: a
    call whose text changed keeps showing its last reading until re-read)."""
    return {
        str(row.content_id): row
        for row in RequirementSlots.objects.filter(content_id__in=list(content_ids))
    }
