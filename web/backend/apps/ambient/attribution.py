"""Which project a conversation is about — with a confidence, or honestly not.

The binding is the **server**, not a channel. A conversation moves between
channels and projects, and one channel can carry three projects in an
afternoon, so every message is scored against the projects its speaker could
plausibly mean, from seven kinds of evidence:

=====================  ====================================================
Signal                 Score
=====================  ====================================================
name or alias          1.0 exact, 0.6 fuzzy — the strongest single signal
known entities         0.25 per dataset, method, venue or milestone the
                       project already lists, up to 0.6
thread inheritance     0.7 for the project a thread's opening was about,
                       unless the content disagrees strongly
continuity             up to 0.75 for the last message in the same place
                       that named the project, falling to nothing over the
                       window; it never chains, and yields to content
title                  0.4 when a thread or forum-post title names it
channel hint           0.3 for a channel's optional default project
participants           up to 0.3 by how many of the others talking are on it
semantic similarity    up to 0.5, only at the nightly read (an embedder)
=====================  ====================================================

**The decision rule** is a floor and a margin: the top candidate wins only if
its score reaches ``AMBIENT_ATTRIBUTION_FLOOR`` *and* it leads the runner-up by
``AMBIENT_ATTRIBUTION_MARGIN``. Otherwise the answer is *unresolved* — which is
a real answer. Guessing is the failure mode: an observation filed under the
wrong project corrupts two things at once, and an unresolved one can still be an
interest observation, or be asked about. Every signal except a name, an alias
or known entities sits below the floor on its own, so a channel hint, a title,
continuity or who-else-is-talking can raise confidence but never decide.

The scorer (:func:`score`) is pure: it takes candidates and a context and
touches nothing. The database half — who the candidates are, what the context
is — is below it, so the rule itself can be tested exhaustively without
fixtures.

Nothing stored here is the person's words. What is kept is the numbers, and the
*project's* vocabulary that matched: an alias, a dataset name.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

# -- signal caps ----------------------------------------------------------------

NAME_EXACT = 1.0
NAME_FUZZY = 0.6
ENTITY_EACH = 0.25
ENTITY_CAP = 0.6
INHERIT = 0.7
CONTINUITY_CAP = 0.75
TITLE_EXACT = 0.4
TITLE_FUZZY = 0.25
HINT = 0.3
PARTICIPANTS_CAP = 0.3
SEMANTIC_CAP = 0.5
#: Cosine similarity below this says nothing; the scale reaches its cap by
#: ``SEMANTIC_ZERO + SEMANTIC_SPAN``. bge-small puts unrelated research text
#: around 0.3 and closely related text above 0.7.
SEMANTIC_ZERO = 0.3
SEMANTIC_SPAN = 0.4

#: Phrases shorter than this are too likely to occur by accident ("ML", "a").
MIN_PHRASE = 3
#: Entity terms shorter than this ("data", "code") are everyone's vocabulary.
MIN_ENTITY = 5
MAX_ENTITY = 80

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def floor() -> float:
    return float(getattr(settings, "AMBIENT_ATTRIBUTION_FLOOR", 0.6))


def margin() -> float:
    return float(getattr(settings, "AMBIENT_ATTRIBUTION_MARGIN", 0.25))


def continuity_minutes() -> int:
    return int(getattr(settings, "AMBIENT_CONTINUITY_MINUTES", 30))


def thread_override() -> float:
    return float(getattr(settings, "AMBIENT_THREAD_OVERRIDE", 0.9))


# -- text matching --------------------------------------------------------------


def fold(text: str) -> str:
    """Case-folded words separated by single spaces, punctuation gone."""
    return " ".join(_NON_WORD.sub(" ", (text or "").casefold()).split())


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def phrase_match(phrase: str, folded_text: str) -> str:
    """``"exact"``, ``"fuzzy"`` or ``""`` for one phrase against folded text.

    *Exact* is the phrase as whole words. *Fuzzy* forgives what people actually
    do in chat: a plural, words in a different order ("pipeline for imaging"),
    or a one-letter typo in a long single word ("segmentaton"). It does not
    forgive a missing word — "imaging" alone is not "imaging pipeline", which is
    exactly the case where two projects share vocabulary.
    """
    target = fold(phrase)
    if len(target) < MIN_PHRASE or not folded_text:
        return ""
    if f" {target} " in f" {folded_text} ":
        return "exact"

    words = {_stem(word) for word in folded_text.split()}
    tokens = [_stem(token) for token in target.split()]
    if len(tokens) > 1:
        significant = [token for token in tokens if len(token) >= 3]
        if significant and all(token in words for token in significant):
            return "fuzzy"
        return ""

    token = tokens[0]
    if token in words:
        return "exact"
    if len(token) >= 6:
        for word in words:
            if abs(len(word) - len(token)) <= 1 and len(word) >= 6:
                if difflib.SequenceMatcher(None, token, word).ratio() >= 0.88:
                    return "fuzzy"
    return ""


# -- the pure scorer -------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One project the speaker could plausibly mean."""

    project_id: str
    name: str
    aliases: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    member_ids: frozenset[int] = frozenset()
    slow_text: str = ""


@dataclass(frozen=True)
class Context:
    """Everything the scorer knows about one message, besides its candidates."""

    text: str
    place_kind: str = "channel"
    place_label: str = ""
    hinted_project_id: str | None = None
    #: The last message in the same place whose own words named a project:
    #: (project id, minutes ago).
    continuity: tuple[str, float] | None = None
    #: The project a thread's opening was attributed to, if this is a thread.
    inherited_project_id: str | None = None
    #: The other speakers active in this place recently (user ids).
    participant_ids: frozenset[int] = frozenset()
    #: Cosine similarity of the conversation to each candidate's slow state,
    #: when an embedder was available. ``None`` means the signal is absent.
    semantic: dict[str, float] | None = None


@dataclass
class Attribution:
    """The answer for one message."""

    project_id: str | None
    confidence: float
    decided_by: str
    scores: dict[str, dict[str, float]] = field(default_factory=dict)
    matched: dict[str, list[str]] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.project_id is not None

    def totals(self) -> dict[str, float]:
        return {
            pid: round(sum(parts.values()), 4) for pid, parts in self.scores.items()
        }

    @property
    def anchor(self) -> bool:
        """Whether the message's own words named the winning project.

        Only an anchor can start continuity. A message attributed by continuity
        is not one, which is what stops a chain of "ok"s carrying a project
        across an afternoon.
        """
        if not self.resolved:
            return False
        parts = self.scores.get(self.project_id, {})
        return any(name in parts for name in _CONTENT_SIGNALS)

    def as_json(self) -> dict:
        """The stored form: numbers and project vocabulary, never the message."""
        return {
            "decided_by": self.decided_by,
            "anchor": self.anchor,
            "scores": {
                pid: {name: round(value, 4) for name, value in parts.items()}
                for pid, parts in self.scores.items()
            },
            "matched": {pid: list(terms) for pid, terms in self.matched.items()},
        }


#: Signals that come from the message's own words.
_CONTENT_SIGNALS = ("name", "entities", "semantic")


def _content_signals(candidate: Candidate, folded: str) -> tuple[dict, list[str]]:
    """The signals that come from the message's own words."""
    parts: dict[str, float] = {}
    matched: list[str] = []

    best = ""
    best_term = ""
    for phrase in (candidate.name, *candidate.aliases):
        kind = phrase_match(phrase, folded)
        if kind == "exact":
            best, best_term = kind, phrase
            break
        if kind == "fuzzy" and not best:
            best, best_term = kind, phrase
    if best:
        parts["name"] = NAME_EXACT if best == "exact" else NAME_FUZZY
        matched.append(best_term)

    entity_score = 0.0
    for term in candidate.entities:
        if phrase_match(term, folded) == "exact":
            entity_score += ENTITY_EACH
            matched.append(term)
            if entity_score >= ENTITY_CAP:
                break
    if entity_score:
        parts["entities"] = min(ENTITY_CAP, entity_score)
    return parts, matched


def _semantic(similarity: float | None) -> float:
    if similarity is None or math.isnan(similarity):
        return 0.0
    scaled = (similarity - SEMANTIC_ZERO) / SEMANTIC_SPAN * SEMANTIC_CAP
    return max(0.0, min(SEMANTIC_CAP, scaled))


def score(candidates: list[Candidate], context: Context) -> Attribution:
    """Score every candidate and apply the floor-and-margin rule."""
    if not candidates:
        return Attribution(None, 0.0, "no_candidates")

    folded = fold(context.text)
    folded_title = (
        fold(context.place_label)
        if context.place_kind in ("thread", "forum")
        else ""
    )

    scores: dict[str, dict[str, float]] = {}
    matched: dict[str, list[str]] = {}
    content: dict[str, float] = {}

    for candidate in candidates:
        parts, terms = _content_signals(candidate, folded)
        if context.semantic is not None:
            value = _semantic(context.semantic.get(candidate.project_id))
            if value:
                parts["semantic"] = value
        content[candidate.project_id] = sum(parts.values())

        if folded_title:
            for phrase in (candidate.name, *candidate.aliases):
                kind = phrase_match(phrase, folded_title)
                if kind:
                    parts["title"] = TITLE_EXACT if kind == "exact" else TITLE_FUZZY
                    terms.append(phrase)
                    break
        if context.hinted_project_id == candidate.project_id:
            parts["hint"] = HINT
        if context.participant_ids and candidate.member_ids:
            shared = len(context.participant_ids & candidate.member_ids)
            if shared:
                parts["participants"] = PARTICIPANTS_CAP * (
                    shared / len(context.participant_ids)
                )
        scores[candidate.project_id] = parts
        if terms:
            matched[candidate.project_id] = terms

    # Continuity, unless another project is named outright — the conversation
    # has moved on, and the last topic does not get to outvote the current one.
    if context.continuity and context.continuity[0] in scores:
        carried = context.continuity[0]
        window = continuity_minutes()
        age = max(0.0, float(context.continuity[1]))
        rival = max(
            (value for pid, value in content.items() if pid != carried), default=0.0
        )
        if age < window and not (
            rival >= floor() and rival > content.get(carried, 0.0)
        ):
            scores[carried]["continuity"] = CONTINUITY_CAP * (1 - age / window)

    # Thread inheritance, unless another project's own content disagrees
    # strongly — a thread that has genuinely moved on is not held to its title.
    inherited = context.inherited_project_id
    if inherited in scores:
        rival = max(
            (value for pid, value in content.items() if pid != inherited),
            default=0.0,
        )
        if not (rival >= thread_override() and rival > content.get(inherited, 0.0)):
            scores[inherited]["inherited"] = INHERIT

    ranked = sorted(
        ((sum(parts.values()), pid) for pid, parts in scores.items()),
        reverse=True,
    )
    top_score, top_id = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0

    scores = {pid: parts for pid, parts in scores.items() if parts}
    if top_score < floor():
        return Attribution(None, 0.0, "below_floor", scores, matched)
    if top_score - runner_up < margin():
        return Attribution(None, 0.0, "no_margin", scores, matched)
    return Attribution(
        top_id, round(min(1.0, top_score), 4), "resolved", scores, matched
    )


# -- the database half -----------------------------------------------------------


def _entities_for(project) -> tuple[str, ...]:
    """The names a project's state already knows: data, methods, venues, milestones."""
    state = getattr(project, "state", None)
    if state is None:
        return ()
    slow = state.slow if isinstance(state.slow, dict) else {}
    fast = state.fast if isinstance(state.fast, dict) else {}
    terms: list[str] = []
    for key in ("data", "method", "planned_components"):
        values = slow.get(key) or []
        terms.extend(str(value) for value in values if isinstance(value, str))
    for venue in fast.get("venue_targets") or []:
        if isinstance(venue, dict) and venue.get("venue"):
            terms.append(str(venue["venue"]))
    for milestone in fast.get("milestones") or []:
        if isinstance(milestone, dict) and milestone.get("what"):
            terms.append(str(milestone["what"]))

    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        folded = fold(term)
        if MIN_ENTITY <= len(folded) <= MAX_ENTITY and folded not in seen:
            seen.add(folded)
            out.append(term.strip())
    return tuple(out)


def _slow_text(project) -> str:
    state = getattr(project, "state", None)
    parts = [project.name]
    if state is not None and isinstance(state.slow, dict):
        slow = state.slow
        parts.append(str(slow.get("problem") or ""))
        parts.append(str(slow.get("claimed_contribution") or ""))
        parts.extend(str(one) for one in (slow.get("method") or []))
    goals = project.goals if isinstance(project.goals, dict) else {}
    parts.append(str(goals.get("description") or ""))
    return " ".join(part for part in parts if part).strip()


def _aliases(project) -> tuple[str, ...]:
    raw = project.aliases if isinstance(project.aliases, list) else []
    return tuple(str(alias) for alias in raw if str(alias).strip())


def candidate_projects(speaker, source, *, place_kind: str):
    """The projects this speaker could plausibly mean, here.

    Only projects the speaker is **on** — their personal projects and those
    they are a member of — plus, in a lab channel only, the lab's projects that
    are shared into lab reports. A DM never attributes to a project the speaker
    is not on: that is a hard filter, not a score.
    """
    from apps.research.models import Project

    on = Q(scope_user=speaker) | Q(memberships__user=speaker)
    if place_kind != "dm" and getattr(source, "lab_id", None):
        on |= Q(scope_lab_id=source.lab_id, share_in_lab_reports=True)
    return (
        Project.objects.filter(is_archived=False)
        .filter(on)
        .select_related("state")
        .prefetch_related("memberships")
        .distinct()
    )


def candidates_for(speaker, source, *, place_kind: str) -> list[Candidate]:
    """Build scorer candidates from the database."""
    out: list[Candidate] = []
    for project in candidate_projects(speaker, source, place_kind=place_kind):
        members = {membership.user_id for membership in project.memberships.all()}
        if project.scope_user_id:
            members.add(project.scope_user_id)
        out.append(
            Candidate(
                project_id=str(project.pk),
                name=project.name,
                aliases=_aliases(project),
                entities=_entities_for(project),
                member_ids=frozenset(members),
                slow_text=_slow_text(project),
            )
        )
    return out


def _place_filter(place_id: str) -> dict:
    """Same place: the same channel or thread id (a DM has none)."""
    return {"place_id": str(place_id or "")}


def continuity_for(source, place_id: str, *, before, exclude_pk=None):
    """The last message in the same place that named its project, and how long ago.

    Only an anchor — a message whose own words named the project — or one a
    person corrected. See :attr:`Attribution.anchor`.
    """
    from .models import RawMessageRef

    window = continuity_minutes()
    recent = (
        RawMessageRef.objects.filter(
            Q(attribution__anchor=True) | Q(attribution__corrected=True),
            source=source,
            project__isnull=False,
            deleted_at__isnull=True,
            sent_at__lte=before,
            sent_at__gte=before - timedelta(minutes=window),
            **_place_filter(place_id),
        )
        .exclude(pk=exclude_pk)
        .order_by("-sent_at", "-pk")
        .first()
    )
    if recent is None:
        return None
    minutes = (before - recent.sent_at).total_seconds() / 60.0
    return (str(recent.project_id), minutes)


def thread_opening_for(source, place_id: str, place_kind: str, *, exclude_pk=None):
    """The project a thread's opening was attributed to, if any.

    A thread or forum post is attributed once, from its opening, and every later
    message inherits unless its own content disagrees strongly.
    """
    from .models import RawMessageRef

    if place_kind not in ("thread", "forum") or not place_id:
        return None
    opening = (
        RawMessageRef.objects.filter(
            source=source,
            place_id=str(place_id),
            project__isnull=False,
            deleted_at__isnull=True,
        )
        .exclude(pk=exclude_pk)
        .order_by("sent_at", "pk")
        .first()
    )
    return str(opening.project_id) if opening else None


def participants_for(source, place_id: str, *, before, speaker_id, exclude_pk=None):
    """The other people talking in the same place, recently."""
    from .models import RawMessageRef

    window = continuity_minutes()
    ids = (
        RawMessageRef.objects.filter(
            source=source,
            speaker__isnull=False,
            deleted_at__isnull=True,
            sent_at__lte=before,
            sent_at__gte=before - timedelta(minutes=window),
            **_place_filter(place_id),
        )
        .exclude(pk=exclude_pk)
        .exclude(speaker_id=speaker_id)
        .values_list("speaker_id", flat=True)
        .distinct()
    )
    return frozenset(ids)


def hint_for(source, place_id: str) -> str | None:
    from .models import ChannelHint

    if not place_id:
        return None
    hint = ChannelHint.objects.filter(source=source, place_id=str(place_id)).first()
    return str(hint.project_id) if hint else None


def context_for(ref, text: str, *, semantic=None) -> Context:
    """The scorer's context for one stored reference."""
    return Context(
        text=text,
        place_kind=ref.place_kind,
        place_label=ref.place_label,
        hinted_project_id=hint_for(ref.source, ref.place_id),
        continuity=continuity_for(
            ref.source, ref.place_id, before=ref.sent_at, exclude_pk=ref.pk
        ),
        inherited_project_id=thread_opening_for(
            ref.source, ref.place_id, ref.place_kind, exclude_pk=ref.pk
        ),
        participant_ids=participants_for(
            ref.source,
            ref.place_id,
            before=ref.sent_at,
            speaker_id=ref.speaker_id,
            exclude_pk=ref.pk,
        ),
        semantic=semantic,
    )


def apply(ref, result: Attribution) -> None:
    """Write an attribution onto a reference."""
    ref.project_id = result.project_id
    ref.project_confidence = result.confidence if result.resolved else 0.0
    ref.attribution = result.as_json()
    ref.attributed_at = timezone.now()
    ref.save(
        update_fields=[
            "project",
            "project_confidence",
            "attribution",
            "attributed_at",
        ]
    )


def attribute_ref(ref, text: str, *, semantic=None) -> Attribution | None:
    """Attribute one stored reference from its text. Mylo's own lines are skipped."""
    if ref.speaker_id is None:
        return None
    candidates = candidates_for(ref.speaker, ref.source, place_kind=ref.place_kind)
    result = score(candidates, context_for(ref, text, semantic=semantic))
    apply(ref, result)
    return result


# -- the nightly pass -------------------------------------------------------------

#: How many earlier lines in the same place the semantic signal reads with a
#: message. One line ("that's the bottleneck") says little; the few before it
#: say what "that" was.
SEMANTIC_CONTEXT_LINES = 5


def _cosine(left, right) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def attribute_window(window_, *, embedder=None) -> dict:
    """Re-score what the arrival pass left unresolved, now with more to go on.

    Called by the nightly read (Plan 04) on each window *before* extraction,
    while the bodies still exist. Only unresolved references are touched: a
    resolved one stays as it was, and one a person corrected is never
    second-guessed. With an ``embedder`` the semantic signal joins in — the
    conversation around the message against each candidate's slow state; with
    none it is simply absent, as on arrival.

    Returns counts, for the caller to log.
    """
    from .models import RawMessageRef

    readable = window_.readable
    by_id = {message.external_id: message for message in readable}
    refs = {
        ref.external_id: ref
        for ref in RawMessageRef.objects.filter(
            source_id=window_.source_id,
            external_id__in=list(by_id),
            project__isnull=True,
            speaker__isnull=False,
            deleted_at__isnull=True,
        ).select_related("source", "speaker")
    }
    counts = {"considered": 0, "resolved": 0}
    slow_vectors: dict[str, list[float]] = {}
    earlier: dict[str, list[str]] = {}

    for message in readable:
        lines = earlier.setdefault(message.place_id, [])
        ref = refs.get(message.external_id)
        if ref is not None and not (ref.attribution or {}).get("corrected"):
            counts["considered"] += 1
            semantic = None
            if embedder is not None:
                semantic = _semantic_scores(
                    ref, [*lines[-SEMANTIC_CONTEXT_LINES:], message.text],
                    embedder, slow_vectors,
                )
            result = attribute_ref(ref, message.text, semantic=semantic)
            if result is not None and result.resolved:
                counts["resolved"] += 1
        lines.append(message.text)
    return counts


def _semantic_scores(ref, lines, embedder, cache) -> dict[str, float] | None:
    candidates = candidates_for(ref.speaker, ref.source, place_kind=ref.place_kind)
    todo = [c for c in candidates if c.slow_text and c.project_id not in cache]
    try:
        vectors = embedder([" ".join(lines), *(c.slow_text for c in todo)])
    except Exception:  # pragma: no cover - an embedder failure means no signal
        return None
    if not vectors:
        return None
    for candidate, vector in zip(todo, vectors[1:], strict=False):
        cache[candidate.project_id] = list(vector)
    conversation = list(vectors[0])
    return {
        c.project_id: _cosine(conversation, cache[c.project_id])
        for c in candidates
        if c.project_id in cache
    }
