"""Deciding what observations mean, once a night (Plan 04, deliberation).

Pure over the ledger: no model call, no text, rerunnable at will. It never acts
on one observation. For every person and project it gathers the trailing
``AMBIENT_LOOKBACK_DAYS`` of observations, groups them by **concept** (one
topic said three ways is one topic seen three times), and computes the
consistency facts Plan 06 reads — distinct days, distinct conversations, the
span, the force mix, explicitness, the last rejection. From those it chooses
exactly one outcome per finding and writes it to :class:`~.models.Finding`,
with the rule that chose it.

The outcomes (Plan 04, step 8):

* **ignore** — below the floor, superseded, about a colleague, already
  covered, or declined. Recorded, so the reason is inspectable.
* **record** — a project fact a person told Mylo directly (a DM, a mention):
  the one thing that becomes a dated development without a question (OD-A3).
* **suggest** — a topic that passed the consistency test, is not covered and
  was never declined, or a project development seen consistently in ambient
  talk. Plan 05 writes it as a *pending* conversational edge or development;
  Plan 06 asks.
* **capability** — repeated first-person doing: a suggested skill, never an area.
* **propose** — an edit to a project's stated intent; Plan 08 raises it.
* **ask** — the evidence would matter but is ambiguous: the project could not
  be told apart, self and colleague could not be told apart, or a possibility
  never became a decision.

**Budget** (step 9). Deliberation spends nothing. It records whether the
person's declared profile has room for the topic and, when it has not, which
cluster nobody has talked about in ``AMBIENT_STALE_DAYS`` — the swap Plan 08
may offer. Removing anything stated is never an outcome.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    PERSONAL_KINDS,
    Finding,
    Force,
    Observation,
    Subject,
    UnderstandingKind,
    Visibility,
)

logger = logging.getLogger(__name__)

#: How much one statement weighs by how firmly it was said. A decision
#: outweighs five possibilities; a rejection weighs nothing — it retires.
FORCE_WEIGHT = {
    Force.DECISION: 1.0,
    Force.FACT: 0.9,
    Force.PREFERENCE: 0.8,
    Force.POSSIBILITY: 0.35,
    Force.QUESTION: 0.25,
    Force.REJECTION: 0.0,
}
STRONG = frozenset({Force.PREFERENCE, Force.DECISION, Force.FACT})
#: Somebody addressing Mylo meant to be understood.
EXPLICIT_WEIGHT = 1.5
#: What a later rejection retires, and what a later fact closes.
RETIRED_BY_REJECTION = frozenset(
    {Force.POSSIBILITY, Force.QUESTION, Force.DECISION, Force.PREFERENCE, Force.FACT}
)
CLOSED_BY_FACT = frozenset({Force.QUESTION, Force.POSSIBILITY})

#: The knowledge-core relation each kind would be recorded under (Plan 05).
RELATION = {
    UnderstandingKind.ENDURING_INTEREST: "interested_in",
    UnderstandingKind.CURRENT_CURIOSITY: "interested_in",
    UnderstandingKind.WORK_PREFERENCE: "interested_in",
    UnderstandingKind.CAREER_DIRECTION: "interested_in",
    UnderstandingKind.CAPABILITY: "can_do",
    UnderstandingKind.LEARNING_GOAL: "wants_to_learn",
    UnderstandingKind.PROJECT_INTENT: "works_on",
    UnderstandingKind.PROJECT_DEVELOPMENT: "works_on",
}
#: Which of a person's own relations make a topic "already covered", per kind.
COVERING = {
    UnderstandingKind.CAPABILITY: {"can_do", "uses_method"},
    UnderstandingKind.LEARNING_GOAL: {"wants_to_learn", "can_do"},
}
_INTEREST_COVERING = {"interested_in", "can_do", "wants_to_learn", "works_on"}


#: Kinds that are one topic seen from slightly different angles. "I'd love to
#: dig into X", "X has been on my mind" and "I want to learn X" are the same
#: person coming back to the same thing; splitting them by kind would keep a
#: real, repeated interest under the floor three times over. One finding per
#: topic; its kind is the one said most (latest on a tie).
INTEREST_FAMILY = frozenset(
    {
        UnderstandingKind.ENDURING_INTEREST,
        UnderstandingKind.CURRENT_CURIOSITY,
        UnderstandingKind.LEARNING_GOAL,
    }
)
_FAMILY = "interest"


def _family(observation) -> str:
    """The group an observation's kind decides in.

    A project intent with no project and the speaker as its subject is one
    person's own intention — "I want to dig into X for my next project" with
    nothing to attribute it to — and joins their interest family rather than
    becoming an unresolved project question (EXP-2026-09-013).
    """
    kind = observation.understanding_kind
    if (
        kind == UnderstandingKind.PROJECT_INTENT
        and not observation.project_id
        and observation.subject == Subject.SELF
    ):
        return _FAMILY
    return _FAMILY if kind in INTEREST_FAMILY else kind


def _dominant(rows) -> str:
    """The family's kind: the interest kind said most, latest on a tie. A
    self intent folded in counts as a current curiosity."""

    def kind_of(o):
        if o.understanding_kind in INTEREST_FAMILY:
            return o.understanding_kind
        return UnderstandingKind.CURRENT_CURIOSITY

    counts = Counter(kind_of(o) for o in rows)
    latest = {kind_of(o): o.observed_at for o in rows}
    return max(counts, key=lambda kind: (counts[kind], latest[kind]))


@dataclass
class DeliberateRun:
    people: int = 0
    projects: int = 0
    linked: int = 0
    superseded: int = 0
    findings: Counter = field(default_factory=Counter)
    paused: int = 0

    def as_dict(self) -> dict:
        data = dict(self.__dict__)
        data["findings"] = dict(self.findings)
        return data


# -- the numbers ------------------------------------------------------------------


def _weight(observation: Observation, now) -> float:
    age = max(0.0, (now - observation.observed_at).total_seconds() / 86400)
    half_life = float(settings.AMBIENT_HALF_LIFE_DAYS) or 21.0
    weight = FORCE_WEIGHT.get(observation.force, 0.25)
    if observation.explicit:
        weight *= EXPLICIT_WEIGHT
    confidence = observation.extraction_confidence
    weight *= 0.5 + 0.5 * (confidence if confidence is not None else 0.6)
    return round(weight * math.pow(0.5, age / half_life), 4)


@dataclass
class Facts:
    days: int = 0
    conversations: int = 0
    span_days: int = 0
    forces: dict = field(default_factory=dict)
    explicit: int = 0
    first_seen: str = ""
    last_seen: str = ""
    last_rejection: str = ""
    strong: bool = False
    influence: float = 0.0

    def consistent(self) -> bool:
        return (
            self.days >= settings.AMBIENT_CONSISTENT_DAYS
            and self.span_days >= settings.AMBIENT_CONSISTENT_SPAN_DAYS
            and self.conversations >= settings.AMBIENT_CONSISTENT_CONVERSATIONS
            and self.strong
        )

    def repeated(self) -> bool:
        """Consistent on days and conversations, whatever the force."""
        return (
            self.days >= settings.AMBIENT_CONSISTENT_DAYS
            and self.span_days >= settings.AMBIENT_CONSISTENT_SPAN_DAYS
            and self.conversations >= settings.AMBIENT_CONSISTENT_CONVERSATIONS
        )


def facts(observations: list[Observation], now, *, since=None) -> Facts:
    """The consistency facts over the observations after the last rejection
    (and after ``since``, when a declined topic must be met afresh)."""
    rejections = [o.observed_at for o in observations if o.force == Force.REJECTION]
    last_rejection = max(rejections) if rejections else None
    floor = max(filter(None, [last_rejection, since]), default=None)
    live = [
        o
        for o in observations
        if o.force != Force.REJECTION and (floor is None or o.observed_at > floor)
    ]
    out = Facts(
        last_rejection=last_rejection.date().isoformat() if last_rejection else ""
    )
    if not live:
        return out
    local = [timezone.localtime(o.observed_at).date() for o in live]
    out.days = len(set(local))
    out.span_days = (max(local) - min(local)).days
    out.conversations = len({o.conversation_key or f"obs:{o.pk}" for o in live})
    out.forces = dict(Counter(o.force for o in live))
    out.explicit = sum(1 for o in live if o.explicit)
    out.first_seen = min(local).isoformat()
    out.last_seen = max(local).isoformat()
    out.strong = any(o.force in STRONG for o in live)
    # One conversation counts once: its strongest statement, not every repeat.
    best: dict[str, float] = {}
    for o in live:
        key = o.conversation_key or f"obs:{o.pk}"
        best[key] = max(best.get(key, 0.0), _weight(o, now))
    out.influence = round(sum(best.values()), 4)
    return out


# -- supersession -----------------------------------------------------------------


def supersede(observations: list[Observation], now) -> int:
    """A later rejection retires what came before it; a later fact closes an
    earlier question. ``observations`` are one subject's, on one concept."""
    ordered = sorted(observations, key=lambda o: (o.observed_at, o.pk))
    retired = 0
    for index, later in enumerate(ordered):
        if later.force == Force.REJECTION:
            retires = RETIRED_BY_REJECTION
        elif later.force == Force.FACT:
            retires = CLOSED_BY_FACT
        else:
            continue
        for earlier in ordered[:index]:
            if (
                earlier.status == Observation.Status.ACTIVE
                and earlier.force in retires
                and earlier.observed_at <= later.observed_at
            ):
                earlier.status = Observation.Status.SUPERSEDED
                earlier.superseded_at = now
                Observation.objects.filter(pk=earlier.pk).update(
                    status=Observation.Status.SUPERSEDED, superseded_at=now
                )
                if later.supersedes_id is None:
                    later.supersedes_id = earlier.pk
                    Observation.objects.filter(pk=later.pk).update(
                        supersedes_id=earlier.pk
                    )
                retired += 1
    return retired


# -- what the person already has --------------------------------------------------


def _cosine(left, right) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


@dataclass
class Holdings:
    """A person's own edges, as the coverage and decline checks need them."""

    # (live id, relation, label, conversational?)
    covering: list = field(default_factory=list)
    rejected: list = field(default_factory=list)  # (live id, updated_at)
    declared_areas: list = field(default_factory=list)  # EdgeView
    vectors: dict = field(default_factory=dict)


def holdings(user) -> Holdings:
    from apps.knowledge.read import live_concepts, own_edges

    edges = own_edges(user)
    concepts = live_concepts([edge.concept_id for edge in edges])
    out = Holdings()
    for edge in edges:
        view = concepts.get(edge.concept_id)
        if view is None:
            continue
        out.vectors[view.id] = view.vector
        if edge.tier == "declared" and edge.status == "active":
            out.covering.append(
                (view.id, edge.relation, edge.surface or view.label, False)
            )
            if edge.relation == "interested_in":
                out.declared_areas.append(edge)
        elif edge.tier == "conversational" and edge.status in ("active", "pending"):
            out.covering.append(
                (view.id, edge.relation, edge.surface or view.label, True)
            )
        elif edge.tier == "conversational" and edge.status == "rejected":
            out.rejected.append((view.id, edge.updated_at))
    return out


def _similar(concept_id: int, vector, other_id: int, vectors: dict) -> bool:
    if concept_id == other_id:
        return True
    return _cosine(vector, vectors.get(other_id)) >= settings.AMBIENT_COVERED_SIMILARITY


def covered_by(kind: str, concept_id: int, vector, held: Holdings) -> str | None:
    """What the person already holds that makes this topic not worth asking.

    Their declared profile, by the same concept or a near one. And what Mylo
    already understood under a *near-synonym* — a second question about the
    same idea in other words. Never the topic's own conversational edge: that
    is this finding's own suggestion (or its confirmed exploration), and it
    has to stay a suggestion to keep being reinforced.
    """
    relations = COVERING.get(kind, _INTEREST_COVERING)
    for other, relation, label, conversational in held.covering:
        if relation not in relations:
            continue
        if conversational and other == concept_id:
            continue
        if _similar(concept_id, vector, other, held.vectors):
            return label
    return None


def declined_at(concept_id: int, vector, held: Holdings):
    """When the person last said no to this topic or a near-synonym of it."""
    dates = [
        at
        for other, at in held.rejected
        if at is not None and _similar(concept_id, vector, other, held.vectors)
    ]
    return max(dates) if dates else None


# -- budget -----------------------------------------------------------------------


def budget(user, held: Holdings, observations_by_concept: dict, now) -> dict:
    """Room on the declared profile, and a swap candidate when there is none."""
    from apps.billing.entitlements import cluster_cap, cluster_topic_cap

    profile = getattr(user, "profile", None)
    interests = (getattr(profile, "interests", None) or {}) if profile else {}
    areas = [str(a) for a in interests.get("areas") or []]
    clusters = interests.get("clusters") or (
        [{"id": "all", "label": "Your interests", "areas": areas}] if areas else []
    )
    cap, topic_cap = cluster_cap(user), cluster_topic_cap(user)
    out = {
        "clusters": len(clusters),
        "cluster_cap": cap,
        "cluster_topic_cap": topic_cap,
        "room_for_cluster": len(clusters) < cap,
        "room_for_topic": any(len(c.get("areas") or []) < topic_cap for c in clusters)
        or not clusters,
        "swap_candidate": None,
    }
    if out["room_for_cluster"]:
        return out
    stale_before = now - timedelta(days=settings.AMBIENT_STALE_DAYS)
    by_surface = {edge.surface.casefold(): edge for edge in held.declared_areas}
    talked = {
        cid
        for cid, rows in observations_by_concept.items()
        if any(o.observed_at >= stale_before for o in rows)
    }
    oldest = None
    for cluster in clusters:
        edges = [by_surface.get(str(a).casefold()) for a in cluster.get("areas") or []]
        edges = [e for e in edges if e is not None]
        if not edges or any(e.first_seen > stale_before for e in edges):
            continue
        if any(e.concept_id in talked for e in edges):
            continue
        since = min(e.first_seen for e in edges)
        if oldest is None or since < oldest[0]:
            oldest = (since, cluster)
    if oldest is not None:
        out["swap_candidate"] = {
            "id": str(oldest[1].get("id") or ""),
            "label": str(oldest[1].get("label") or ""),
        }
    return out


# -- deciding ---------------------------------------------------------------------


@dataclass
class Decision:
    outcome: str
    reason: str
    facts: Facts
    extra: dict = field(default_factory=dict)


def decide_personal(kind, rows, concept_id, vector, held: Holdings, now) -> Decision:
    """One person, one concept, one of the kinds that describe them."""
    selfish = [o for o in rows if o.subject == Subject.SELF]
    unknown = [o for o in rows if o.subject == Subject.UNKNOWN]
    mine = facts(selfish, now)
    if not selfish and not unknown:
        return Decision(Finding.Outcome.IGNORE, "not_self", facts(rows, now))
    if selfish and not mine.days and mine.last_rejection:
        return Decision(Finding.Outcome.IGNORE, "rejected_in_conversation", mine)
    if not mine.consistent():
        either = facts(selfish + unknown, now)
        if unknown and either.consistent() and len(unknown) >= len(selfish):
            return Decision(Finding.Outcome.ASK, "subject_unclear", either)
        return Decision(Finding.Outcome.IGNORE, "below_floor", mine)
    label = covered_by(kind, concept_id, vector, held)
    if label is not None:
        return Decision(Finding.Outcome.IGNORE, "covered", mine, {"covered_by": label})
    said_no = declined_at(concept_id, vector, held)
    if said_no is not None:
        if now - said_no < timedelta(days=settings.AMBIENT_DECLINE_REST_DAYS):
            return Decision(
                Finding.Outcome.IGNORE,
                "declined_resting",
                mine,
                {"declined_at": said_no.date().isoformat()},
            )
        afresh = facts(selfish, now, since=said_no)
        if not afresh.consistent():
            return Decision(
                Finding.Outcome.IGNORE,
                "declined_not_returned",
                afresh,
                {"declined_at": said_no.date().isoformat()},
            )
        mine = afresh
    if kind == UnderstandingKind.CAPABILITY:
        return Decision(Finding.Outcome.CAPABILITY, "capability_consistent", mine)
    return Decision(Finding.Outcome.SUGGEST, "consistent", mine)


def _told_fact(rows) -> bool:
    return any(
        o.explicit
        and o.force in (Force.FACT, Force.DECISION)
        and o.subject in (Subject.SELF, Subject.PROJECT, Subject.LAB)
        and o.understanding_kind == UnderstandingKind.PROJECT_DEVELOPMENT
        for o in rows
    )


def decide_project(kind, rows, *, resolved: bool, covered: str | None, now) -> Decision:
    """One project (or an unresolved one), one concept, one project kind."""
    seen = facts(rows, now)
    if not seen.days and seen.last_rejection:
        return Decision(Finding.Outcome.IGNORE, "rejected_in_conversation", seen)
    live = [
        o
        for o in rows
        if o.force != Force.REJECTION
        and (
            not seen.last_rejection
            or timezone.localtime(o.observed_at).date().isoformat()
            > seen.last_rejection
        )
    ]
    if not resolved:
        # Which project? is worth a question only for a fact told to Mylo, or
        # talk consistent enough to have been suggested had it been placed.
        if _told_fact(live) or seen.consistent():
            return Decision(Finding.Outcome.ASK, "attribution_unresolved", seen)
        return Decision(Finding.Outcome.IGNORE, "below_floor", seen)
    if kind == UnderstandingKind.PROJECT_DEVELOPMENT and _told_fact(live):
        return Decision(Finding.Outcome.RECORD, "told_directly", seen)
    if not seen.consistent():
        if seen.repeated() and not seen.strong:
            return Decision(Finding.Outcome.ASK, "never_decided", seen)
        return Decision(Finding.Outcome.IGNORE, "below_floor", seen)
    if kind == UnderstandingKind.PROJECT_INTENT:
        if covered is not None:
            return Decision(
                Finding.Outcome.IGNORE, "covered", seen, {"covered_by": covered}
            )
        return Decision(Finding.Outcome.PROPOSE, "intent_consistent", seen)
    return Decision(Finding.Outcome.SUGGEST, "development_consistent", seen)


# -- the pass ---------------------------------------------------------------------


def _fingerprint(rows) -> str:
    ids = ",".join(str(o.pk) for o in sorted(rows, key=lambda o: o.pk))
    return hashlib.sha1(ids.encode()).hexdigest()


def _save(
    key: dict,
    kind: str,
    concept,
    decision: Decision,
    rows,
    visibility,
    now,
    *,
    budget_: dict | None = None,
) -> Finding:
    ids = sorted(o.pk for o in rows)
    fingerprint = _fingerprint(rows)
    needs_words = decision.outcome != Finding.Outcome.IGNORE
    finding = Finding.objects.filter(
        user_id=key.get("user_id"),
        project_id=key.get("project_id"),
        concept_id=concept.id,
        understanding_kind=kind,
    ).first() or Finding(
        user_id=key.get("user_id"),
        project_id=key.get("project_id"),
        concept_id=concept.id,
        understanding_kind=kind,
    )
    finding.topic = (rows[-1].topic or concept.label)[:200]
    finding.facet = rows[-1].facet or concept.facet
    finding.relation = RELATION.get(kind, "interested_in")
    finding.visibility = visibility
    finding.outcome = decision.outcome
    finding.reason = decision.reason
    finding.facts = decision.facts.__dict__ | decision.extra
    finding.influence = decision.facts.influence
    finding.budget = budget_ or {}
    finding.observation_ids = ids
    finding.trace = {
        "rule": decision.reason,
        "outcome": decision.outcome,
        "influence": decision.facts.influence,
        "thresholds": {
            "days": settings.AMBIENT_CONSISTENT_DAYS,
            "span_days": settings.AMBIENT_CONSISTENT_SPAN_DAYS,
            "conversations": settings.AMBIENT_CONSISTENT_CONVERSATIONS,
            "covered_similarity": settings.AMBIENT_COVERED_SIMILARITY,
            "half_life_days": settings.AMBIENT_HALF_LIFE_DAYS,
        },
        **decision.extra,
    }
    if needs_words:
        if (
            finding.explained_from != fingerprint
            or finding.explained != Finding.Explained.WRITTEN
        ):
            finding.explained = Finding.Explained.PENDING
    elif finding.explained != Finding.Explained.WRITTEN:
        finding.explained = Finding.Explained.NOT_NEEDED
    finding.decided_at = now
    finding.save()
    return finding


def _eligible(user) -> bool:
    from .eligibility import tier_is_paid

    return tier_is_paid(user)


def deliberate(*, now=None, users=None) -> DeliberateRun:
    """Decide every finding over the lookback. Pure over the ledger."""
    from django.contrib.auth import get_user_model

    from apps.knowledge.read import live_concepts, project_edges

    from .reading import link

    now = now or timezone.now()
    run = DeliberateRun()
    since = now - timedelta(days=settings.AMBIENT_LOOKBACK_DAYS)
    base = Observation.objects.filter(observed_at__gte=since).select_related(
        "project", "speaker"
    )
    if users is not None:
        base = base.filter(speaker__in=list(users))
    run.linked = link(
        list(base.filter(concept__isnull=True, status=Observation.Status.ACTIVE))
    )

    rows = list(
        base.filter(concept__isnull=False).exclude(status=Observation.Status.STALE)
    )
    concepts = live_concepts({o.concept_id for o in rows})
    by_person = defaultdict(list)
    for o in rows:
        by_person[o.speaker_id].append(o)
    people = {u.pk: u for u in get_user_model().objects.filter(pk__in=list(by_person))}

    groups: dict[tuple, list[Observation]] = defaultdict(list)
    eligible_people = set()
    for speaker_id, own in by_person.items():
        person = people.get(speaker_id)
        if person is None:
            continue
        if not _eligible(person):
            run.paused += 1  # a lapse pauses the memory; it is kept, not decided
            continue
        eligible_people.add(speaker_id)
        for o in own:
            view = concepts.get(o.concept_id)
            if view is None:
                continue
            if o.understanding_kind in PERSONAL_KINDS or not o.project_id:
                side = ("u", speaker_id, None)
            elif o.visibility == Visibility.LAB:
                side = ("p", None, str(o.project_id))
            else:
                side = ("up", speaker_id, str(o.project_id))
            groups[(side, view.id, _family(o))].append(o)

    # Supersession runs per subject and concept, across kinds.
    by_topic: dict[tuple, list[Observation]] = defaultdict(list)
    for (side, concept_id, _kind), members in groups.items():
        by_topic[(side, concept_id)].extend(members)
    for members in by_topic.values():
        run.superseded += supersede(members, now)

    held_by_person = {pk: holdings(people[pk]) for pk in eligible_people}
    by_person_concept: dict[int, dict[int, list]] = defaultdict(
        lambda: defaultdict(list)
    )
    for (side, concept_id, _kind), members in groups.items():
        if side[1] is not None:
            by_person_concept[side[1]][concept_id].extend(members)

    touched = set()
    with transaction.atomic():
        for (side, _concept_id, kind), members in groups.items():
            # What is still standing, plus the rejections that decide what
            # counts; if everything was retired, the retired rows explain why.
            members = [
                o
                for o in members
                if o.status == Observation.Status.ACTIVE or o.force == Force.REJECTION
            ] or members
            members.sort(key=lambda o: (o.observed_at, o.pk))
            concept = concepts[members[0].concept_id]
            if kind == _FAMILY:
                kind = _dominant(members)
                # One finding per topic in the family: a kind that lost the
                # majority tonight gives its row up rather than duplicating it.
                Finding.objects.filter(
                    user_id=side[1],
                    project__isnull=True,
                    concept_id=concept.id,
                    understanding_kind__in=INTEREST_FAMILY - {kind},
                ).delete()
            kind_is_personal = kind in PERSONAL_KINDS
            if side[0] == "u" and kind_is_personal:
                person = people[side[1]]
                held = held_by_person[side[1]]
                decision = decide_personal(
                    kind, members, concept.id, concept.vector, held, now
                )
                decision.extra["kinds"] = dict(
                    Counter(o.understanding_kind for o in members)
                )
                spend = None
                if decision.outcome == Finding.Outcome.SUGGEST:
                    spend = budget(person, held, by_person_concept[side[1]], now)
                finding = _save(
                    {"user_id": side[1]},
                    kind,
                    concept,
                    decision,
                    members,
                    Visibility.PERSONAL,
                    now,
                    budget_=spend,
                )
            else:
                resolved = side[2] is not None
                covered = None
                if resolved and kind == UnderstandingKind.PROJECT_INTENT:
                    stated = project_edges(members[0].project, members[0].speaker)
                    views = live_concepts([edge.concept_id for edge in stated])
                    vectors = {v.id: v.vector for v in views.values()}
                    for edge in stated:
                        view = views.get(edge.concept_id)
                        if view and _similar(
                            concept.id, concept.vector, view.id, vectors
                        ):
                            covered = edge.surface or view.label
                            break
                decision = decide_project(
                    kind, members, resolved=resolved, covered=covered, now=now
                )
                key = {"user_id": side[1], "project_id": side[2]}
                visibility = Visibility.LAB if side[0] == "p" else Visibility.PERSONAL
                finding = _save(key, kind, concept, decision, members, visibility, now)
            for o in members:
                weight = (
                    _weight(o, now) if o.status == Observation.Status.ACTIVE else 0.0
                )
                if o.influence != weight:
                    Observation.objects.filter(pk=o.pk).update(influence=weight)
            touched.add(finding.pk)
            run.findings[finding.outcome] += 1
    run.people = len(eligible_people)
    run.projects = len({side[2] for (side, _c, _k) in groups if side[2]})
    return run
