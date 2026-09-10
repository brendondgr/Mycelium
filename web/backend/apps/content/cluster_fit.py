"""Stage two of the model pipeline: one theme, one reader, one call.

Prompt B. A research scout writes for one named researcher about one named
strand of their work. It reads the précis from :mod:`.comprehension` plus a
**retrieval evidence packet** — which of this theme's interests matched, in
strength order; which literal terms appear in the text; whether the item also
sits in another theme's slate; whether it is new to this one; and where it sits
today. Without that packet the model is guessing why the system surfaced
something, which is precisely why the reasons it used to write were generic.

What comes back per candidate:

1. a **verdict** — read / skim / file / skip (:mod:`.verdicts`);
2. a **reason in three explicit beats**, in order — why this matters to *this
   theme*, naming the specific interest it connects to; how they could use it, as
   a concrete action; and what to take from it, as a specific finding, technique,
   table, or dataset. The beats are structural, not a request: "explain in depth"
   without structure produces longer generic text, not deeper text;
3. a **caveat** — the strongest reason this might not be worth their time.
   Mandatory, and a missing one triggers the fallback for that item rather than
   persisting a blank field. It is what makes the document read as judgement
   rather than promotion;
4. a **bridge note**, only where the item already sits in another theme's slate.

Two constraints worth naming because they are load-bearing rather than
decorative. The model is told **not to reorder** — ordering is retrieval's job,
and saying so removes the incentive to hedge toward a ranking, which in turn
makes input position effects harmless because the model's ordering is never
read. And candidates are **shuffled with a recorded seed** at prompt-build time:
free, reproducible, and the only cheap defence against position bias.

Storage and reuse (plan §19)
----------------------------

A write-up is keyed on **(item, cluster, target)** and lives at
``signals["writeups"][cluster_id]``. Keying it on the item alone would serve one
theme's reasoning under both headings for a bridge item; keying the *précis* on
the pair would evaporate the saving that stage exists for. Both keys matter and
they are different.

What does **not** trigger a re-run: a moved position, a re-entry into the slate
(badged new again — but "new to the reader's attention" is not "new to Mylo"), a
new run, or the item newly bridging into a second theme. What does, and nothing
else: the cluster's areas changed, the cluster is gone (a delete, handled by
:func:`apps.content.slates.prune_cluster_slates`), the rubric version moved, or
the item's source text changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone

from .clustering import Cluster
from .comprehension import fallback_block
from .models import ContentItem, ItemComprehension
from .verdicts import VERDICTS, derive_verdict, parse_verdict

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]

#: Stamped on every stored write-up. **Bump this whenever the prompt or the
#: output contract below changes.** A rubric edit without a bump is the one
#: failure this stamp cannot catch, so there is a test that catches it instead.
RUBRIC_VERSION = "b1"

#: Stamped alongside the rubric on **deterministic** write-ups only, and bumped
#: whenever their templated wording changes. It exists so template copy can be
#: fixed without bumping :data:`RUBRIC_VERSION`, which would invalidate the
#: model-written ones too and re-bill the whole corpus for an edit no model was
#: involved in. Rebuilding a deterministic write-up costs nothing, so this can
#: move as often as the wording needs it to.
TEMPLATE_VERSION = "t2"

#: Run-safety cap on write-ups per target per run — **not** a spend cap. The
#: nightly batch is shared: a reader who just redirected their whole research
#: profile has every item in every theme as an entrant, and an unbounded spike
#: for them can exhaust the run window or trip a provider rate limit and degrade
#: *everyone else's* report. So write-ups are ordered priority-first and whatever
#: does not fit carries to the next run rather than being dropped. A heavy reader
#: gets everything, occasionally across two mornings, never at another reader's
#: expense. It is enforced across all themes jointly and is independent of slate
#: depth — otherwise slate depth becomes a cost dial by accident.
DEFAULT_WRITEUP_BUDGET = 40

#: Candidates per call. One call per theme is the design; this only splits a
#: theme whose entrant list is long enough that a single answer would be
#: truncated before the last item.
DEFAULT_BATCH = 12

_SYSTEM_PROMPT = (
    "You are Mylo, a research scout writing for one named researcher about ONE "
    "named strand of their work. You are given that strand's interests, a "
    "structured précis of each candidate, and the retrieval evidence that "
    "surfaced it.\n"
    "Return ONLY one JSON object:\n"
    '  {"items": [{"n": <candidate number>, "verdict": "read"|"skim"|"file"'
    '|"skip", "matters": <one sentence: why this matters to THIS strand, '
    "naming the specific interest it connects to — not the strand in "
    'general>, "use": <one sentence: a concrete action they could take — '
    "adopt the method, use it as a baseline, check a result against it, "
    'contact the authors>, "take": <one sentence: the specific finding, '
    'technique, table, or dataset to take from it>, "caveat": <the strongest '
    'reason this might NOT be worth their time>, "bridge": <one clause on '
    "what the two strands share here, ONLY when the evidence says the item is "
    'also in another strand\'s slate; otherwise "">}]}\n'
    "Rules:\n"
    "- Ground everything in the précis and the evidence. If a claim is not in "
    "the source, do not make it.\n"
    "- DO NOT reorder the list and do not rank. Ordering is decided before you "
    "see the candidates and your order is never read.\n"
    "- The caveat is mandatory. Never write an empty caveat and never write "
    '"none".\n'
    "- Use the full range of verdicts. Do not drift to the middle.\n"
    "- Never rename an item. Judge only the candidates given, by their number.\n"
    "- No cross-strand comparison, no percentages, no encouragement, no prose "
    "outside the JSON, no markdown fences."
)


# --------------------------------------------------------------------------- #
# The stored artefact
# --------------------------------------------------------------------------- #


@dataclass
class Evidence:
    """Why retrieval surfaced one candidate for one theme.

    The part that was entirely missing from the old prompt. Everything here is
    already known at prompt-build time; none of it costs a query.
    """

    #: This theme's interests that matched, strongest first.
    matched_interests: list[str] = field(default_factory=list)
    #: Interest terms that appear literally in the item's own text.
    literal_terms: list[str] = field(default_factory=list)
    #: Labels of other themes whose slate this item also sits in.
    also_in: list[str] = field(default_factory=list)
    #: Whether it entered *this* theme's slate on this run.
    is_new: bool = False
    #: Its position in this theme today.
    position: int = 0

    def as_lines(self) -> list[str]:
        out: list[str] = []
        if self.matched_interests:
            out.append(
                f"matched interests (strongest first): "
                f"{', '.join(self.matched_interests)}"
            )
        if self.literal_terms:
            out.append(f"literal terms in the text: {', '.join(self.literal_terms)}")
        if self.also_in:
            out.append(f"also in your {', '.join(self.also_in)} slate")
        out.append(
            f"position {self.position} in this strand today"
            + (" — new to it" if self.is_new else "")
        )
        return out


def areas_fingerprint(areas: Sequence[str]) -> str:
    """A digest of a cluster's interests — what a stored write-up was judged against.

    Order-insensitive and case-folded, so re-saving a profile without changing
    anything does not invalidate a good write-up, while genuinely editing the
    strand's interests does. Relabelling a cluster changes nothing here, which is
    correct: a rename changes its name everywhere and changes nothing else.
    """
    payload = "␟".join(sorted(" ".join(a.split()).casefold() for a in areas if a))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stored_writeup(signals: Mapping | None, cluster_id: str) -> dict | None:
    """The stored write-up for one theme on one row, if there is one."""
    writeups = (signals or {}).get("writeups")
    if not isinstance(writeups, dict):
        return None
    entry = writeups.get(cluster_id)
    return entry if isinstance(entry, dict) else None


def is_current(writeup: Mapping | None, fingerprint: str) -> bool:
    """Whether a stored write-up still answers the question it was asked.

    Four invalidations and only four (plan §19): the areas changed, the cluster
    is gone (handled by pruning), the rubric moved, or the item's text changed —
    the last cascading in through the précis, which is re-read when it does.

    Deterministic write-ups carry a fifth, and it is free: their wording is a
    template rather than a model's answer, so a copy fix re-renders them on the
    next run instead of waiting for one of the four to fire. Model write-ups are
    deliberately not subject to it — invalidating those means paying for them
    again, which no wording change justifies.
    """
    if not writeup:
        return False
    if writeup.get("source") == "deterministic" and (
        writeup.get("template_version") != TEMPLATE_VERSION
    ):
        return False
    return (
        writeup.get("rubric_version") == RUBRIC_VERSION
        and writeup.get("areas_fingerprint") == fingerprint
        and bool(writeup.get("caveat"))
        and writeup.get("verdict") in VERDICTS
    )


def make_writeup(
    *,
    verdict: str,
    beats: Sequence[str],
    caveat: str,
    bridge_note: str,
    fingerprint: str,
    source: str,
) -> dict:
    """One stored write-up, in the shape every renderer reads."""
    return {
        "verdict": verdict,
        "beats": [b for b in beats if b],
        "caveat": caveat,
        "bridge_note": bridge_note,
        "source": source,
        "rubric_version": RUBRIC_VERSION,
        "areas_fingerprint": fingerprint,
        "written_on": timezone.now().date().isoformat(),
        # Only meaningful on the deterministic path; harmless on the other.
        **({"template_version": TEMPLATE_VERSION} if source == "deterministic" else {}),
    }


def lead_sentence(writeup: Mapping | None) -> str:
    """The reason's **first beat** — the one line the PDF prints.

    The single most load-bearing sentence in the document: without it a reader
    gets sixty titles and must open the site to make any judgement at all, which
    defeats a morning brief. The remaining beats and the caveat go to the web
    entry, where the reader has already decided the item deserves attention.
    """
    beats = (writeup or {}).get("beats") or []
    return beats[0] if beats else ""


def full_reason(writeup: Mapping | None) -> str:
    """All three beats as one paragraph — the web entry's reasoning."""
    return " ".join((writeup or {}).get("beats") or [])


# --------------------------------------------------------------------------- #
# The deterministic path — the baseline product, not a fallback
# --------------------------------------------------------------------------- #


def deterministic_writeup(
    item: ContentItem,
    cluster: Cluster,
    evidence: Evidence,
    *,
    depth: int,
    fingerprint: str,
) -> dict:
    """A complete write-up with no model involved.

    This is what most readers get, and it must read as a finished thing rather
    than as a paid document with the good parts missing. The verdict comes from
    the rank band, the lead sentence is templated from the interests that
    actually matched, and the caveat is honest about what has *not* been
    established rather than inventing a criticism.
    """
    interest = evidence.matched_interests[0] if evidence.matched_interests else ""
    # The implicit cluster is the fallback grouping a profile with no declared
    # themes falls into, not a theme with a name — writing "your All interests
    # work" would name a thing the reader never created.
    strand = "" if cluster.is_implicit else cluster.label
    where = f"in your {strand} work" if strand else "in your feed"
    # No position in the sentence. It used to open "Ranked 4th in your …", which
    # was the only place a per-theme rank survived once the cards stopped showing
    # one — and a rank quoted in prose, with nothing beside it to say which list
    # it counts, is exactly the number that read as a sorting fault.
    if interest:
        matters = (
            f"Matches {where.removeprefix('in ')} through its overlap "
            f"with {interest}."
        )
    elif strand:
        matters = f"Matches your {strand} interests."
    else:
        matters = "Matches your research interests."
    caveat = (
        "Mylo has not read this one for you — the placement is a topical match, "
        "not a judgement of the work itself."
    )
    bridge = (
        f"Also in your {evidence.also_in[0]} slate." if evidence.also_in else ""
    )
    return make_writeup(
        verdict=derive_verdict(evidence.position, depth=depth),
        beats=[matters],
        caveat=caveat,
        bridge_note=bridge,
        fingerprint=fingerprint,
        source="deterministic",
    )


# --------------------------------------------------------------------------- #
# The model path
# --------------------------------------------------------------------------- #


@dataclass
class Candidate:
    """One item queued for a write-up, with everything the prompt needs."""

    item: ContentItem
    evidence: Evidence
    precis: ItemComprehension | None = None


def write_cluster_fits(
    profile_text: str,
    cluster: Cluster,
    other_cluster_labels: Sequence[str],
    candidates: Sequence[Candidate],
    *,
    depth: int,
    complete: CompleteFn | None = None,
    seed: int = 0,
    batch: int | None = None,
) -> dict[str, dict]:
    """Write-ups for one theme's candidates, keyed by content id.

    Never raises. Any candidate the model does not cover — because it was
    unreachable, unparseable, or answered without the mandatory caveat — falls
    back to :func:`deterministic_writeup` for that item alone, so a partial
    answer is still a complete section.
    """
    if not candidates:
        return {}
    fingerprint = areas_fingerprint(cluster.areas)
    out: dict[str, dict] = {}
    size = int(batch or getattr(settings, "CLUSTER_FIT_BATCH", DEFAULT_BATCH))
    ask = complete if complete is not None else _settings_complete

    for start in range(0, len(candidates), max(1, size)):
        chunk = list(candidates[start : start + max(1, size)])
        order = _shuffled(chunk, seed=seed + start)
        prompt = build_prompt(
            profile_text, cluster, other_cluster_labels, order, seed=seed + start
        )
        try:
            raw = ask(prompt)
        except Exception as exc:  # noqa: BLE001 — degrade, never raise
            logger.warning(
                "cluster-fit writer unavailable for %s (%s); using the "
                "deterministic write-up.",
                cluster.id,
                exc,
            )
            raw = None
        out.update(parse(raw, order, fingerprint=fingerprint))

    for candidate in candidates:
        cid = str(candidate.item.id)
        if cid not in out:
            out[cid] = deterministic_writeup(
                candidate.item,
                cluster,
                candidate.evidence,
                depth=depth,
                fingerprint=fingerprint,
            )
    return out


def _shuffled(candidates: Sequence[Candidate], *, seed: int) -> list[Candidate]:
    """Candidate order for the prompt, shuffled reproducibly.

    Seeded so a run can be replayed exactly. The model is told its ordering is
    never read, so shuffling costs nothing and removes the last way input
    position could leak into the output.
    """
    shuffled = list(candidates)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def build_prompt(
    profile_text: str,
    cluster: Cluster,
    other_cluster_labels: Sequence[str],
    candidates: Sequence[Candidate],
    *,
    seed: int = 0,
) -> str:
    """The per-theme prompt: the reader, this strand, and the evidence packet."""
    parts = [
        f"Researcher:\n{profile_text or '(no profile details)'}",
        "",
        f"The strand you are judging for: {cluster.label}",
        f"Its interests: {', '.join(cluster.areas) or '(none declared)'}",
    ]
    if other_cluster_labels:
        parts.append(
            "Their other strands (OUT OF SCOPE for this judgement — present only "
            "so you can name a bridge, never so you can grade fit to them): "
            + ", ".join(other_cluster_labels)
        )
    parts.append("")
    parts.append(f"Candidates (order is arbitrary; shuffle seed {seed}):")
    for index, candidate in enumerate(candidates, start=1):
        meta = candidate.item.metadata or {}
        title = _clean(meta.get("title") or meta.get("name")) or "(untitled)"
        parts.append(f"[{index}] {title}")
        block = (
            candidate.precis.as_prompt_block()
            if candidate.precis is not None and not candidate.precis.is_empty
            else fallback_block(candidate.item)
        )
        if block:
            parts.append(block)
        for line in candidate.evidence.as_lines():
            parts.append(f"    evidence: {line}")
    parts.append("")
    parts.append("Judge every candidate. Do not reorder them.")
    return "\n".join(parts)


def parse(
    raw: str | None, candidates: Sequence[Candidate], *, fingerprint: str
) -> dict[str, dict]:
    """Model output as stored write-ups, keyed by content id.

    Everything is validated at this boundary: an unknown verdict is rejected
    rather than persisted as a novel label, and a missing or empty caveat drops
    that item so the caller falls back for it — a blank caveat field would read
    as "nothing to warn you about", which is not what happened.
    """
    if not raw:
        return {}
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    rows = data.get("items") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}

    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = _as_index(row.get("n"), len(candidates))
        if index is None:
            continue
        candidate = candidates[index]
        verdict = parse_verdict(row.get("verdict"))
        caveat = _clean(row.get("caveat"))
        beats = [
            _clean(row.get("matters")),
            _clean(row.get("use")),
            _clean(row.get("take")),
        ]
        if verdict is None or not caveat or caveat.casefold() in {"none", "n/a"}:
            continue
        if not beats[0]:
            continue
        bridge = _clean(row.get("bridge")) if candidate.evidence.also_in else ""
        out[str(candidate.item.id)] = make_writeup(
            verdict=verdict,
            beats=beats,
            caveat=caveat,
            bridge_note=bridge,
            fingerprint=fingerprint,
            source="llm",
        )
    return out


def _as_index(value: Any, count: int) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n - 1 if 1 <= n <= count else None


def writeup_budget() -> int:
    """How many write-ups one target's run may pay for — see the module docstring."""
    return int(getattr(settings, "CLUSTER_WRITEUP_BUDGET", DEFAULT_WRITEUP_BUDGET))


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value else ""


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="cluster_fit")
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    if response.finish_reason == "length" and not (response.content or "").strip():
        logger.warning(
            "cluster-fit response truncated before any answer; raise "
            "LLM_MAX_TOKENS or lower CLUSTER_FIT_BATCH."
        )
    return response.content
