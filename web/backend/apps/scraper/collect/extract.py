"""Phase 8 — universal LLM structured extraction, verified in a bounded loop.

Plan decision D9: every collected record's description is produced by a model
under a schema-checked contract, verified deterministically, and the VERIFIED
text — never the raw source — is what gets embedded (D10). This is universal:
grants and conferences, not just records missing text, because the raw source
is not a uniform embedding basis (an NSF description averages 11,411 chars, a
conference's ``cfp_text`` is empty on all 2,234 collector rows).

**This module ports a measured design; it does not invent one.** The schema,
prompts, deterministic validators, the source-length-aware grounding rule and
the bounded repair loop are exactly what
``docs/research/experiments/EXP-2026-08-007-extraction-grounding-floor/code/
run.py`` benchmarked at 1.798 verified records/second and 3.1% refusal, 16
workers, reasoning off. Two pieces are reused rather than re-derived, per the
plan: :func:`~apps.scraper.collect.conferences.enrich.overlap_ratio` for the
prose-grounding ratio itself, and
:func:`~apps.scraper.collect.conferences.enrich.venue_matches` for the
conference identity check — both already do exactly this job and are exercised
by that module's own test suite.

Word-counting for the *grounding regime* (rich vs. stub — see
``MIN_SOURCE_WORDS_FOR_OVERLAP`` below) stays the definition EXP-2026-08-007
measured the 80-word threshold against, not ``enrich``'s conference-tuned one
(which drops domain words like "research" and "international" that would be
meaningful in a *grant*'s source text). The two word-counters therefore
deliberately differ; see :func:`_words` vs. ``enrich.overlap_ratio``'s own.

**Two defects the recon proved on live data, and where their fix actually
lives.** The plan names two bugs to fix "on port": ``apply_enrichment``
collapsing verified deadlines by ``(kind, round_label)`` when the model always
returns ``""`` for the label, and a stored ``page_hash`` that is never
compared. Both functions live in
``apps.scraper.collect.conferences.enrich``, a file this task's assignment
does not authorise editing (only ``extract.py`` and its test file), and this
module's own schema (below) carries no deadline field at all — Phase 8 never
calls ``apply_enrichment``, so that defect is not reachable from here and
remains a discrepancy to flag, not something silently worked around. The
*second* defect — page_hash stored and never compared — genuinely is fixed
here: every :class:`Checkpoint` record carries the content hash of the source
it was extracted from, and :func:`run_extraction` only ever treats a settled
verdict as a cache hit when the freshly-resolved source hashes the same (see
``_cached_outcome``). A page that moves after a prior ``ok`` gets re-read.

Runtime order is ``ingest -> extract -> embed`` (D10): this stage runs after
collector records have been mapped and upserted into ``ContentItem`` rows, and
its output — ``metadata["search_text"]`` — is what the embed step consumes.
Nothing here touches the database or the ``ContentItem`` model directly; the
public surface is a pure ``ExtractionInput -> ExtractionOutcome`` pipeline plus
:func:`apply_to_metadata`, so the caller that owns the model decides how and
when to persist it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

#: The name every extraction call is billed against in the daily LLM ledger
#: (``apps.core.llm_usage`` / ``core.LLMUsageDaily``). Plan §8, item 7.
COMPONENT = "opportunity_extraction"

#: Measured, not assumed (EXP-2026-08-007): no plateau at 12 workers, and the
#: collector's own published table describes a different endpoint entirely.
DEFAULT_WORKERS = 16

#: A record may never spin. Mean attempts per verified record measured at
#: 1.16-1.23, so this is a backstop, not a budget.
EXTRACTION_MAX_ATTEMPTS = 3

#: How much source text a prompt carries. Matches the reference harness and
#: ``enrich.MAX_PAGE_CHARS`` — the same figure, arrived at independently for
#: the same reason: enough for a full announcement or call for papers, bounded
#: so a wiki-sized page cannot blow the context window.
MAX_SOURCE_CHARS = 12_000

#: The fallback text a refused or short-circuited record embeds instead, so it
#: stays retrievable without ever looking like a checked summary. Kept
#: deliberately short — the whole premise of D9 is that a full raw dump is not
#: a comparable embedding basis, and that does not stop being true just
#: because this particular record was refused.
RAW_FALLBACK_CHARS = 1_500


# --------------------------------------------------------------------------- #
# Status vocabulary (plan §8, item 9)
# --------------------------------------------------------------------------- #
#
# Retryable statuses are about *us or the moment*: an unreachable model, a dead
# host, a page with nothing on it. Settled statuses are answers about the
# record itself. The distinction is load-bearing — a run at too much
# concurrency once wrote 321 ``model_failed`` rows in one sitting, and treating
# those as settled would have excluded 321 records from ever being retried.

RETRYABLE_STATUSES = frozenset({"pending", "model_failed", "fetch_failed", "thin_page"})
SETTLED_STATUSES = frozenset(
    {"ok", "robots_denied", "not_the_venue", "refused", "no_url"}
)
STATUSES = tuple(sorted(RETRYABLE_STATUSES | SETTLED_STATUSES))


# --------------------------------------------------------------------------- #
# The structured-output contract (plan §8.2, ported unchanged from the harness)
# --------------------------------------------------------------------------- #

GRANT_KEYS = {
    "summary": str,
    "purpose": str,
    "audience": str,
    "research_areas": list,
    "eligibility": str,
    "award_summary": str,
    "confidence": str,
}

CONFERENCE_KEYS = {
    "summary": str,
    "purpose": str,
    "audience": str,
    "topics": list,
    "field": str,
    "confidence": str,
}

GRANT_PROMPT = """\
You are extracting a structured description of a funding opportunity.

Return ONLY a JSON object with exactly these keys:
  "summary"        2-3 sentences: what this funds and why it exists
  "purpose"        one sentence: the funder's stated goal
  "audience"       one sentence: who this is for
  "research_areas" array of 2-6 short topic strings
  "eligibility"    one paragraph, or "" if the source does not state it
  "award_summary"  plain-language money line, or ""
  "confidence"     "high", "medium" or "low"

Every claim must be supported by the source text below. Do not add a number,
a date or an amount that does not appear in it. If the source does not say
something, use "".

SOURCE:
{source}
"""

CONFERENCE_PROMPT = """\
You are extracting a structured description of an academic conference.

Return ONLY a JSON object with exactly these keys:
  "summary"    2-3 sentences: what this venue is about
  "purpose"    one sentence
  "audience"   one sentence
  "topics"     array of 2-6 short topic strings
  "field"      the discipline in plain words
  "confidence" "high", "medium" or "low"

Every claim must be supported by the source text below. Do not invent dates,
locations or statistics. If the source is thin, say so via
"confidence": "low" rather than filling gaps from general knowledge.

SOURCE:
{source}
"""


# --------------------------------------------------------------------------- #
# Deterministic validators — no model, no I/O (plan §8.3 step 3 / §8.5b)
# --------------------------------------------------------------------------- #

_WORD = re.compile(r"[a-z0-9]+")

#: Words too common to count as evidence a claim came from the source. Kept
#: separate from ``enrich``'s stopword list on purpose: that list drops
#: domain filler like "research" and "international", which is right for a
#: page about a conference and wrong for a grant, whose whole text is often
#: exactly that vocabulary.
_STOP = frozenset(
    "the a an and or of for to in on at by with from is are be this that it as "
    "we our their its will can may all any more most other than which who".split()
)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


#: Below this many distinct content words, an overlap ratio is not a
#: meaningful test of grounding. Measured on the live stores
#: (EXP-2026-08-007): a conference record carries a median of 9 distinct
#: content words (``cfp_text`` is empty on all 2,234 rows; the source is
#: title + acronym + series + area codes), a grant a median of 484. A 2-3
#: sentence summary has roughly 35 content words, so the *ceiling* on overlap
#: against a 9-word source is 9/35 = 0.26 — below the 0.45 floor by
#: construction, for any summary at all, honest or not. That refused every
#: conference and was misread as a model failure until this fix.
MIN_SOURCE_WORDS_FOR_OVERLAP = 80

#: Reused from ``enrich``: the same floor that guards summaries of full
#: fetched web pages there guards a rich source here. Same number,
#: deliberately, because the property being tested is the same.
PROSE_FLOOR = 0.45

#: What a stub source is checked for instead of overlap: invented specifics.
#: Money, four-digit years, ordinals and bare integers. A model summarising
#: nine words cannot be asked to reuse them, but it can be held to inventing
#: nothing.
_SPECIFIC = re.compile(
    r"\$[\d,]+(?:\.\d+)?|\b\d{4}\b|\b\d+(?:st|nd|rd|th)\b|\b\d[\d,]*\b"
)


def _specifics(text: str) -> set[str]:
    """Numeric/date/money tokens, normalised so ``1,000`` and ``1000`` match."""
    return {
        m.group(0).replace(",", "").lstrip("$").rstrip(".")
        for m in _SPECIFIC.finditer(text)
    }


def grounding_failures(prose: str, source: str) -> list[str]:
    """Check prose against the source, scaled to how much source there is.

    Two regimes, because one test cannot serve both. A rich source (a grant
    description, a fetched conference page) can carry a word-overlap floor —
    computed by ``enrich.overlap_ratio``, reused rather than reimplemented,
    since it already does exactly this job. A stub source cannot carry that
    floor at all (see ``MIN_SOURCE_WORDS_FOR_OVERLAP``), so it is held to a
    stricter, narrower promise instead: invent no specifics.
    """
    from apps.scraper.collect.conferences.enrich import overlap_ratio

    source_words = _words(source)
    if len(source_words) >= MIN_SOURCE_WORDS_FOR_OVERLAP:
        ratio = overlap_ratio(prose, source)
        if ratio < PROSE_FLOOR:
            return [
                f"ungrounded_prose: summary+purpose+audience overlap the "
                f"source at {ratio:.2f}, floor is {PROSE_FLOOR} (source has "
                f"{len(source_words)} content words)"
            ]
        return []

    invented = _specifics(prose) - _specifics(source)
    if invented:
        return [
            f"unsupported_claim: {sorted(invented)} appear in the summary "
            f"but not in the source (source has only {len(source_words)} "
            "content words, so overlap is not tested -- invention is)"
        ]
    return []


def _venue_ok(source: str, *, acronym: str, title: str) -> bool:
    """Conference identity check: does the source identify this conference?

    Delegates entirely to ``enrich.venue_matches``, which already implements
    exactly this rule (an acronym on the page, else half the title's long
    words) and is exercised by its own test suite. The task object it wants
    is built here purely to carry the two fields it reads.
    """
    from apps.scraper.collect.conferences.enrich import EnrichmentTask, venue_matches

    task = EnrichmentTask(
        instance_key="", url="", acronym=acronym, title=title, year_label="", gaps=()
    )
    return venue_matches(task, source)


def validate(
    payload: object,
    source: str,
    kind: str,
    *,
    acronym: str = "",
    title: str = "",
    page_text: str = "",
) -> list[str]:
    """Return every failure reason. An empty list means the reply is verified.

    Order follows plan §8.3 step 3: schema -> bounds -> identity (conferences
    only) -> prose grounding -> topic grounding, where the no-invention check
    is the stub regime of prose/topic grounding rather than a separate step
    (see :func:`grounding_failures`).

    ``page_text`` is deliberately a *separate* parameter from ``source``: the
    prompt/grounding "source" always includes the identity header
    (``_conference_source_text`` prepends "Conference: ... Acronym: ...", by
    design -- it is what run.py's own measured stub regime checks against).
    Checking identity against that same header would be circular, since the
    header always contains the very acronym it is being asked to verify. The
    identity check therefore looks at ``page_text`` -- the raw ``cfp_text`` or
    fetched page, unaugmented -- falling back to ``source`` only so a caller
    testing :func:`validate` in isolation is not forced to supply both.
    """
    schema = GRANT_KEYS if kind == "grant" else CONFERENCE_KEYS
    fails: list[str] = []

    if not isinstance(payload, dict):
        return ["malformed: reply is not a JSON object"]

    for key, typ in schema.items():
        if key not in payload:
            fails.append(f"malformed: missing key {key!r}")
        elif not isinstance(payload[key], typ):
            fails.append(
                f"malformed: {key!r} should be {typ.__name__}, "
                f"got {type(payload[key]).__name__}"
            )
    if fails:
        return fails

    if payload["confidence"] not in {"high", "medium", "low"}:
        fails.append(
            f"out_of_bounds: confidence {payload['confidence']!r} "
            "is not high/medium/low"
        )
    if not 40 <= len(payload["summary"]) <= 900:
        fails.append(
            f"out_of_bounds: summary is {len(payload['summary'])} chars, "
            "want 40-900"
        )

    listkey = "research_areas" if kind == "grant" else "topics"
    items = payload[listkey]
    if not 2 <= len(items) <= 6:
        fails.append(f"out_of_bounds: {listkey} has {len(items)} entries, want 2-6")
    if len({str(i).strip().lower() for i in items}) != len(items):
        fails.append(f"out_of_bounds: {listkey} contains duplicates")

    identity_source = page_text or source
    if kind == "conference" and not _venue_ok(
        identity_source, acronym=acronym, title=title
    ):
        fails.append(
            "not_the_venue: the source does not identify itself as this "
            "conference"
        )

    prose = " ".join(str(payload[k]) for k in ("summary", "purpose", "audience"))
    fails.extend(grounding_failures(prose, source))

    source_words = _words(source)
    if len(source_words) >= MIN_SOURCE_WORDS_FOR_OVERLAP:
        for item in items:
            if not (_words(str(item)) & source_words):
                fails.append(
                    f"ungrounded_topic: {str(item)!r} shares no word with "
                    "the source"
                )
    else:
        for item in items:
            invented = _specifics(str(item)) - _specifics(source)
            if invented:
                fails.append(
                    f"ungrounded_topic: {str(item)!r} states {sorted(invented)}, "
                    "which the source does not"
                )

    return fails


def parse_reply(text: str) -> object:
    """Take the first ``{...}`` block. Models wrap JSON in prose more often
    than not."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# What one record carries in, and what comes back out
# --------------------------------------------------------------------------- #


@dataclass
class ExtractionInput:
    """Everything one record needs for extraction, decoupled from the ORM.

    Duck-typed convenience constructors below build this from the collector's
    own ``Opportunity`` / ``ConferenceInstance`` records so a caller never has
    to hand-assemble these fields, but this module never imports those
    classes itself — only the attributes it actually reads.
    """

    key: str
    kind: str  # "grant" | "conference"

    #: Identity fields that must always be searchable (plan §8.4), whichever
    #: of them apply to this record's kind.
    title: str = ""
    acronym: str = ""
    funder: str = ""
    opportunity_number: str = ""
    year_label: str = ""

    # -- grants -------------------------------------------------------
    description: str = ""
    eligibility: str = ""
    categories: list[str] = field(default_factory=list)

    # -- conferences ----------------------------------------------------
    cfp_text: str = ""
    url: str = ""
    series_name: str = ""
    field_codes: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    @classmethod
    def from_opportunity(cls, op: Any, *, key: str | None = None) -> ExtractionInput:
        """Build from a ``collect.grants.record.Opportunity``-shaped object."""
        return cls(
            key=key or op.stable_key,
            kind="grant",
            title=op.title,
            funder=op.funder,
            opportunity_number=op.opportunity_number,
            description=op.description,
            eligibility=op.eligibility,
            categories=list(op.categories or []),
        )

    @classmethod
    def from_conference(
        cls, instance: Any, series: Any = None, *, key: str | None = None
    ) -> ExtractionInput:
        """Build from a ``ConferenceInstance`` plus its resolved series."""
        full_name = getattr(series, "full_name", "") if series else ""
        field_codes = getattr(series, "field_codes", []) if series else []
        return cls(
            key=key or instance.instance_key,
            kind="conference",
            title=instance.title,
            acronym=instance.acronym,
            year_label=instance.year_label,
            cfp_text=instance.cfp_text,
            url=instance.url,
            series_name=full_name or instance.title,
            field_codes=list(field_codes or []),
            topics=list(instance.topics or []),
        )


@dataclass
class ExtractionOutcome:
    """One record's extraction verdict: verified, refused, or not yet settled.

    Carries exactly what plan §8's "apply or refuse" step needs to fold onto
    a ``ContentItem``'s ``metadata`` (:func:`apply_to_metadata`) and exactly
    what a :class:`Checkpoint` needs to resume a killed run without re-billing
    the model for work already settled.
    """

    key: str
    status: str
    attempts: int = 0
    ai_summary: str = ""
    ai_fields: dict[str, Any] | None = None
    summary_source: str = ""
    search_text: str = ""
    search_text_source: str = "raw"
    refusal_reason: str = ""
    #: Content hash of the source this outcome was built from. Empty when the
    #: record was never reachable at all (e.g. ``no_url``).
    page_hash: str = ""


def scrub(value: Any) -> Any:
    """Strip NUL code points from anything on its way into ``metadata``.

    PostgreSQL ``jsonb`` cannot represent ``\\u0000`` -- it raises
    ``unsupported Unicode escape sequence`` and takes the whole batch down with
    it. That is not hypothetical: the venue crawl fetches arbitrary URLs, and a
    host that answers a page request with a binary body (a mis-served archive,
    a content-type lie) yields decoded text containing NULs, which then travel
    all the way from ``page_text`` into ``search_text`` before anything
    notices. One such page failed a 4,660-record write.

    Scrubbing here rather than at the fetch is deliberate: this is the single
    boundary every extraction verdict crosses on its way to the database, so
    one guard covers the collector, this module's own callers, and any future
    one. NUL carries no meaning in any of these fields, so removing it loses
    nothing a reader would want.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def apply_to_metadata(
    metadata: dict[str, Any], outcome: ExtractionOutcome
) -> dict[str, Any]:
    """Fold a verdict onto a ``ContentItem``'s ``metadata``, in place.

    Provenance never blurs (plan §8.7): a refused record carries no
    ``ai_summary`` / ``ai_fields`` at all, only the reason it was refused.
    Returns the same dict, mutated, so a caller can chain this into an
    ``item.metadata = apply_to_metadata(item.metadata, outcome)`` update.
    """
    metadata["search_text"] = scrub(outcome.search_text)
    metadata["search_text_source"] = outcome.search_text_source
    metadata["extraction_status"] = outcome.status
    metadata["extraction_attempts"] = outcome.attempts
    if outcome.page_hash:
        metadata["extraction_page_hash"] = outcome.page_hash

    if outcome.status == "ok":
        metadata["ai_summary"] = scrub(outcome.ai_summary)
        metadata["ai_fields"] = scrub(outcome.ai_fields)
        metadata["summary_source"] = outcome.summary_source
        metadata.pop("extraction_refusal", None)
    else:
        metadata.pop("ai_summary", None)
        metadata.pop("ai_fields", None)
        metadata.pop("summary_source", None)
        metadata["extraction_refusal"] = scrub(outcome.refusal_reason)
    return metadata


# --------------------------------------------------------------------------- #
# Checkpointing (plan §8, item 10) — an interrupted backfill resumes
# --------------------------------------------------------------------------- #


class Checkpoint(Protocol):
    """The two operations :func:`run_extraction` needs from a durable store."""

    def get(self, key: str) -> Mapping[str, Any] | None: ...

    def save(self, key: str, record: Mapping[str, Any]) -> None: ...


class DictCheckpoint:
    """In-memory checkpoint. The default, and what every test uses.

    A real backfill should pass :class:`JsonFileCheckpoint` or an
    equivalent durable store so a killed process resumes instead of
    re-billing the model for every already-settled record; this exists so
    the module works standalone and so a test needs nothing more than a
    plain dict to prove resumption works.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> Mapping[str, Any] | None:
        return self._store.get(key)

    def save(self, key: str, record: Mapping[str, Any]) -> None:
        self._store[key] = dict(record)


class JsonFileCheckpoint:
    """A JSON-lines file: one line per save, replayed on load.

    Append-only on purpose. A process killed mid-write leaves at worst one
    truncated trailing line, skipped on load, rather than a corrupted store —
    which is the property that makes "resume after an interrupted backfill"
    actually safe to rely on, without needing a database migration this
    module has no business introducing.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._state: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a truncated trailing line from a killed run
                self._state[record["key"]] = record

    def get(self, key: str) -> Mapping[str, Any] | None:
        return self._state.get(key)

    def save(self, key: str, record: Mapping[str, Any]) -> None:
        payload = {"key": key, **record}
        self._state[key] = payload
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Source text (plan §8.3 step 1)
# --------------------------------------------------------------------------- #


def _identity_text(rec: ExtractionInput) -> str:
    parts = [rec.title, rec.acronym, rec.funder, rec.opportunity_number, rec.year_label]
    return " ".join(p for p in parts if p)


def _grant_source_text(rec: ExtractionInput) -> str:
    return (
        f"Title: {rec.title}\nFunder: {rec.funder}\n"
        f"Categories: {', '.join(rec.categories)}\n\n"
        f"{rec.description}\n\nEligibility: {rec.eligibility}"
    )[:MAX_SOURCE_CHARS]


def _conference_source_text(rec: ExtractionInput, body: str) -> str:
    return (
        f"Conference: {rec.title}\nAcronym: {rec.acronym} {rec.year_label}\n"
        f"Series: {rec.series_name}\nCCF areas: {', '.join(rec.field_codes)}\n"
        f"Topics: {', '.join(rec.topics)}\n\n{body}"
    )[:MAX_SOURCE_CHARS]


def _raw_fallback_text(rec: ExtractionInput, source_text: str) -> str:
    """The truncated raw text a refused or unreachable record falls back to.

    Deliberately shorter than the prompt's own source budget: the entire
    premise of D9 is that a raw dump is not a comparable embedding basis, and
    that stays true for the fallback case too.
    """
    body = source_text or rec.description or rec.cfp_text
    return f"{_identity_text(rec)} {body}".strip()[:RAW_FALLBACK_CHARS]


@dataclass
class SourceResolution:
    """What resolving one record's source text produced."""

    text: str = ""
    #: The raw, un-augmented body (``cfp_text`` or a fetched page) for the
    #: identity check to read. Kept apart from ``text`` -- which carries our
    #: own identity header -- so identity can never trivially pass just
    #: because we asserted the acronym ourselves. See ``validate``'s
    #: docstring.
    identity_text: str = ""
    #: "" means proceed to extraction; anything else is a status to
    #: short-circuit on without ever calling the model.
    status: str = ""
    page_hash: str = ""
    detail: str = ""


def _resolve_source(
    rec: ExtractionInput, *, http_client: Any, robots_gate: Any, host_locks: Any
) -> SourceResolution:
    """Grants: description + eligibility, always available, never fetched.

    Conferences: ``cfp_text`` where present, else the venue website fetched
    through the robots-aware gate, one lock per host so sixteen workers can
    never become sixteen simultaneous hits on one site.
    """
    from apps.scraper.collect.conferences.enrich import describes_something, page_hash

    if rec.kind == "grant":
        text = _grant_source_text(rec)
        return SourceResolution(text=text, page_hash=page_hash(text))

    if describes_something(rec.cfp_text):
        text = _conference_source_text(rec, rec.cfp_text)
        return SourceResolution(
            text=text, identity_text=rec.cfp_text, page_hash=page_hash(text)
        )

    from apps.scraper.collect.conferences.enrich import EnrichmentTask, fetch_page

    task = EnrichmentTask(
        instance_key=rec.key,
        url=rec.url,
        acronym=rec.acronym,
        title=rec.title,
        year_label=rec.year_label,
        gaps=("description", "deadlines"),
    )
    if not task.is_fetchable:
        return SourceResolution(status="no_url", detail="no fetchable URL")
    if http_client is None or robots_gate is None:
        return SourceResolution(
            status="fetch_failed", detail="no fetch client configured"
        )

    lock = host_locks.for_url(rec.url) if host_locks is not None else nullcontext()
    with lock:
        fetched, page = fetch_page(http_client, robots_gate, task)
    if fetched.status != "fetched":
        return SourceResolution(status=fetched.status, detail=fetched.detail)
    text = _conference_source_text(rec, page)
    return SourceResolution(
        text=text, identity_text=page, page_hash=fetched.page_hash
    )


# --------------------------------------------------------------------------- #
# The bounded agent loop (plan §8.3 steps 2-5)
# --------------------------------------------------------------------------- #


def _repair_prompt(template: str, source_text: str, failures: list[str]) -> str:
    """Feed the model its SPECIFIC failed checks, never a generic retry."""
    return (
        f"{template.format(source=source_text)}\n\n"
        "Your previous reply was rejected for these reasons:\n"
        + "\n".join(f"- {f}" for f in failures)
        + "\n\nReturn a corrected JSON object addressing every one."
    )


def _verified_outcome(
    rec: ExtractionInput, payload: dict[str, Any], *, attempts: int, page_hash: str
) -> ExtractionOutcome:
    listkey = "research_areas" if rec.kind == "grant" else "topics"
    items = [str(i) for i in payload[listkey]]
    prose = " ".join(str(payload[k]) for k in ("summary", "purpose", "audience"))
    search_text = " ".join(
        part for part in (_identity_text(rec), prose, " ".join(items)) if part
    )
    return ExtractionOutcome(
        key=rec.key,
        status="ok",
        attempts=attempts,
        ai_summary=str(payload["summary"]),
        ai_fields=dict(payload),
        summary_source="extracted",
        search_text=search_text,
        search_text_source="extracted",
        refusal_reason="",
        page_hash=page_hash,
    )


def _short_circuit_outcome(
    rec: ExtractionInput, resolution: SourceResolution
) -> ExtractionOutcome:
    """No source text worth sending to a model — settled or retryable per
    the status vocabulary, never a fabricated verdict."""
    return ExtractionOutcome(
        key=rec.key,
        status=resolution.status,
        attempts=0,
        search_text=_raw_fallback_text(rec, ""),
        search_text_source="raw",
        refusal_reason=f"{resolution.status}: {resolution.detail}",
        page_hash=resolution.page_hash,
    )


def extract_one(
    llm_client: Any,
    rec: ExtractionInput,
    source_text: str,
    *,
    max_attempts: int = EXTRACTION_MAX_ATTEMPTS,
    page_hash: str = "",
    identity_text: str = "",
) -> ExtractionOutcome:
    """The bounded agent loop: extract -> validate -> repair -> apply | refuse.

    Never makes more than ``max_attempts`` calls. A transport failure
    (``model_failed``) and a validation failure both consume an attempt, but
    they resolve to different final statuses: if every attempt failed to
    produce a reply at all, the record is ``model_failed`` (retryable — we
    never learned anything about the content); if at least the last attempt
    was judged and rejected, it is ``refused`` (settled); if identity itself
    never passed, it is ``not_the_venue`` (settled, and distinct from a
    generic refusal so a caller can tell "wrong page" from "bad prose" without
    parsing the reason string).
    """
    template = GRANT_PROMPT if rec.kind == "grant" else CONFERENCE_PROMPT
    prompt = template.format(source=source_text)
    last_failures: list[str] = []
    last_model_failed = False

    for attempt in range(1, max_attempts + 1):
        try:
            answer = llm_client.complete(prompt, reasoning="none", temperature=0.0)
            reply = answer.content or ""
        # Broad on purpose: transport and API errors propagate straight from
        # the SDK, and every one of them is a retryable model_failed, counted
        # -- never fatal to the batch, never silently a settled answer. The
        # collector once wrote 321 model_failed rows in one over-concurrent
        # run; treating those as answers would have excluded 321 records from
        # ever being retried.
        except Exception as exc:  # noqa: BLE001
            last_failures = [f"model_failed: {type(exc).__name__}: {exc}"]
            last_model_failed = True
            prompt = _repair_prompt(template, source_text, last_failures)
            continue

        last_model_failed = False
        payload = parse_reply(reply)
        fails = (
            ["malformed: no JSON object in reply"]
            if payload is None
            else validate(
                payload,
                source_text,
                rec.kind,
                acronym=rec.acronym,
                title=rec.title,
                page_text=identity_text,
            )
        )
        if not fails:
            return _verified_outcome(
                rec, payload, attempts=attempt, page_hash=page_hash
            )

        last_failures = fails
        prompt = _repair_prompt(template, source_text, fails)

    if any(f.startswith("not_the_venue") for f in last_failures):
        status = "not_the_venue"
    elif last_model_failed:
        status = "model_failed"
    else:
        status = "refused"

    return ExtractionOutcome(
        key=rec.key,
        status=status,
        attempts=max_attempts,
        search_text=_raw_fallback_text(rec, source_text),
        search_text_source="raw",
        refusal_reason="; ".join(last_failures) or "exhausted with no reply",
        page_hash=page_hash,
    )


# --------------------------------------------------------------------------- #
# Orchestration: newness gate, checkpoint resume, bounded concurrency
# --------------------------------------------------------------------------- #


def _cached_outcome(
    rec: ExtractionInput, checkpoint: Checkpoint | None, current_hash: str
) -> ExtractionOutcome | None:
    """A settled verdict is a cache hit only while the source has not moved.

    This is the fix for the defect the recon proved on live data: the
    collector's own ``plan_enrichment`` treated any settled status as
    permanently cached and never looked at ``page_hash`` again, so a page
    that changed its deadline after a prior ``ok`` was never re-read. Here,
    a hash mismatch always forces re-extraction regardless of prior status.
    """
    if checkpoint is None:
        return None
    prior = checkpoint.get(rec.key)
    if prior is None or prior.get("status") in RETRYABLE_STATUSES:
        return None
    if prior.get("page_hash", "") != current_hash:
        return None
    return ExtractionOutcome(**prior)


def run_extraction(
    records: Iterable[ExtractionInput],
    *,
    llm_client: Any = None,
    http_client: Any = None,
    robots_gate: Any = None,
    host_locks: Any = None,
    cache_dir: Path | None = None,
    max_workers: int = DEFAULT_WORKERS,
    max_attempts: int = EXTRACTION_MAX_ATTEMPTS,
    checkpoint: Checkpoint | None = None,
    only_keys: set[str] | None = None,
) -> dict[str, ExtractionOutcome]:
    """Run the bounded extraction loop over a batch, in parallel.

    ``only_keys`` is the newness gate (plan §8, item 8): pass the set of keys
    the caller has determined are genuinely new -- a nightly run -- to extract
    only those; pass ``None`` to process every record given -- a full
    backfill. The collector's own ``plan_enrichment`` never wired this gate
    up (it filters on content gaps and never reads ``new_items``), so it is
    wired here instead, at the one call boundary both a backfill and a
    nightly share.

    Concurrency is a plain ``ThreadPoolExecutor``; the per-host lock lives
    inside :func:`_resolve_source` around the fetch call only, so parallel
    workers never serialise on the model call, just on hitting one host.

    ``cache_dir`` is the collector's shared HTTP cache (``<root>/cache``, the
    same directory both collector pipelines pass their own client). Passing it
    matters more here than anywhere else in the codebase: conference records
    without usable ``cfp_text`` are enriched by fetching the venue's own site,
    which for a full backfill is thousands of pages spread over ~1,500
    third-party hosts. Without a cache every interrupted or repeated run
    re-hits all of them -- rude to those hosts and slow for us. The checkpoint
    prevents re-*extraction*; only this prevents re-*fetching*.
    """
    if llm_client is None:
        from apps.core.llm import build_llm_client

        llm_client = build_llm_client(component=COMPONENT)
    if http_client is None or robots_gate is None:
        from apps.scraper.collect.core.http import PoliteClient, RobotsGate

        http_client = http_client or PoliteClient(cache_dir=cache_dir)
        robots_gate = robots_gate or RobotsGate(http_client)
    if host_locks is None:
        from apps.scraper.collect.runner import _HostLocks

        host_locks = _HostLocks()

    selected = [r for r in records if only_keys is None or r.key in only_keys]
    if not selected:
        return {}

    def _one(rec: ExtractionInput) -> tuple[str, ExtractionOutcome]:
        resolution = _resolve_source(
            rec, http_client=http_client, robots_gate=robots_gate, host_locks=host_locks
        )
        if not resolution.status:
            cached = _cached_outcome(rec, checkpoint, resolution.page_hash)
            if cached is not None:
                # Nothing changed since the prior settled verdict: no write,
                # no re-billing the model. This is the resumption item 10
                # asks for, whether "prior" means an earlier run or an
                # interrupted one restarting from the same checkpoint.
                return rec.key, cached
            outcome = extract_one(
                llm_client,
                rec,
                resolution.text,
                max_attempts=max_attempts,
                page_hash=resolution.page_hash,
                identity_text=resolution.identity_text,
            )
        else:
            outcome = _short_circuit_outcome(rec, resolution)
        if checkpoint is not None:
            checkpoint.save(rec.key, asdict(outcome))
        return rec.key, outcome

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        pairs = list(pool.map(_one, selected))
    return dict(pairs)
