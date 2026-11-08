"""Can this project make that deadline? — the arithmetic, and its edges.

The distinctions these tests defend are the ones that make the answer worth
reading. "Tight" and "misses" are different advice. "Misses" and "not viable" are
different claims — one about this project's plan, the other about anybody's. And
"no milestone" is an answer, not a gap to fill with a guessed date: a guessed date
produces a confident verdict about a plan that does not exist.
"""

from __future__ import annotations

from datetime import date

import pytest
from tools.retrieval.models import ContentDeadline, ContentItem, SavedOpportunity

from apps.content.matchers import timeline as tl
from apps.content.timeline_settings import Timeline

TODAY = date(2026, 9, 11)
DEFAULTS = Timeline(buffer_days=14, window_days=60, buffer_source="you",
                    window_source="you")


def _row(
    *,
    due: date | None,
    kind: str = SavedOpportunity.DeadlineKind.MANUSCRIPT,
    confidence: str = ContentDeadline.Confidence.CONFIRMED,
    title: str = "CIKM 2027",
) -> ContentDeadline:
    """An unsaved deadline row — the matcher is pure and needs no database."""
    item = ContentItem(type=ContentItem.Type.CONFERENCE, metadata={"title": title})
    return ContentDeadline(
        content=item, kind=kind, due_date=due, confidence=confidence
    )


def _plan(*milestones, constraints=()) -> tl.ProjectPlan:
    return tl.ProjectPlan(milestones=list(milestones), constraints=list(constraints))


DRAFT = {"id": "m2", "kind": "draft_by", "what": "paper draft", "date": "2026-12-15"}
RESULTS = {"id": "m1", "kind": "results_by", "what": "pilot", "date": "2026-10-09"}


# --------------------------------------------------------------------------- #
# The four verdicts about a plan
# --------------------------------------------------------------------------- #
def test_a_deadline_a_buffer_past_the_milestone_fits() -> None:
    row = _row(due=date(2027, 1, 20))  # 36 days after the 15 Dec draft

    verdict = tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY)

    assert verdict.status == tl.FITS
    assert verdict.slack_days == 36
    assert verdict.milestone_what == "paper draft"


def test_inside_the_buffer_is_tight_not_a_fit() -> None:
    """Still possible. The report says so, and says by how little."""
    row = _row(due=date(2026, 12, 20))  # 5 days after the draft

    verdict = tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY)

    assert verdict.status == tl.TIGHT
    assert verdict.slack_days == 5
    assert verdict.is_reachable is True


def test_a_deadline_before_the_milestone_misses() -> None:
    row = _row(due=date(2026, 11, 20))

    verdict = tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY)

    assert verdict.status == tl.MISSES
    assert verdict.slack_days < 0
    assert verdict.is_reachable is False


def test_constraint_marks_venue_not_viable() -> None:
    """A different claim from "misses": about anybody's plan, not this one's."""
    row = _row(due=date(2026, 11, 11))  # 61 days out, so viable on its own

    unconstrained = tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY)
    assert unconstrained.status != tl.NOT_VIABLE

    constrained = tl.judge_row(
        row,
        _plan(
            DRAFT,
            constraints=[
                {"id": "c1", "kind": "earliest_start", "date": "2026-10-24"}
            ],
        ),
        DEFAULTS,
        today=TODAY,
    )

    assert constrained.status == tl.NOT_VIABLE
    assert constrained.window_days == 18
    assert constrained.constraint_id == "c1"


def test_the_binding_constraint_is_the_latest_one() -> None:
    """"Not before October" and "not before December" together mean December."""
    plan = _plan(
        DRAFT,
        constraints=[
            {"id": "c1", "kind": "earliest_start", "date": "2026-10-01"},
            {"id": "c2", "kind": "earliest_start", "date": "2026-12-01"},
        ],
    )

    verdict = tl.judge_row(_row(due=date(2027, 1, 5)), plan, DEFAULTS, today=TODAY)

    assert verdict.constraint_id == "c2"
    assert verdict.status == tl.NOT_VIABLE


# --------------------------------------------------------------------------- #
# What Mylo declines to judge
# --------------------------------------------------------------------------- #
def test_an_undated_milestone_produces_no_milestone_not_a_guess() -> None:
    """A guessed date produces a confident verdict about a plan that isn't there."""
    undated = {"id": "m9", "kind": "draft_by", "what": "draft", "date": ""}

    verdict = tl.judge_row(
        _row(due=date(2027, 3, 1)), _plan(undated), DEFAULTS, today=TODAY
    )

    assert verdict.status == tl.NO_MILESTONE
    assert verdict.slack_days is None


def test_a_rolling_call_is_reported_as_rolling_not_skipped() -> None:
    """Always makeable — which is precisely why it is worth saying."""
    row = _row(due=None, confidence=ContentDeadline.Confidence.ROLLING)

    verdict = tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY)

    assert verdict.status == tl.ROLLING
    assert verdict.due_date is None


def test_an_event_date_is_not_a_deadline_at_all() -> None:
    """When the conference happens is never a thing to plan a submission against."""
    row = _row(due=date(2027, 6, 1), kind=SavedOpportunity.DeadlineKind.EVENT)

    assert tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY) is None


def test_an_anticipated_date_is_flagged_not_confirmed() -> None:
    """Planning against a projected date is a different act, and Mylo says so."""
    row = _row(
        due=date(2027, 5, 16), confidence=ContentDeadline.Confidence.ANTICIPATED
    )

    verdict = tl.judge_row(row, _plan(DRAFT), DEFAULTS, today=TODAY)

    assert verdict.anticipated is True
    assert verdict.status == tl.FITS  # still judged; just not as a published date


# --------------------------------------------------------------------------- #
# Which milestone, and which tests apply
# --------------------------------------------------------------------------- #
def test_an_abstract_is_judged_against_results_and_a_paper_against_a_draft() -> None:
    """Backwards here is how you tell someone a venue fits six weeks too late."""
    plan = _plan(RESULTS, DRAFT)
    due = date(2026, 11, 13)

    abstract = tl.judge_row(
        _row(due=due, kind=SavedOpportunity.DeadlineKind.ABSTRACT),
        plan,
        DEFAULTS,
        today=TODAY,
    )
    paper = tl.judge_row(
        _row(due=due, kind=SavedOpportunity.DeadlineKind.MANUSCRIPT),
        plan,
        DEFAULTS,
        today=TODAY,
    )

    assert abstract.milestone_id == "m1"
    assert abstract.status == tl.FITS  # 35 days after the pilot
    assert paper.milestone_id == "m2"
    assert paper.status == tl.MISSES  # the draft is a month later


def test_the_paper_window_is_not_applied_to_an_abstract() -> None:
    """Holding an abstract to a writing window rules out the easiest venues."""
    due = date(2026, 10, 20)  # 39 days out, under the 60-day window

    abstract = tl.judge_row(
        _row(due=due, kind=SavedOpportunity.DeadlineKind.ABSTRACT),
        _plan(RESULTS),
        DEFAULTS,
        today=TODAY,
    )
    paper = tl.judge_row(
        _row(due=due, kind=SavedOpportunity.DeadlineKind.MANUSCRIPT),
        _plan(RESULTS, DRAFT),
        DEFAULTS,
        today=TODAY,
    )

    assert abstract.status != tl.NOT_VIABLE
    assert paper.status == tl.NOT_VIABLE


def test_the_earliest_dated_milestone_of_a_kind_is_the_one_that_counts() -> None:
    """The work first exists at the first of them."""
    later = {"id": "m3", "kind": "draft_by", "what": "second draft",
             "date": "2027-02-01"}

    verdict = tl.judge_row(
        _row(due=date(2027, 1, 20)), _plan(DRAFT, later), DEFAULTS, today=TODAY
    )

    assert verdict.milestone_id == "m2"
    assert verdict.status == tl.FITS


# --------------------------------------------------------------------------- #
# The setting that makes it adjustable
# --------------------------------------------------------------------------- #
def test_buffer_override_changes_status_without_writeup_refresh() -> None:
    """Plan S10: changing a buffer recomputes statuses with zero model calls."""
    row = _row(due=date(2026, 12, 20))  # 5 days after the draft

    generous = tl.judge_row(
        row,
        _plan(DRAFT),
        Timeline(buffer_days=3, window_days=60),
        today=TODAY,
    )
    strict = tl.judge_row(
        row,
        _plan(DRAFT),
        Timeline(buffer_days=30, window_days=60),
        today=TODAY,
    )

    assert generous.status == tl.FITS
    assert strict.status == tl.TIGHT
    # The verdict carries where the number came from, so a reader who disagrees
    # knows which dial to turn.
    assert strict.buffer_days == 30


@pytest.mark.django_db
def test_rows_come_back_as_a_timeline_with_undated_last(db) -> None:
    """A caller should never have to re-sort what is meant to read as a timeline."""
    from django.contrib.auth.models import User

    from apps.research.models import Project, ProjectState

    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Ariadne", scope_user=owner)
    ProjectState.objects.create(project=project).apply(
        {"fast": {"milestones": [DRAFT]}}
    ).save()
    project.refresh_from_db()

    ids = []
    for title, due, confidence in (
        ("Later venue", date(2027, 3, 1), ContentDeadline.Confidence.CONFIRMED),
        ("Rolling venue", None, ContentDeadline.Confidence.ROLLING),
        ("Sooner venue", date(2027, 1, 20), ContentDeadline.Confidence.CONFIRMED),
    ):
        item = ContentItem.objects.create(
            type=ContentItem.Type.CONFERENCE,
            source="test",
            external_id=title,
            metadata={"title": title},
        )
        ContentDeadline.objects.create(
            content=item,
            kind=SavedOpportunity.DeadlineKind.MANUSCRIPT,
            due_date=due,
            confidence=confidence,
        )
        ids.append(item.id)

    rows = tl.timeline_rows(project, ids, reader=owner, today=TODAY)

    assert [row.venue for row in rows] == [
        "Sooner venue",
        "Later venue",
        "Rolling venue",
    ]
    assert rows[0].status == tl.FITS
    assert rows[-1].status == tl.ROLLING
