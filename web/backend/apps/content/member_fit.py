"""Who is this for? — Mylo's per-item member recommendations.

A lab feed answers "what should this lab look at". It does not answer the question
a PI actually asks next: *which of my people should look at it?* This module is
that second answer, and it is the one thing a lab surface has that a personal one
does not — the structure of the four lab feeds is otherwise identical to the
personal pages by design.

Two signals, in that order:

1. **Arithmetic.** The cosine between the item's vector and each member's own
   interest vector, reusing the same primitives the cross-member fan-out uses
   (:func:`apps.content.fanout.member_vector`). A member is a candidate above
   ``settings.MEMBER_FIT_COSINE_FLOOR``; at most ``MEMBER_FIT_MAX_MEMBERS`` are
   named per item so a card stays readable in a large lab. This always runs, needs
   no model, and is what the percent on the chip means.
2. **Mylo.** For the strongest ``MEMBER_FIT_LLM_LIMIT`` items of each area, the
   model reads the item and the candidates' research profiles and writes *why*
   each named member is the right person — the consultant's line. It may drop a
   candidate it judges a poor fit, but it may never invent one: every member it
   names must come from the shortlist the cosine produced, so the model can
   explain a recommendation but never manufacture one.

The result is persisted on the target's own ``RelevanceScore.signals["member_fit"]``
at scoring time, so the read path stays one query per area. Only the username is
stored — display name and initials are resolved live at read time, so renaming a
member never needs a re-score (the same rule ``cluster_labels`` follows).

Every LLM seam degrades to signal 1 alone. A lab with no embedded member profiles
simply gets no recommendation layer; the feed itself is unaffected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.core.people import display_name

from .fanout import cosine, member_vector
from .models import ContentItem, RelevanceScore

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]

#: How much of an item's abstract/description the model is shown per item.
_ABSTRACT_CHARS = 420

#: How much of a member's profile the model is shown.
_PROFILE_CHARS = 320

_SYSTEM_PROMPT = (
    "You are Mylo, a research consultant embedded in a lab. You are given the "
    "lab members' research profiles and a numbered list of items the lab "
    "matched (papers, grants, fellowships, or conferences). For each item, say "
    "which of those members it is most applicable to and why.\n"
    "Return ONLY one JSON object:\n"
    '  {"items": [{"item": <number>, "members": [{"member": <number>, '
    '"why": <one sentence, addressed to the lab, naming the concrete link '
    "between THIS item and THAT member's work>}]}]}\n"
    "Rules: only ever name members from the numbered roster given for that item "
    "— never invent a person or reach for someone not listed. Order each item's "
    "members best first. Name at most the members the item genuinely suits: if "
    "only one of them fits, name only that one; if none genuinely fit, return an "
    "empty members list for that item. Ground every sentence in the item and the "
    "member's stated research — do not invent findings, affiliations, or "
    "eligibility. No prose outside the JSON, no markdown fences."
)


# --------------------------------------------------------------------------- #
# Candidates
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MemberCandidate:
    """One member of the scope, with everything the ranking + prompt need."""

    username: str
    name: str
    vector: list[float]
    profile_text: str
    terms: tuple[str, ...]


def _profile_terms(interests: dict) -> tuple[str, ...]:
    """A member's own research vocabulary — areas + keywords, lowercased."""
    terms: list[str] = []
    seen: set[str] = set()
    for key in ("areas", "keywords"):
        for value in interests.get(key) or []:
            text = " ".join(str(value).split()).lower()
            if text and text not in seen:
                seen.add(text)
                terms.append(text)
    return tuple(terms)


def _profile_text(interests: dict) -> str:
    """A one-blob research summary of a member, for the prompt."""
    parts: list[str] = []
    statement = " ".join(str(interests.get("statement") or "").split())
    if statement:
        parts.append(statement)
    for label, key in (("Focus", "areas"), ("Keywords", "keywords")):
        values = [
            " ".join(str(v).split())
            for v in (interests.get(key) or [])
            if str(v).strip()
        ]
        if values:
            parts.append(f"{label}: {', '.join(values[:12])}")
    return " · ".join(parts)[:_PROFILE_CHARS]


def build_candidates(
    users: Iterable, *, embed_missing: bool = False
) -> list[MemberCandidate]:
    """The members who can be recommended to — those with an interest vector.

    ``embed_missing`` off (the default, and what the daily/refit passes use) scores
    only members with a stored ``Profile.embedding``, so annotating a feed never
    turns into an embedding job. A member with no profile vector is simply not a
    candidate; they are never named on a guess.
    """
    out: list[MemberCandidate] = []
    for user in users:
        vector = member_vector(user, embed_missing=embed_missing)
        if not vector:
            continue
        profile = getattr(user, "profile", None)
        interests = (getattr(profile, "interests", None) or {}) if profile else {}
        out.append(
            MemberCandidate(
                username=user.get_username(),
                name=display_name(user),
                vector=list(vector),
                profile_text=_profile_text(interests),
                terms=_profile_terms(interests),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Signal 1 — the cosine shortlist
# --------------------------------------------------------------------------- #


def rank_members(
    item_vector: Sequence[float],
    candidates: Sequence[MemberCandidate],
    *,
    floor: float | None = None,
    limit: int | None = None,
) -> list[tuple[MemberCandidate, float]]:
    """The members this item fits, best first — cosine above ``floor``, capped.

    The cosine is read directly (never an RRF rank), the same calibration rule
    :mod:`apps.content.fanout` follows: only an absolute similarity means anything
    as a threshold.
    """
    if not item_vector or not candidates:
        return []
    floor = settings.MEMBER_FIT_COSINE_FLOOR if floor is None else floor
    limit = settings.MEMBER_FIT_MAX_MEMBERS if limit is None else limit
    scored = [
        (candidate, cosine(item_vector, candidate.vector)) for candidate in candidates
    ]
    scored = [pair for pair in scored if pair[1] >= floor]
    scored.sort(key=lambda pair: (-pair[1], pair[0].username))
    return scored[:limit]


def _item_text(item: ContentItem) -> str:
    """Title + body snippet for one item, whatever kind of item it is."""
    meta = item.metadata or {}
    title = " ".join(str(meta.get("title") or "Untitled").split())
    body = ""
    for key in ("abstract", "description", "blurb", "summary", "search_text"):
        value = meta.get(key)
        if value:
            body = " ".join(str(value).split())
            break
    return f"{title}. {body}"[: _ABSTRACT_CHARS + 120]


def _shared_terms(item: ContentItem, candidate: MemberCandidate) -> list[str]:
    """The member's own research terms that literally appear in the item."""
    haystack = _item_text(item).lower()
    return [term for term in candidate.terms if len(term) > 3 and term in haystack][:3]


def _fallback_reason(
    item: ContentItem, candidate: MemberCandidate, similarity: float
) -> str:
    """The deterministic 'why' — honest about being a profile-similarity call."""
    shared = _shared_terms(item, candidate)
    if shared:
        return (
            f"Overlaps {candidate.name}'s work on "
            f"{', '.join(shared)} ({round(similarity * 100)}% profile match)."
        )
    return (
        f"Closest match to {candidate.name}'s research profile "
        f"({round(similarity * 100)}% profile match)."
    )


# --------------------------------------------------------------------------- #
# Signal 2 — Mylo's rationale
# --------------------------------------------------------------------------- #


def _build_prompt(
    units: Sequence[tuple[ContentItem, list[tuple[MemberCandidate, float]]]],
) -> str:
    lines: list[str] = []
    for index, (item, shortlist) in enumerate(units, start=1):
        lines.append(f"ITEM {index}: {_item_text(item)}")
        lines.append("  Candidate members:")
        for member_index, (candidate, similarity) in enumerate(shortlist, start=1):
            summary = candidate.profile_text or "(no research profile recorded)"
            lines.append(
                f"    {member_index}. {candidate.name} "
                f"[profile similarity {round(similarity * 100)}%] — {summary}"
            )
        lines.append("")
    return "\n".join(lines).strip()


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="member_fit")
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    return response.content


def _parse(
    raw: str | None,
    units: Sequence[tuple[ContentItem, list[tuple[MemberCandidate, float]]]],
) -> dict[str, dict[str, str]]:
    """``{content_id: {username: why}}`` from the model's JSON, or ``{}``.

    Anything the model says about a member who was not on that item's shortlist is
    dropped here — the model explains the arithmetic's picks, it does not add to
    them.
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

    out: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_index = _as_index(row.get("item"), len(units))
        if item_index is None:
            continue
        item, shortlist = units[item_index]
        members = row.get("members")
        if not isinstance(members, list):
            continue
        picks: dict[str, str] = {}
        for member_row in members:
            if not isinstance(member_row, dict):
                continue
            member_index = _as_index(member_row.get("member"), len(shortlist))
            if member_index is None:
                continue
            why = " ".join(str(member_row.get("why") or "").split())
            if not why:
                continue
            picks[shortlist[member_index][0].username] = why
        if picks:
            out[str(item.id)] = picks
    return out


def _as_index(value: Any, count: int) -> int | None:
    """A 1-based reference from the model → a 0-based index, or ``None``."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    index = number - 1
    return index if 0 <= index < count else None


def _mylo_rationales(
    units: Sequence[tuple[ContentItem, list[tuple[MemberCandidate, float]]]],
    *,
    complete: CompleteFn | None,
) -> dict[str, dict[str, str]]:
    """Mylo's per-member sentence for each unit; ``{}`` on any failure."""
    if not units:
        return {}
    ask = complete if complete is not None else _settings_complete
    try:
        raw = ask(_build_prompt(units))
    except Exception as exc:
        # An unreachable model is an expected degradation — one concise line, then
        # the deterministic reasons carry the layer.
        logger.warning(
            "member-fit rationale unavailable (%s); using similarity reasons.", exc
        )
        return {}
    if not raw:
        return {}
    parsed = _parse(raw, units)
    if not parsed:
        logger.warning(
            "member-fit LLM returned nothing usable; using similarity reasons. "
            "Response head: %r",
            raw[:300],
        )
    return parsed


# --------------------------------------------------------------------------- #
# Compute + persist
# --------------------------------------------------------------------------- #


def compute_member_fit(
    scores: Sequence[RelevanceScore],
    candidates: Sequence[MemberCandidate],
    *,
    complete: CompleteFn | None = None,
    llm_limit: int | None = None,
    floor: float | None = None,
    limit: int | None = None,
    prior: dict[str, dict[str, str]] | None = None,
) -> dict[str, list[dict]]:
    """``{content_id: [{username, fit, reason, source}]}`` for the given scores.

    ``scores`` is one area's rows for a single target, already in feed order (best
    first). An item with no embedding, or with no member above the floor, simply
    gets no entry — the card then renders without a recommendation strip rather
    than with a hedged one.

    ``prior`` is the last run's Mylo-written rationales (``{content_id: {username:
    why}}``). An item Mylo has already explained is carried forward rather than
    re-sent, exactly as the paper and opportunity digests carry their verdicts
    forward: the nightly run then spends its ``llm_limit`` on items nobody has
    explained yet, and the wording a reader saw yesterday does not churn overnight
    for no reason.
    """
    if not candidates:
        return {}
    llm_limit = settings.MEMBER_FIT_LLM_LIMIT if llm_limit is None else llm_limit
    prior = prior or {}

    units: list[tuple[ContentItem, list[tuple[MemberCandidate, float]]]] = []
    for score in scores:
        item = score.content
        vector = item.embedding
        if vector is None:
            continue
        shortlist = rank_members(list(vector), candidates, floor=floor, limit=limit)
        if shortlist:
            units.append((item, shortlist))
    if not units:
        return {}

    unexplained = [unit for unit in units if str(unit[0].id) not in prior]
    fresh = _mylo_rationales(unexplained[:llm_limit], complete=complete)
    rationales = {**prior, **fresh}

    out: dict[str, list[dict]] = {}
    for item, shortlist in units:
        cid = str(item.id)
        written = rationales.get(cid, {})
        rows: list[dict] = []
        for candidate, similarity in shortlist:
            why = written.get(candidate.username)
            # Mylo saw this item and left this member out: that is a judgement, not
            # a gap — drop them rather than pad the card with a similarity line.
            if cid in rationales and not why:
                continue
            rows.append(
                {
                    "username": candidate.username,
                    "fit": round(similarity * 100),
                    "reason": why or _fallback_reason(item, candidate, similarity),
                    "source": "llm" if why else "similarity",
                }
            )
        if rows:
            out[cid] = rows
    return out


def annotate_member_fit(
    target_filter: dict,
    users: Iterable,
    *,
    content_types: Sequence[str] | None = None,
    complete: CompleteFn | None = None,
    llm_limit: int | None = None,
    embed_missing: bool = False,
    log: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Recompute and persist ``signals["member_fit"]`` for one target's feeds.

    Runs after that target's areas have been scored (the daily append or an
    on-demand refit), over the rows the feed actually shows. Rows that lose their
    recommendation — a member left the lab, a profile moved on — have the key
    cleared rather than left stale. Rationales Mylo already wrote are carried
    forward, so a nightly run explains the day's arrivals instead of re-writing
    the whole feed. Returns ``{area: items annotated}``.

    Best-effort by contract: a failure here must never sink the scoring run that
    produced the feed, so callers wrap it. Nothing about the feed's contents
    depends on it.
    """
    candidates = build_candidates(users, embed_missing=embed_missing)
    types = content_types or (
        ContentItem.Type.PAPER,
        ContentItem.Type.GRANT,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.FELLOWSHIP,
    )
    written: dict[str, int] = {}
    for ctype in types:
        scores = [
            score
            for score in RelevanceScore.objects.filter(
                **target_filter, content__type=ctype
            ).select_related("content")
            if score.signals.get("suggested")
        ]
        if not scores:
            written[ctype] = 0
            continue
        scores.sort(key=_feed_order)
        fits = compute_member_fit(
            scores,
            candidates,
            complete=complete,
            llm_limit=llm_limit,
            prior=_prior_rationales(scores),
        )
        changed: list[RelevanceScore] = []
        for score in scores:
            rows = fits.get(str(score.content_id))
            current = score.signals.get("member_fit")
            if rows:
                if current != rows:
                    score.signals["member_fit"] = rows
                    changed.append(score)
            elif current is not None:
                score.signals.pop("member_fit", None)
                changed.append(score)
        if changed:
            RelevanceScore.objects.bulk_update(changed, ["signals"], batch_size=200)
        written[ctype] = len(fits)
        if log is not None:
            log(f"[member-fit:{ctype}] named members on {len(fits)} of {len(scores)}")
    return written


def _prior_rationales(scores: Sequence[RelevanceScore]) -> dict[str, dict[str, str]]:
    """The Mylo-written rationales already stored, ``{content_id: {username: why}}``.

    Only ``source == "llm"`` rows carry forward: a deterministic overlap line is a
    stand-in for a rationale nobody wrote, so it must not block the item from
    reaching the model on a later run.
    """
    out: dict[str, dict[str, str]] = {}
    for score in scores:
        written = {
            entry["username"]: entry["reason"]
            for entry in (score.signals.get("member_fit") or [])
            if entry.get("source") == "llm"
            and entry.get("username")
            and entry.get("reason")
        }
        if written:
            out[str(score.content_id)] = written
    return out


def _feed_order(score: RelevanceScore):
    """The order the feed shows a row in — strongest match first."""
    match = score.signals.get("match_percent")
    match = match if isinstance(match, int) else -1
    return (-match, -score.score)


# --------------------------------------------------------------------------- #
# Scope resolution — who "the members" are for a target
# --------------------------------------------------------------------------- #


def scope_members(persist_kwargs: dict) -> list:
    """The people a target's recommendations can name.

    A **lab**: its members. A **project**: its lab's members when it is lab-scoped
    (the people who could pick the work up), else its own members. Anything else
    (a personal target) has nobody to recommend to and yields an empty list — which
    is exactly why the personal pages carry no recommendation layer.
    """
    from apps.accounts.models import LabMembership

    lab = persist_kwargs.get("target_lab")
    project = persist_kwargs.get("target_project")
    if lab is None and project is not None:
        lab = getattr(project, "scope_lab", None)
    if lab is not None:
        return [
            membership.user
            for membership in LabMembership.objects.filter(lab=lab).select_related(
                "user", "user__profile"
            )
        ]
    if project is not None:
        return list(project.members.select_related("profile"))
    return []


def annotate_for_target(
    target,
    *,
    complete: CompleteFn | None = None,
    llm_limit: int | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Annotate one :class:`~apps.content.targets.MatchTarget`'s feeds. Never raises.

    The single call site the scoring passes use: it resolves the scope's members,
    recomputes the layer, and swallows any failure — the feed has already been
    written and must not be rolled back because the "who is this for" pass had a
    bad day.
    """
    try:
        members = scope_members(target.persist_kwargs)
        if not members:
            return {}
        return annotate_member_fit(
            target.persist_kwargs,
            members,
            complete=complete,
            llm_limit=llm_limit,
            log=log,
        )
    except Exception:  # pragma: no cover - defensive; the feed is already written
        logger.warning("member-fit annotation failed for %s", target.key, exc_info=True)
        return {}
