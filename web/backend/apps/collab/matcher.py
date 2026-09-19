"""The matcher: who could share this work, and who brings what it lacks (CN-05).

One matcher behind three entry points — a call, a project, or text a seeker
types (design §8.1) — all producing the same editable query of **slots**,
**lanes** and a **scope**. It runs only when a seeker asks; nothing searches for
everyone overnight.

For each lane it ranks **works**, not people (design §5.2), then credits their
authors with their best work's score — a person is never averaged into one
vector (§5.3):

| Lane | A work matches when | and must differ in |
|---|---|---|
| in-field | its problem (and setting, when the need names one) match | — |
| method bridge | its method (or its neutral phrasing) matches | field |
| problem bridge | its problem matches | method and field |
| resource | what it makes reusable matches a data slot | — |

Bridges and resources answer the slots the seeker does **not** cover ("fills a
gap"); the in-field lane answers the ones they do ("shares expertise"). Lanes
are never merged into one ranking and each keeps its own places (§9.1).

Every candidate passes one **gate** before anything about them is shown or
explained: open to collaboration and not expired; the seeker inside their
audience and they inside the seeker's scope (verified affiliations only); under
the appearance cap; not the seeker, not a lab-mate, not an existing co-author.
Their evidence is only what they declared and what their papers show
(:func:`apps.knowledge.read.discoverable_edges`, ``discoverable_works``) —
never conversation, never a project.

The model then reads each lane's shortlist and may drop a candidate and write a
one-line reason; it can never add anyone. Without the model the lanes stand in
retrieval order, unexplained, and say so.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.content.embeddings import embed_texts
from apps.core.people import display_name
from apps.knowledge.read import (
    WorkView,
    coauthor_distances,
    concept_vectors,
    discoverable_edges,
    discoverable_works,
    introduction_paths,
    network_of,
    own_edges,
)

from . import consent
from .coverage import YOU, assess
from .models import (
    Audience,
    CollaborationSetting,
    Lane,
    RequirementSlots,
    SearchLog,
    SlotFacet,
)

logger = logging.getLogger(__name__)

COMPONENT = "collab_rerank"
LANES = (Lane.IN_FIELD, Lane.METHOD_BRIDGE, Lane.PROBLEM_BRIDGE, Lane.RESOURCE)
GAP_LANES = (Lane.METHOD_BRIDGE, Lane.PROBLEM_BRIDGE, Lane.RESOURCE)

CompleteFn = Callable[[str, str], str | None]


class SearchRefused(ValueError):
    """The seeker may not run this search; nothing was searched or recorded.

    ``code`` names the reason for a surface that must decide what to show
    instead (an upgrade note, a verify prompt) without parsing the message.
    """

    def __init__(self, message: str, code: str = "refused"):
        super().__init__(message)
        self.code = code


# --- the query ------------------------------------------------------------


@dataclass
class Query:
    entry: str  # "call" | "project" | "manual"
    slots: list[dict]
    lanes: tuple[str, ...] = LANES
    scope: str = Audience.INSTITUTION
    need_fields: frozenset[str] = frozenset()
    #: Leave out co-authors of co-authors too, not only co-authors (CN-07).
    outside_network: bool = False

    def key(self) -> str:
        raw = json.dumps(
            {
                "slots": [(s["facet"], s["text"].casefold()) for s in self.slots],
                "lanes": sorted(self.lanes),
                "scope": self.scope,
                "outside_network": self.outside_network,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()


def _with_vectors(slots: list[dict]) -> list[dict]:
    """Every matchable slot with a vector, embedded now if it has none."""
    slots = [dict(s) for s in slots if s.get("text")]
    wanted = [s for s in slots if s["facet"] != SlotFacet.ROLE and not s.get("vector")]
    if wanted:
        vectors = embed_texts([s["text"] for s in wanted]) or []
        for slot, vector in zip(wanted, vectors, strict=False):
            slot["vector"] = [float(v) for v in vector]
    return slots


def _fields_of(users) -> frozenset[str]:
    return frozenset(w.field for w in discoverable_works(users) if w.field)


def query_for_call(seeker, call, **options) -> Query:
    row = RequirementSlots.objects.filter(content=call).first()
    slots = list(row.slots) if row else []
    return Query(
        "call", _with_vectors(slots), need_fields=_fields_of([seeker]), **options
    )


#: A project's declared relation, as the slot facet it asks for.
_PROJECT_FACETS = {
    "works_on": SlotFacet.PROBLEM,
    "uses_method": SlotFacet.METHOD,
    "works_in_setting": SlotFacet.DATA,
    "needs": SlotFacet.METHOD,
}


def query_for_project(seeker, project, **options) -> Query:
    """A project's stated state as slots — read only through the viewer's own
    access to the project, and never written anywhere shared (design §9.2)."""
    from apps.knowledge.read import project_edges

    edges = project_edges(project, seeker)
    if not edges and not project_visible(project, seeker):
        raise SearchRefused("you cannot see that project")
    slots = [
        {
            "facet": _PROJECT_FACETS[e.relation],
            "text": e.surface or e.label,
            "required": e.relation == "needs",
        }
        for e in edges
        if e.relation in _PROJECT_FACETS
    ]
    people = list(project.members.all()) or [seeker]
    return Query(
        "project", _with_vectors(slots), need_fields=_fields_of(people), **options
    )


def project_visible(project, viewer) -> bool:
    from apps.research.models import Project

    return Project.objects.visible_to(viewer).filter(pk=project.pk).exists()


def query_for_text(seeker, text: str, *, complete=None, **options) -> Query:
    """The seeker's own words, read by the same slot reader as a call."""
    from . import slots as slot_reader

    class _Typed:
        pk = None
        metadata = {"title": "", "description": text}

    outcome = slot_reader.extract(
        _Typed(), complete=complete, min_words=slot_reader.MIN_NEED_WORDS
    )
    found = outcome.slots if outcome else []
    return Query(
        "manual", _with_vectors(found), need_fields=_fields_of([seeker]), **options
    )


# --- the gate ---------------------------------------------------------------


def _labs_by_user(user_ids) -> dict[int, set[int]]:
    from apps.accounts.models import LabMembership

    out: dict[int, set[int]] = defaultdict(set)
    for user_id, lab_id in LabMembership.objects.filter(
        user_id__in=list(user_ids)
    ).values_list("user_id", "lab_id"):
        out[user_id].add(lab_id)
    return out


def _coauthors_by_user(user_ids) -> dict[int, set[str]]:
    from apps.accounts.models import AuthorWork

    out: dict[int, set[str]] = defaultdict(set)
    for user_id, ids in AuthorWork.objects.filter(
        user_id__in=list(user_ids)
    ).values_list("user_id", "coauthor_ids"):
        out[user_id].update(str(i) for i in ids or [])
    return out


def eligible_candidates(
    seeker, scope: str, now=None, *, outside_network: bool = False
) -> list:
    """Everyone the gate lets this seeker see, before any matching.

    Open and not expired; mutually visible on verified affiliations; not the
    seeker, not a lab-mate, not an existing co-author; under the appearance
    cap. Every condition is re-checked on every search — nothing about who is
    findable is cached (plan CN-04). ``outside_network`` also leaves out
    everyone within two co-authorships of the seeker (plan CN-07).
    """
    now = now or timezone.now()
    seeker_place = consent.place_of(seeker)
    if seeker_place is None:
        return []
    settings_rows = list(
        CollaborationSetting.objects.filter(open=True, expires_at__gt=now)
        .exclude(user=seeker)
        .select_related("user", "user__profile", "user__verified_affiliation")
    )
    ids = [row.user_id for row in settings_rows] + [seeker.pk]
    labs = _labs_by_user(ids)
    coauthors = _coauthors_by_user(ids)
    seeker_openalex = getattr(seeker.profile, "openalex_id", "") or ""
    network = network_of(seeker.pk, hops=2) if outside_network else set()
    out = []
    for setting in settings_rows:
        candidate = setting.user
        if candidate.pk in network:
            continue
        place = consent.stored_place(candidate)
        if not consent.mutually_visible(place, setting.audience, seeker_place, scope):
            continue
        if labs[seeker.pk] & labs[candidate.pk]:
            continue  # a lab-mate belongs in the team-fit line, not here
        their_id = getattr(candidate.profile, "openalex_id", "") or ""
        if (their_id and their_id in coauthors[seeker.pk]) or (
            seeker_openalex and seeker_openalex in coauthors[candidate.pk]
        ):
            continue  # they already work together
        if not consent.may_appear(candidate, seeker, now):
            continue
        out.append(candidate)
    return out


# --- lanes ------------------------------------------------------------------


@dataclass
class Hit:
    user_id: int
    lane: str
    score: float
    slot: str  # the query slot it answers
    facet: str  # which of their facets matched
    matched: str  # their own words for it
    tier: str  # "demonstrated" | "declared"
    year: int | None = None


def _unit(vector) -> np.ndarray | None:
    if not vector:
        return None
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    return array / norm if norm else None


def _sim(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return -1.0
    return float(a @ b)


def _recency(year: int | None, now) -> float:
    if not year:
        return 0.9
    return max(0.7, 1.0 - 0.03 * max(0, now.year - year))


def _add(hits, work, recency, lane, slot, facet, matched, score) -> None:
    hits.append(
        Hit(
            work.user_id,
            lane,
            score * recency,
            slot["text"],
            facet,
            matched,
            "demonstrated",
            work.year,
        )
    )


def _work_hits(query: Query, works: list[WorkView], gaps, covered, now) -> list[Hit]:
    match = settings.COLLAB_LANE_MATCH_COSINE
    differ = settings.COLLAB_LANE_DIFFER_COSINE
    method_slots = [s for s in query.slots if s["facet"] == SlotFacet.METHOD]
    hits: list[Hit] = []
    for work in works:
        v = {name: _unit(vec) for name, vec in work.vectors.items()}
        other_field = bool(work.field) and work.field not in query.need_fields
        same_field = not work.field or work.field in query.need_fields
        recency = _recency(work.year, now)

        for slot in gaps:
            sv = _unit(slot.get("vector"))
            if (
                slot["facet"] == SlotFacet.METHOD
                and Lane.METHOD_BRIDGE in query.lanes
                and other_field
            ):
                score = max(
                    _sim(sv, v.get("method")), _sim(sv, v.get("method_neutral"))
                )
                if score >= match:
                    _add(
                        hits,
                        work,
                        recency,
                        Lane.METHOD_BRIDGE,
                        slot,
                        "method",
                        work.method or work.method_neutral,
                        score,
                    )
            if (
                slot["facet"] == SlotFacet.PROBLEM
                and Lane.PROBLEM_BRIDGE in query.lanes
                and other_field
            ):
                score = _sim(sv, v.get("problem"))
                method_overlap = max(
                    (
                        _sim(_unit(m.get("vector")), v.get("method"))
                        for m in method_slots
                    ),
                    default=-1.0,
                )
                if score >= match and method_overlap < differ:
                    _add(
                        hits,
                        work,
                        recency,
                        Lane.PROBLEM_BRIDGE,
                        slot,
                        "problem",
                        work.problem,
                        score,
                    )
            if slot["facet"] == SlotFacet.DATA and Lane.RESOURCE in query.lanes:
                score = _sim(sv, v.get("reusable"))
                if score >= match:
                    _add(
                        hits,
                        work,
                        recency,
                        Lane.RESOURCE,
                        slot,
                        "reusable",
                        work.reusable,
                        score,
                    )
        if Lane.IN_FIELD in query.lanes and same_field:
            problems = [s for s in covered if s["facet"] == SlotFacet.PROBLEM]
            data = [s for s in query.slots if s["facet"] == SlotFacet.DATA]
            for slot in problems:
                score = _sim(_unit(slot.get("vector")), v.get("problem"))
                if data:
                    setting = max(
                        _sim(_unit(d.get("vector")), v.get("setting")) for d in data
                    )
                    if setting < match - 0.1:
                        continue
                    score = (score + setting) / 2
                if score >= match:
                    _add(
                        hits,
                        work,
                        recency,
                        Lane.IN_FIELD,
                        slot,
                        "problem",
                        work.problem,
                        score,
                    )
    return hits


#: Which of a person's concept relations can answer which lane, per tier.
_METHOD_RELATIONS = {"uses_method", "can_do"}
_TIER_WEIGHT = {"demonstrated": 1.0, "declared": 0.9}


def _concept_hits(
    query: Query, candidates, gaps, covered, field_of: dict[int, set]
) -> list[Hit]:
    """Lanes answered by the concepts a person holds — the short terms their
    papers were linked to (demonstrated) and what their profile states
    (declared, ranked slightly below, design §5.4). Sharper than whole facet
    sentences: a slot that says "kriging" meets a concept called "kriging".
    Each concept is matched on its own; nothing is averaged.

    A concept is a short phrase, and short phrases for *different* methods
    sit close together in the embedding space ("finite element analysis" and
    "image processing" meet at 0.70), so concepts match at their own, higher
    threshold, ``COLLAB_CONCEPT_MATCH_COSINE`` — the bar coverage uses for the
    same slot-against-concept comparison (EXP-2026-09-010's smoke run)."""
    match = settings.COLLAB_CONCEPT_MATCH_COSINE
    differ = settings.COLLAB_LANE_DIFFER_COSINE
    edges = [
        e
        for e in discoverable_edges(candidates)
        if e.tier in _TIER_WEIGHT and e.status == "active"
    ]
    vectors = {
        k: _unit(v) for k, v in concept_vectors({e.concept_id for e in edges}).items()
    }
    method_slots = [
        _unit(s.get("vector")) for s in query.slots if s["facet"] == SlotFacet.METHOD
    ]
    methods_of: dict[int, list] = defaultdict(list)
    for e in edges:
        if e.relation in _METHOD_RELATIONS:
            methods_of[e.user_id].append(vectors.get(e.concept_id))
    hits = []

    def add(edge, lane, slot, facet, score):
        hits.append(
            Hit(
                edge.user_id,
                lane,
                score * _TIER_WEIGHT[edge.tier],
                slot["text"],
                facet,
                edge.surface or edge.label,
                edge.tier,
            )
        )

    for edge in edges:
        fields = field_of.get(edge.user_id) or set()
        other_field = bool(fields) and not (fields & query.need_fields)
        same_field = not fields or bool(fields & query.need_fields)
        cv = vectors.get(edge.concept_id)
        for slot in gaps:
            sv = _unit(slot.get("vector"))
            score = _sim(sv, cv)
            if score < match:
                continue
            if (
                slot["facet"] == SlotFacet.METHOD
                and edge.relation in _METHOD_RELATIONS | {"interested_in"}
                and Lane.METHOD_BRIDGE in query.lanes
                and other_field
            ):
                add(edge, Lane.METHOD_BRIDGE, slot, "method", score)
            elif (
                slot["facet"] == SlotFacet.PROBLEM
                and edge.relation == "works_on"
                and Lane.PROBLEM_BRIDGE in query.lanes
                and other_field
            ):
                overlap = max(
                    (
                        _sim(m, their)
                        for m in method_slots
                        for their in methods_of[edge.user_id]
                    ),
                    default=-1.0,
                )
                if overlap < differ:
                    add(edge, Lane.PROBLEM_BRIDGE, slot, "problem", score)
            elif (
                slot["facet"] == SlotFacet.DATA
                and edge.relation == "offers"
                and Lane.RESOURCE in query.lanes
            ):
                add(edge, Lane.RESOURCE, slot, "reusable", score)
        if Lane.IN_FIELD in query.lanes and same_field and edge.relation == "works_on":
            for slot in covered:
                if slot["facet"] != SlotFacet.PROBLEM:
                    continue
                score = _sim(_unit(slot.get("vector")), cv)
                if score >= match:
                    add(edge, Lane.IN_FIELD, slot, "problem", score)
    return hits


def _slot_rounds(hits: list[Hit], k: int) -> list[Hit]:
    """Up to ``k`` people for one lane, filled slot by slot.

    The best person for each slot first (slots ordered by their best score),
    then each slot's second best, and so on; nobody twice. A lane's places are
    shared by every slot of the need, and ranking across slots gave a project
    that needs three methods three people for its easiest one
    (EXP-2026-09-008 arm A: hit rate 0.46 at precision 0.98).
    """
    best: dict[tuple[str, int], Hit] = {}
    for h in hits:
        key = (h.slot, h.user_id)
        if key not in best or h.score > best[key].score:
            best[key] = h
    by_slot: dict[str, list[Hit]] = defaultdict(list)
    for h in best.values():
        by_slot[h.slot].append(h)
    queues = sorted(
        (sorted(v, key=lambda h: (-h.score, h.user_id)) for v in by_slot.values()),
        key=lambda q: -q[0].score,
    )
    chosen: list[Hit] = []
    seen: set[int] = set()
    while len(chosen) < k and any(queues):
        for queue in queues:
            while queue and queue[0].user_id in seen:
                queue.pop(0)
            if queue and len(chosen) < k:
                h = queue.pop(0)
                chosen.append(h)
                seen.add(h.user_id)
    return chosen


def _by_lane(hits: list[Hit], k: int) -> dict[str, list[Hit]]:
    lanes: dict[str, list[Hit]] = defaultdict(list)
    for h in hits:
        lanes[h.lane].append(h)
    return {lane: _slot_rounds(v, k) for lane, v in lanes.items()}


# --- the rerank ---------------------------------------------------------------

RERANK_SYSTEM = (
    "You judge whether each shortlisted researcher could help with a stated "
    "research need, from the one piece of their work shown. You never add anyone "
    "and never invent facts about them. Reply with one JSON object only."
)

RERANK_PROMPT = """The need, as requirement slots:
{slots}

Lane: {lane_label}

Shortlisted researchers (id: the part of their work that matched):
{candidates}

For each id, decide keep or drop, and for kept ones write one short sentence
(at most 25 words) saying which part of their work answers which slot.
Reply as {{"verdicts": [{{"id": "c1", "keep": true, "reason": "..."}}]}}"""


def _rerank(
    query, lane, shortlist: list[Hit], complete
) -> tuple[list[Hit], dict[int, str], bool]:
    """Keep/drop and a reason per candidate. Never adds anyone."""
    if not shortlist:
        return [], {}, True
    ids = {f"c{i + 1}": h for i, h in enumerate(shortlist)}
    prompt = RERANK_PROMPT.format(
        slots="\n".join(
            f"- [{s['facet']}] {s['text']}"
            for s in query.slots
            if s["facet"] != SlotFacet.ROLE
        ),
        lane_label=Lane(lane).label,
        candidates="\n".join(
            f"{key}: ({h.facet}) {h.matched[:300]}" for key, h in ids.items()
        ),
    )
    try:
        raw = complete(RERANK_SYSTEM, prompt) or ""
        start = raw.find("{")
        if start < 0:
            raise ValueError("no JSON object in the reply")
        # The first object only: a model that adds a second block or a
        # sentence after its answer must not void the whole lane.
        answer, _ = json.JSONDecoder().raw_decode(raw[start:])
        verdicts = answer.get("verdicts") or []
    except Exception as exc:  # noqa: BLE001 - the lane stands unexplained
        logger.warning("collab rerank unavailable (%s)", exc)
        return shortlist, {}, False
    kept: list[Hit] = []
    reasons: dict[int, str] = {}
    decided = {}
    for verdict in verdicts if isinstance(verdicts, list) else []:
        key = str((verdict or {}).get("id") or "")
        if key in ids:  # a name that was not shortlisted is discarded
            decided[key] = verdict
    for key, h in ids.items():
        verdict = decided.get(key)
        if verdict is not None and verdict.get("keep") is False:
            continue
        kept.append(h)
        if verdict is not None:
            reasons[h.user_id] = " ".join(str(verdict.get("reason") or "").split())[
                :240
            ]
    return kept, reasons, True


def _default_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    return (
        build_llm_client(component=COMPONENT)
        .complete([LLMMessage("system", system), LLMMessage("user", user)])
        .content
    )


# --- the search -------------------------------------------------------------


@dataclass
class SearchResult:
    lanes: dict[str, list[dict]] = field(default_factory=dict)
    explained: bool = True
    candidates_considered: int = 0
    search_id: int | None = None

    def groups(self) -> dict[str, list[dict]]:
        return {
            "fills_a_gap": [r for lane in GAP_LANES for r in self.lanes.get(lane, [])],
            "shares_expertise": list(self.lanes.get(Lane.IN_FIELD, [])),
        }

    def as_dict(self) -> dict:
        return {
            "lanes": self.lanes,
            "groups": self.groups(),
            "explained": self.explained,
            "search_id": self.search_id,
        }


def _allowed_scope(scope: str) -> None:
    order = [Audience.INSTITUTION, Audience.COUNTRY, Audience.ANYWHERE]
    if scope not in order:
        raise SearchRefused(f"unknown scope {scope!r}")
    if order.index(scope) > order.index(settings.COLLAB_MAX_SCOPE):
        raise SearchRefused(
            f"searches reach at most {settings.COLLAB_MAX_SCOPE} for now"
        )


def _split(seeker, query: Query) -> tuple[list[dict], list[dict]]:
    """The query's matchable slots as (what the seeker covers, the gaps).

    What the seeker already has is what the in-field lane shares; the rest is
    what the bridges — and a team — must fill."""
    own = [e for e in own_edges(seeker) if e.status == "active"]
    row = RequirementSlots(content_id=None, slots=query.slots, status="ok")
    fit = assess(row, own=own)
    covered_texts = {s.text for s in fit.slots if s.covered_by == YOU}
    matchable = [s for s in query.slots if s["facet"] != SlotFacet.ROLE]
    return (
        [s for s in matchable if s["text"] in covered_texts],
        [s for s in matchable if s["text"] not in covered_texts],
    )


def check_seeker(seeker, now=None) -> None:
    """Refuse a seeker who may not search: unverified, over the daily limit, or
    on a free plan while plans are enforced (plan CN-04, OD-CN5)."""
    from apps.billing.entitlements import effective_tier, enforcing
    from apps.billing.models import Tier

    if consent.place_of(seeker) is None:
        raise SearchRefused("verify your email to search", "unverified")
    if enforcing() and effective_tier(seeker) == Tier.FREE:
        raise SearchRefused(
            "searching for collaborators is part of a paid plan", "paid_plan"
        )
    since = (now or timezone.now()) - timedelta(days=1)
    if (
        SearchLog.objects.filter(seeker=seeker, created_at__gte=since).count()
        >= settings.COLLAB_SEARCHES_PER_DAY
    ):
        raise SearchRefused("that is today's limit of searches", "daily_limit")


def search(
    seeker, query: Query, *, complete: CompleteFn | None = None, now=None
) -> SearchResult:
    """Run one search. Refusals raise :class:`SearchRefused` before anything
    is read, matched or recorded."""
    now = now or timezone.now()
    _allowed_scope(query.scope)
    check_seeker(seeker, now)

    cached = (
        SearchLog.objects.filter(
            seeker=seeker,
            query_hash=query.key(),
            created_at__gte=now - timedelta(days=1),
        )
        .exclude(cached={})
        .first()
    )
    if cached is not None:
        # The model's work is reused; who may be shown is not. Everyone in the
        # cached answer passes the gate again, so a person who turned the
        # setting off since is gone from it at once.
        allowed = {
            c.get_username()
            for c in eligible_candidates(
                seeker, query.scope, now, outside_network=query.outside_network
            )
        }
        lanes = {
            lane: [row for row in rows if row["username"] in allowed]
            for lane, rows in cached.cached.get("lanes", {}).items()
        }
        return SearchResult(
            lanes=lanes,
            explained=cached.cached.get("explained", True),
            search_id=cached.pk,
        )

    covered, gaps = _split(seeker, query)
    if not covered:
        covered = [s for s in query.slots if s["facet"] == SlotFacet.PROBLEM]

    candidates = eligible_candidates(
        seeker, query.scope, now, outside_network=query.outside_network
    )
    result = SearchResult(candidates_considered=len(candidates))
    by_id = {c.pk: c for c in candidates}
    works = discoverable_works(candidates)
    field_of: dict[int, set] = defaultdict(set)
    for w in works:
        if w.field:
            field_of[w.user_id].add(w.field)
    hits = _work_hits(query, works, gaps, covered, now)
    hits += _concept_hits(query, candidates, gaps, covered, field_of)
    ranked = _by_lane(hits, settings.COLLAB_SHORTLIST_PER_LANE)

    ask = complete if complete is not None else _default_complete
    shown: set[int] = set()
    places = {c.pk: getattr(c, "verified_affiliation", None) for c in candidates}
    for lane in query.lanes:
        shortlist = ranked.get(lane, [])[: settings.COLLAB_SHORTLIST_PER_LANE]
        kept, reasons, explained = _rerank(query, lane, shortlist, ask)
        result.explained = result.explained and explained
        rows = []
        for h in kept[: settings.COLLAB_RESULTS_PER_LANE]:
            person = by_id[h.user_id]
            place = places.get(h.user_id)
            rows.append(
                {
                    "username": person.get_username(),
                    "name": display_name(person),
                    "institution": place.institution if place else "",
                    "lane": lane,
                    "slot": h.slot,
                    "facet": h.facet,
                    "matched": h.matched,
                    "tier": h.tier,
                    "reason": reasons.get(h.user_id, ""),
                }
            )
            shown.add(h.user_id)
        result.lanes[lane] = rows

    with transaction.atomic():
        for user_id in shown:
            consent.record_appearance(by_id[user_id], seeker, now)
        log = SearchLog.objects.create(
            seeker=seeker,
            entry=query.entry,
            slots=[{"facet": s["facet"], "text": s["text"]} for s in query.slots],
            lanes=list(query.lanes),
            scope=query.scope,
            query_hash=query.key(),
            results=sum(len(v) for v in result.lanes.values()),
            cached={"lanes": result.lanes, "explained": result.explained},
        )
    result.search_id = log.pk
    return result


# --- introductions (plan CN-07) ----------------------------------------------


def introduce(seeker, search_id: int, username: str, now=None) -> dict:
    """ "Who can introduce me?" — the shortest co-authorship chain from the
    seeker to someone a search of theirs returned.

    Only for a person that search showed, who still passes the gate. Every
    intermediary named is open to collaboration now, with an audience that
    includes the seeker, and under the appearance cap — being named on a path
    is being shown, so it is recorded as an appearance. Nobody else is ever
    named; if the only chains run through people who have not opted in, the
    answer is that there is no path.
    """
    now = now or timezone.now()
    log = SearchLog.objects.filter(pk=search_id, seeker=seeker).first()
    if log is None:
        raise SearchRefused("no such search", "not_found")
    shown = {
        row["username"]
        for rows in (log.cached or {}).get("lanes", {}).values()
        for row in rows
    } | {row["username"] for row in (log.cached or {}).get("team", [])}
    if username not in shown:
        raise SearchRefused("that person was not in this search", "not_found")
    target = next(
        (
            c
            for c in eligible_candidates(seeker, log.scope, now)
            if c.get_username() == username
        ),
        None,
    )
    if target is None:
        raise SearchRefused("that person is no longer open to you", "not_found")
    seeker_place = consent.place_of(seeker)
    through = []
    for setting in CollaborationSetting.objects.filter(
        open=True, expires_at__gt=now
    ).select_related("user", "user__verified_affiliation"):
        person = setting.user
        if person.pk in (seeker.pk, target.pk):
            continue
        if not consent.within(
            consent.stored_place(person), seeker_place, setting.audience
        ):
            continue
        if not consent.may_appear(person, seeker, now):
            continue
        through.append(person)
    by_id = {p.pk: p for p in through}
    path = introduction_paths(
        seeker.pk, [target.pk], by_id, max_hops=settings.COLLAB_INTRO_MAX_HOPS
    ).get(target.pk)
    if not path:
        return {"path": None, "hops": None}
    middle = [by_id[pk] for pk in path[1:-1]]
    with transaction.atomic():
        for person in middle:
            consent.record_appearance(person, seeker, now)
    return {
        "hops": len(path) - 1,
        "path": [
            {
                "username": person.get_username(),
                "name": display_name(person),
                "institution": getattr(
                    getattr(person, "verified_affiliation", None), "institution", ""
                ),
            }
            for person in middle
        ],
    }


# --- team formation (plan CN-07) ---------------------------------------------


@dataclass
class TeamResult:
    team: list[dict] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    search_id: int | None = None

    def as_dict(self) -> dict:
        return {
            "team": self.team,
            "uncovered": self.uncovered,
            "search_id": self.search_id,
        }


#: A person further than this from everyone chosen counts as this far.
_FAR = 4


def assemble_team(seeker, query: Query, *, now=None) -> TeamResult:
    """A small set of people who together cover every gap in the need.

    Greedy set cover with a distance penalty (the team formation problem): at
    each step, the person whose match scores over the still-uncovered gaps,
    less ``COLLAB_TEAM_DISTANCE_WEIGHT`` times their mean co-authorship
    distance to the seeker and those already chosen, is added. Everyone
    considered comes through :func:`eligible_candidates`, so each member passes
    the gate alone; a gap nobody eligible covers is reported, never filled.
    Deterministic: no model is asked, and each member's line is their own
    words for what they cover.
    """
    now = now or timezone.now()
    _allowed_scope(query.scope)
    check_seeker(seeker, now)
    _, gaps = _split(seeker, query)
    if len(gaps) < settings.COLLAB_TEAM_MIN_GAPS:
        raise SearchRefused(
            f"a team is proposed for {settings.COLLAB_TEAM_MIN_GAPS} or more gaps",
            "too_few_gaps",
        )
    candidates = eligible_candidates(
        seeker, query.scope, now, outside_network=query.outside_network
    )
    by_id = {c.pk: c for c in candidates}
    works = discoverable_works(candidates)
    field_of: dict[int, set] = defaultdict(set)
    for w in works:
        if w.field:
            field_of[w.user_id].add(w.field)
    # Any field may fill a gap in a team, so the bridge lanes run with no
    # "home" field: the lane rules still decide what counts as covering.
    open_query = Query(query.entry, query.slots, lanes=GAP_LANES, scope=query.scope)
    hits = _work_hits(open_query, works, gaps, [], now)
    hits += _concept_hits(open_query, candidates, gaps, [], field_of)
    cover: dict[str, dict[int, Hit]] = defaultdict(dict)
    for h in hits:
        best = cover[h.slot].get(h.user_id)
        if best is None or h.score > best.score:
            cover[h.slot][h.user_id] = h

    distances = {seeker.pk: coauthor_distances(seeker.pk, _FAR - 1)}
    chosen: list[int] = []
    uncovered = [s["text"] for s in gaps]
    weight = settings.COLLAB_TEAM_DISTANCE_WEIGHT
    while uncovered and len(chosen) < settings.COLLAB_TEAM_MAX_SIZE:
        best_value, best_id = None, None
        people = sorted(
            {uid for text in uncovered for uid in cover.get(text, {})} - set(chosen)
        )
        for uid in people:
            gain = sum(
                cover[text][uid].score for text in uncovered if uid in cover[text]
            )
            dist = sum(d.get(uid, _FAR) for d in distances.values()) / len(distances)
            value = gain - weight * dist
            if best_value is None or value > best_value:
                best_value, best_id = value, uid
        if best_id is None:
            break
        chosen.append(best_id)
        distances[best_id] = coauthor_distances(best_id, _FAR - 1)
        uncovered = [t for t in uncovered if best_id not in cover.get(t, {})]

    result = TeamResult(uncovered=uncovered)
    for uid in chosen:
        person = by_id[uid]
        place = getattr(person, "verified_affiliation", None)
        result.team.append(
            {
                "username": person.get_username(),
                "name": display_name(person),
                "institution": place.institution if place else "",
                "covers": [
                    {
                        "slot": text,
                        "facet": cover[text][uid].facet,
                        "matched": cover[text][uid].matched,
                        "tier": cover[text][uid].tier,
                    }
                    for text in (s["text"] for s in gaps)
                    if uid in cover.get(text, {})
                ],
                "distance": distances[seeker.pk].get(uid),
            }
        )
    with transaction.atomic():
        for uid in chosen:
            consent.record_appearance(by_id[uid], seeker, now)
        log = SearchLog.objects.create(
            seeker=seeker,
            entry=query.entry,
            slots=[{"facet": s["facet"], "text": s["text"]} for s in query.slots],
            lanes=["team"],
            scope=query.scope,
            # Its own hash, so a search for the same need never reads a team
            # back from the day's cache as if it were lanes.
            query_hash=hashlib.sha256(f"team:{query.key()}".encode()).hexdigest(),
            results=len(chosen),
            cached={"team": result.team},
        )
    result.search_id = log.pk
    return result


def prune_logs(now=None) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=90)
    return SearchLog.objects.filter(created_at__lt=cutoff).delete()[0]


User = get_user_model()
