"""How much runway a reader thinks they need — resolved from four places.

Two numbers decide whether Mylo calls a venue a fit:

**deadline buffer** (default 14 days) — the slack a reader wants between finishing
something and the deadline for it. A deadline 35 days after the milestone that
feeds it "fits"; one 3 days after is "tight" whatever the calendar says.

**minimum paper window** (default 60 days) — the fewest days they consider enough
to write a full paper from a standing start. Below it Mylo says *not viable*
rather than *tight*, which is a different sentence and a different decision.

Both are placeholders (plan D5). They are guesses about a person's working pace,
and a guess presented as a system constant is how a report starts being argued
with instead of used. So they are adjustable at every level the pace could
plausibly differ, resolved most-specific-first:

    project override → lab default (for a lab project) → user default → system

The reader matters as well as the project. A lab project appearing in two people's
personal reports is judged against each of their own buffers, because "can *I*
make this" is the question a personal report answers. Only the lab's own report
falls back to the lab's default, since it has no single reader.

Nothing here is cached: the whole point of the resolver is that changing a buffer
recomputes every timeline status with zero model calls (plan S10), and a cache
would be one more place for a setting to fail to take effect.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The system defaults, and the last resort. Named rather than inlined so a
#: surface can say "yours" versus "the default" without comparing to a literal.
SYSTEM_BUFFER_DAYS = 14
SYSTEM_WINDOW_DAYS = 60

#: Where a resolved setting came from, for the report's "buffer 14 (yours)" note.
#: A reader who disagrees with a verdict needs to know which dial to turn.
SOURCE_PROJECT = "project"
SOURCE_LAB = "lab"
SOURCE_USER = "you"
SOURCE_SYSTEM = "default"


@dataclass(frozen=True)
class Timeline:
    """One resolved pair, with where each half came from."""

    buffer_days: int
    window_days: int
    buffer_source: str = SOURCE_SYSTEM
    window_source: str = SOURCE_SYSTEM

    def as_dict(self) -> dict:
        return {
            "buffer_days": self.buffer_days,
            "window_days": self.window_days,
            "buffer_source": self.buffer_source,
            "window_source": self.window_source,
        }


def _override(project, name: str):
    """A project's own override for one setting, or ``None`` meaning inherit."""
    state = getattr(project, "state", None)
    fast = getattr(state, "fast", None) or {}
    overrides = fast.get("timeline_overrides") or {}
    value = overrides.get(name)
    return value if isinstance(value, int) else None


def _watch_value(watch, name: str):
    value = getattr(watch, name, None)
    return value if isinstance(value, int) else None


def effective_timeline(project=None, reader=None) -> Timeline:
    """The buffer and window to judge ``project`` by, for ``reader``.

    Either argument may be ``None``: a personal report with no project in hand
    resolves the reader's own defaults, and a lab's report passes the lab as the
    reader. Every level is consulted independently for each of the two numbers, so
    a project can override the window and inherit the buffer.
    """
    from apps.accounts.models import Lab

    candidates: list[tuple[int | None, str]] = []
    window_candidates: list[tuple[int | None, str]] = []

    if project is not None:
        candidates.append((_override(project, "deadline_buffer_days"), SOURCE_PROJECT))
        window_candidates.append(
            (_override(project, "min_paper_window_days"), SOURCE_PROJECT)
        )

    # The reader's own settings come before the lab's: a lab project in someone's
    # personal report is judged by whether *they* can make the deadline.
    if reader is not None and not isinstance(reader, Lab):
        watch = getattr(reader, "watch", None)
        candidates.append((_watch_value(watch, "deadline_buffer_days"), SOURCE_USER))
        window_candidates.append(
            (_watch_value(watch, "min_paper_window_days"), SOURCE_USER)
        )

    lab = reader if isinstance(reader, Lab) else getattr(project, "scope_lab", None)
    if lab is not None:
        watch = getattr(lab, "watch", None)
        candidates.append((_watch_value(watch, "deadline_buffer_days"), SOURCE_LAB))
        window_candidates.append(
            (_watch_value(watch, "min_paper_window_days"), SOURCE_LAB)
        )

    buffer_days, buffer_source = _first(candidates, SYSTEM_BUFFER_DAYS)
    window_days, window_source = _first(window_candidates, SYSTEM_WINDOW_DAYS)
    return Timeline(
        buffer_days=buffer_days,
        window_days=window_days,
        buffer_source=buffer_source,
        window_source=window_source,
    )


def _first(candidates: list[tuple[int | None, str]], fallback: int) -> tuple[int, str]:
    for value, source in candidates:
        if value is not None:
            return value, source
    return fallback, SOURCE_SYSTEM
