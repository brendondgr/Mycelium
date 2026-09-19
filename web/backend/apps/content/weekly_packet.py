"""The closed evidence packet one weekly synthesis call is allowed to see.

The weekly is the one report where the model writes at length about a *project*
rather than about a topic, and that is exactly where a model will confabulate if
you let it. The defence is not a better prompt. It is that the prompt physically
cannot contain anything the verifier will not accept: every item is numbered,
every number resolves, every date and count is computed by a matcher, and the
verifier afterwards removes any sentence whose citation does not resolve or whose
number is not in the packet (plan H1/H2).

**Closed** means two things:

*Nothing outside it may be referenced.* The model is told to cite ``[P#]`` for
every factual sentence about an item, and a sentence citing ``[P9]`` in a packet
that stops at ``[P7]`` is removed rather than repaired — a citation to nothing is
worse than no citation, because it looks checked.

*Nothing in it may be seen by someone who should not see it* (plan H4). A packet
is built for one surface: a DM packet carries the reader's own projects including
private ones, a lab packet carries only shared projects and never fellowship
eligibility. The scope is recorded on the packet itself, so a packet cannot be
handed to the wrong renderer by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

#: How far ahead the weekly's deadline horizon looks. Ten weeks, because that is
#: roughly the planning horizon a full-paper submission needs: shorter and the
#: weekly stops being the place you notice a venue in time to act.
HORIZON_WEEKS = 10

#: Items per project in one packet. A synthesis call that has to weigh forty
#: papers writes about none of them; the cap is what keeps the prose specific.
ITEMS_PER_PROJECT = 8


@dataclass
class PacketItem:
    """One numbered item in a packet — everything a sentence may cite."""

    n: int
    content_id: str
    title: str
    url: str
    precis: dict = field(default_factory=dict)
    writeup: dict = field(default_factory=dict)
    #: ``[trigger]`` for anything this item raised for this project this week.
    matchers: list[str] = field(default_factory=list)
    #: What the reader did with it — the weekly reports status, not a rewrite.
    reader_signals: dict = field(default_factory=dict)
    #: Set when the item's text changed since the reader last saw it.
    revised_on: str = ""
    kind: str = "paper"
    source: str = ""

    def as_dict(self) -> dict:
        return {
            "id": f"P{self.n}",
            "title": self.title,
            "url": self.url,
            "kind": self.kind,
            "source": self.source,
            "precis": self.precis,
            "writeup": self.writeup,
            "matchers": list(self.matchers),
            "reader_signals": dict(self.reader_signals),
            **({"revised_on": self.revised_on} if self.revised_on else {}),
        }

    def as_reference(self) -> dict:
        return {
            "n": self.n,
            "title": self.title,
            "source": self.source,
            "kind": self.kind,
        }


@dataclass
class ProjectPacket:
    """One project's week, closed."""

    project_id: str
    label: str
    stage: str = ""
    state_slow: dict = field(default_factory=dict)
    state_fast: dict = field(default_factory=dict)
    days_since_confirmed: int | None = None
    items: list[PacketItem] = field(default_factory=list)
    timeline_rows: list[dict] = field(default_factory=list)
    team_gaps: list[dict] = field(default_factory=list)
    #: ``[{item, trigger, on}]`` — raised earlier this week, so the weekly
    #: reports what happened to it rather than raising it again (plan 6.6).
    already_alerted: list[dict] = field(default_factory=list)
    entered: int = 0
    left: int = 0
    #: ``[{id: "O#", what, on}]`` — this week's changes to the project that took
    #: effect (ambient Plan 09), citable as ``[O#]``.
    changes: list[dict] = field(default_factory=list)

    @property
    def is_quiet(self) -> bool:
        # Changes alone do not wake the model: they are in "What changed", and a
        # section with no item to tie them to could only restate them.
        return not self.items and not self.already_alerted

    def as_dict(self) -> dict:
        return {
            "project": self.label,
            "stage": self.stage,
            "state": {"slow": self.state_slow, "fast": self.state_fast},
            "days_since_confirmed": self.days_since_confirmed,
            "items": [item.as_dict() for item in self.items],
            "matcher_rows": {
                "timeline": self.timeline_rows,
                "team_gaps": self.team_gaps,
            },
            "already_alerted": list(self.already_alerted),
            "movement": {"entered": self.entered, "left": self.left},
            **({"changes": list(self.changes)} if self.changes else {}),
        }


@dataclass
class WeeklyPacket:
    """One week, one target, one surface."""

    packet_id: str
    #: ``dm`` or ``channel`` — which readers this packet's contents are safe for.
    surface: str
    week_start: date = field(default_factory=timezone.localdate)
    projects: list[ProjectPacket] = field(default_factory=list)
    personal: list[PacketItem] = field(default_factory=list)
    deadline_horizon: list[dict] = field(default_factory=list)
    engagement: dict = field(default_factory=dict)
    private_projects_hidden: int = 0
    #: "Mylo's reflection", already rendered. Deterministic rules phrased in code
    #: (:mod:`apps.content.reflection`) — the model is never asked to decide that
    #: a reader's own description of their work should change.
    reflection: str = ""
    #: This week's changes that took effect, numbered ``[O#]`` (ambient Plan 09,
    #: :mod:`apps.content.weekly_changes`). Rendered by code; the project ones
    #: also travel in each project's packet.
    changes: list[dict] = field(default_factory=list)
    #: Personal weekly only: questions answered by surface, the project the
    #: week's conversation went to, and conversation proposals waiting.
    answers: dict = field(default_factory=dict)
    attention_lead: str = ""
    proposals_waiting: int = 0
    #: What the report was written against (``understanding.context_version``).
    context_version: str = ""
    #: Who the packet is for (a user or a lab) — for the change rows' "you".
    reader: object = None

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=6)

    @property
    def all_items(self) -> list[PacketItem]:
        return [item for project in self.projects for item in project.items] + list(
            self.personal
        )

    def references(self) -> list[dict]:
        """The numbered references, in packet order — the code-rendered block."""
        return [item.as_reference() for item in sorted(self.all_items, key=_number)]

    def numbers(self) -> set[int]:
        """Every citation the verifier will accept."""
        return {item.n for item in self.all_items}

    def change_numbers(self) -> set[int]:
        """Every ``[O#]`` the verifier will accept."""
        return {row["n"] for row in self.changes}

    def as_dict(self) -> dict:
        return {
            "packet": self.packet_id,
            "scope": {"surface": self.surface},
            "week": [self.week_start.isoformat(), self.week_end.isoformat()],
            "projects": [project.as_dict() for project in self.projects],
            "personal": [item.as_dict() for item in self.personal],
            "deadline_horizon": list(self.deadline_horizon),
            "engagement": dict(self.engagement),
            "private_projects_hidden": self.private_projects_hidden,
            **(
                {"context_version": self.context_version}
                if self.context_version
                else {}
            ),
        }


def _number(item: PacketItem) -> int:
    return item.n
