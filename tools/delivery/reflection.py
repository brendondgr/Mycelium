"""What Mylo noticed about how the reader actually behaved this week.

A weekly that only reports the corpus is a weekly that never gets better. What a
reader *did* — four saves on one topic, six dismissals sharing a word, a venue
Mylo could not judge because no milestone is dated — is the most reliable signal
in the product about whether the project state is still true, and it is free.

**The rules are deterministic and the model only phrases them** (plan 7.2). That
is the whole design. A model deciding on its own that a project's method has
changed and writing it into the state is precisely the failure invariant 9 exists
to prevent: the reader would find their own words replaced by a machine's, in the
one document they are supposed to be able to trust because they wrote it.

So each rule is a count with a threshold, each proposal is a concrete edit in the
shape a state PATCH would take, and every one of them is **accepted or rejected
by a person**. Nothing here writes to :class:`~apps.research.models.ProjectState`.

Four rules, and the reason for each:

``add_method``
    Repeated saves whose titles share a term the project's method does not name.
    A reader saving four papers on confidence estimation is telling you something
    the project description has not caught up with.
``add_exclusion``
    Repeated dismissals sharing a term. This is the rule that pays for itself:
    the reader is doing filtering work the system should be doing, and the
    proposal is Mylo admitting it got something wrong.
``set_milestone``
    Timeline rows Mylo declined to judge because the milestone they hang on has
    no date. The proposal is "give me a date and I can answer this", which is a
    more useful thing to say than a guessed verdict.
``review_state``
    The state has not been confirmed in over thirty days. Stale state is the most
    dangerous input the reports have, because it reads as current.

A proposal expires after 14 days and is not re-proposed for a further 28, so
declining one is a decision the system respects rather than a question it asks
again next Monday.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from tools.delivery.models import ReflectionProposal

#: Days a pending proposal stands before it lapses.
EXPIRES_AFTER_DAYS = 14
#: Days after a decision before the same proposal may be raised again. Longer
#: than the expiry on purpose: "no" should cost more to overturn than silence.
COOLDOWN_DAYS = 28

#: How many saves or dismissals must share a term before it is a pattern rather
#: than a coincidence. Three is the smallest number that is not two.
MIN_SAVES_FOR_METHOD = 3
MIN_DISMISSALS_FOR_EXCLUSION = 4

#: Confirmations older than this are worth asking about.
STALE_STATE_DAYS = 30

_WORD = re.compile(r"[a-z][a-z0-9-]{3,}")
_STOP = frozenset(
    "with from that this into over under using used based toward towards "
    "their there which while when what have been were will more most other "
    "some such than then they them also only very much many both each".split()
)


@dataclass
class Proposal:
    """One proposed change, before it is written down."""

    project_id: str
    kind: str
    #: The change, in the shape a state PATCH would take.
    proposal: dict = field(default_factory=dict)
    #: What the reader did that produced it — counts, the shared term.
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "project": self.project_id,
            "kind": self.kind,
            "proposal": self.proposal,
            "evidence": self.evidence,
        }


def terms(titles: Iterable[str]) -> dict[str, int]:
    """``{term: how many titles used it}`` — the crudest possible topic signal.

    Crude deliberately. The proposal it produces is read by a person who can see
    the papers it came from, and a sophisticated extraction that occasionally
    proposes something inexplicable is worse than a simple one whose mistakes are
    obvious.
    """
    counts: dict[str, int] = {}
    for title in titles:
        seen = {
            word
            for word in _WORD.findall((title or "").casefold())
            if word not in _STOP
        }
        for word in seen:
            counts[word] = counts.get(word, 0) + 1
    return counts


def _best_term(counts: dict[str, int]) -> str:
    """The term worth proposing, out of several that cleared the threshold.

    Most frequent first, then **longest**. The length tie-break is the one that
    matters: four papers titled "Federated learning for task N" make "federated",
    "learning" and "task" all equally frequent, and excluding "task" would
    suppress an enormous amount the reader never objected to. A more specific
    term is a safer proposal, and length is the crudest honest proxy for
    specificity.
    """
    return max(counts, key=lambda term: (counts[term], len(term), term))


def _known(state_slow: dict, state_fast: dict) -> set[str]:
    """Every term the project already names, so a proposal is never a repeat."""
    text = " ".join(
        [
            *(state_slow.get("method") or []),
            *(state_slow.get("data") or []),
            *(state_slow.get("planned_components") or []),
            *(state_fast.get("exclusions") or []),
            str(state_slow.get("claimed_contribution") or ""),
        ]
    ).casefold()
    return set(_WORD.findall(text))


def method_proposal(project, saved_titles: list[str]) -> Proposal | None:
    """Repeated saves on a term the project's method does not name."""
    state = getattr(project, "state", None)
    slow = getattr(state, "slow", None) or {}
    fast = getattr(state, "fast", None) or {}
    known = _known(slow, fast)
    counts = {
        term: count
        for term, count in terms(saved_titles).items()
        if count >= MIN_SAVES_FOR_METHOD and term not in known
    }
    if not counts:
        return None
    term = _best_term(counts)
    return Proposal(
        project_id=str(project.id),
        kind=ReflectionProposal.Kind.ADD_METHOD,
        proposal={"slow": {"method": [*(slow.get("method") or []), term]}},
        evidence={"saved": counts[term], "shared_term": term},
    )


def exclusion_proposal(project, dismissed_titles: list[str]) -> Proposal | None:
    """Repeated dismissals sharing a term — Mylo admitting it got something wrong."""
    state = getattr(project, "state", None)
    slow = getattr(state, "slow", None) or {}
    fast = getattr(state, "fast", None) or {}
    known = _known(slow, fast)
    counts = {
        term: count
        for term, count in terms(dismissed_titles).items()
        if count >= MIN_DISMISSALS_FOR_EXCLUSION and term not in known
    }
    if not counts:
        return None
    term = _best_term(counts)
    return Proposal(
        project_id=str(project.id),
        kind=ReflectionProposal.Kind.ADD_EXCLUSION,
        proposal={"fast": {"exclusions": [*(fast.get("exclusions") or []), term]}},
        evidence={"dismissed": counts[term], "shared_term": term},
    )


def milestone_proposal(project, timeline_rows: list[dict]) -> Proposal | None:
    """Venues Mylo declined to judge for want of a dated milestone.

    "Give me a date and I can answer this" is a more useful thing to say than a
    guessed verdict, and it is the only honest one.
    """
    blocked = [
        row for row in timeline_rows if row.get("status") == "no_milestone"
    ]
    if not blocked:
        return None
    return Proposal(
        project_id=str(project.id),
        kind=ReflectionProposal.Kind.SET_MILESTONE,
        proposal={"fast": {"milestones": []}},
        evidence={
            "unjudged": len(blocked),
            "venues": [row.get("venue", "") for row in blocked[:3]],
        },
    )


def review_proposal(project, *, today: date) -> Proposal | None:
    """State nobody has confirmed in a month, which reads as current and is not.

    Never-confirmed counts. A project whose state was imported, extracted from a
    document, or written before confirmation existed has never had a person say
    it is right, and the reports are quoting it as though somebody had.
    """
    state = getattr(project, "state", None)
    if state is None or getattr(state, "is_empty", True):
        return None
    days = state.days_since_confirmed(today)
    if days is not None and days <= STALE_STATE_DAYS:
        return None
    return Proposal(
        project_id=str(project.id),
        kind=ReflectionProposal.Kind.REVIEW_STATE,
        proposal={},
        evidence={"days_since_confirmed": days},
    )


def propose_for_project(
    project, *, saved_titles: list[str], dismissed_titles: list[str],
    timeline_rows: list[dict], today: date,
) -> list[Proposal]:
    """Every rule that fires for one project, in the order the weekly shows them."""
    found = [
        method_proposal(project, saved_titles),
        exclusion_proposal(project, dismissed_titles),
        milestone_proposal(project, timeline_rows),
        review_proposal(project, today=today),
    ]
    return [proposal for proposal in found if proposal is not None]


def persist(
    proposals: list[Proposal], target_filter: dict, *, today: date | None = None
) -> int:
    """Write the ones that are not already pending or recently declined.

    Returns how many were new. A proposal the reader rejected is not raised again
    for :data:`COOLDOWN_DAYS`, because asking again next Monday is how a system
    teaches people to ignore it.
    """
    from apps.research.models import Project

    today = today or timezone.localdate()
    made = 0
    for proposal in proposals:
        recent = ReflectionProposal.objects.filter(
            **target_filter,
            project_id=proposal.project_id,
            kind=proposal.kind,
        ).order_by("-created_at").first()
        if recent is not None:
            if recent.status == ReflectionProposal.Status.PENDING:
                continue
            if (today - recent.created_at.date()).days < COOLDOWN_DAYS:
                continue
        project = Project.objects.filter(pk=proposal.project_id).first()
        if project is None:  # pragma: no cover - raced with a delete
            continue
        ReflectionProposal.objects.create(
            **target_filter,
            project=project,
            kind=proposal.kind,
            proposal=proposal.proposal,
            evidence=proposal.evidence,
            expires_on=today + timedelta(days=EXPIRES_AFTER_DAYS),
        )
        made += 1
    return made


def expire_stale(today: date | None = None) -> int:
    """Lapse pending proposals past their date. Returns how many."""
    today = today or timezone.localdate()
    return ReflectionProposal.objects.filter(
        status=ReflectionProposal.Status.PENDING, expires_on__lt=today
    ).update(status=ReflectionProposal.Status.EXPIRED)


def reflection_block(proposals: list[ReflectionProposal]) -> str:
    """"Mylo's reflection" — the weekly's closing section, rendered by code.

    Phrased from the stored evidence rather than by the model, for the same
    reason the rules are deterministic: a proposal is a request to change what the
    reader wrote about their own work, and it has to say plainly what prompted it.
    """
    if not proposals:
        return ""
    lines = [
        "## Mylo's reflection",
        "",
        "**Proposed changes** (accept or reject on the web):",
    ]
    for index, row in enumerate(proposals, start=1):
        evidence = row.evidence or {}
        label = f"r{index} · {row.project.name}"
        if row.kind == ReflectionProposal.Kind.ADD_METHOD:
            lines.append(
                f"- **{label} method:** you saved {evidence.get('saved')} papers "
                f"sharing the term \"{evidence.get('shared_term')}\". Add it to "
                "this project's method?"
            )
        elif row.kind == ReflectionProposal.Kind.ADD_EXCLUSION:
            lines.append(
                f"- **{label} exclusion:** you dismissed "
                f"{evidence.get('dismissed')} items sharing the term "
                f"\"{evidence.get('shared_term')}\". Exclude it?"
            )
        elif row.kind == ReflectionProposal.Kind.SET_MILESTONE:
            venues = ", ".join(evidence.get("venues") or []) or "some venues"
            lines.append(
                f"- **{label} milestone:** Mylo could not judge {venues} because "
                "no milestone is dated. Set one?"
            )
        else:
            days = evidence.get("days_since_confirmed")
            when = f"{days} days ago" if days is not None else "never"
            lines.append(
                f"- **{label} review:** this project's state was last confirmed "
                f"{when}. Is it still right?"
            )
    return "\n".join(lines)
