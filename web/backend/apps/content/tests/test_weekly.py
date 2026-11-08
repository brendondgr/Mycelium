"""The Monday weekly: a closed packet, a checked body, and one delivery.

The weekly is the only report where a model writes at length about a project, so
these tests are mostly about what it is *not allowed* to say. A weekly that is
confidently wrong about a project's own research is wrong in the reader's own
domain, where they will notice, and it takes the correct sentences down with it.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.retrieval.models import (
    ContentItem,
    DailyBriefing,
    ProjectAlert,
    RelevanceScore,
)

from apps.accounts.models import Lab, WatchPreference
from apps.content import weekly as weekly_module
from apps.content.weekly import compose_weekly, generate_weekly_for_user
from apps.content.weekly_build import SURFACE_DM, build_weekly_packet, week_start
from apps.content.weekly_packet import PacketItem, ProjectPacket, WeeklyPacket
from apps.content.weekly_verify import verify_body, verify_line
from apps.research.models import Project, ProjectState

MONDAY = date(2026, 9, 21)
WEDNESDAY = date(2026, 9, 23)


def _packet(*items: PacketItem, **project_fields) -> WeeklyPacket:
    project = ProjectPacket(
        project_id="p1", label="Synapse", items=list(items), **project_fields
    )
    return WeeklyPacket(
        packet_id="weekly:test:2026-09-21",
        surface=SURFACE_DM,
        week_start=MONDAY,
        projects=[project],
    )


def _item(n: int, **fields) -> PacketItem:
    return PacketItem(
        n=n,
        content_id=f"c{n}",
        title=fields.pop("title", f"Paper {n}"),
        url=f"https://example.org/{n}",
        **fields,
    )


# --------------------------------------------------------------------------- #
# The week's key
# --------------------------------------------------------------------------- #
def test_the_week_is_keyed_on_its_monday_not_on_the_day_it_ran() -> None:
    """A re-run on Tuesday must re-find Monday's row, not write a second week."""
    assert week_start(MONDAY) == MONDAY
    assert week_start(WEDNESDAY) == MONDAY
    assert week_start(MONDAY + timedelta(days=6)) == MONDAY


# --------------------------------------------------------------------------- #
# The verifier
# --------------------------------------------------------------------------- #
def test_unresolved_citation_sentence_removed() -> None:
    """A citation to nothing is worse than no citation — it looks checked."""
    kept, removed = verify_line(
        "It tests your question [P1]. It also beats your baseline [P9].",
        allowed={1},
        numbers=set(),
    )

    assert kept == "It tests your question [P1]."
    assert [row.check for row in removed] == ["unresolved_citation"]


def test_number_not_in_packet_removes_sentence() -> None:
    """The damaging failure is not a false claim but a plausible one."""
    kept, removed = verify_line(
        "The grant typically funds about 47 awards per cycle [P1].",
        allowed={1},
        numbers={"1200"},
    )

    assert kept == ""
    assert removed[0].check == "numbers_in_packet"


def test_a_number_the_packet_does_contain_survives() -> None:
    kept, _removed = verify_line(
        "It releases 1,200 labelled passages [P1].", allowed={1}, numbers={"1200"}
    )
    assert kept.startswith("It releases 1,200")


def test_small_counts_are_not_claims_about_the_source() -> None:
    """Requiring the packet to contain "three" would remove correct English."""
    kept, removed = verify_line(
        "It tests on two of your three benchmarks [P1].", allowed={1}, numbers=set()
    )
    assert kept
    assert not removed


def test_uncited_prose_is_allowed_to_be_uncited() -> None:
    """A sentence asserting nothing about an item is prose, and prose is fine."""
    kept, removed = verify_line(
        "This was a quiet week for the project.", allowed=set(), numbers=set()
    )
    assert kept
    assert not removed


def test_structure_survives_the_verifier_untouched() -> None:
    """Reflowing what survives would make the verifier decide the document's shape."""
    body = (
        "## Project · Synapse\n"
        "\n"
        "1. **[A paper](https://x.org/1)** — **NEW**\n"
        "- **What overlaps:** it asks your question [P1]. It cites 47 studies [P1].\n"
        "| Due | What |\n"
    )
    checked, record = verify_body(body, _packet(_item(1)))

    lines = checked.splitlines()
    assert lines[0] == "## Project · Synapse"
    assert lines[2].startswith("1. **[A paper]")
    assert lines[3].startswith("- **What overlaps:** it asks your question [P1].")
    assert "47 studies" not in checked
    assert record.removed == 1


def test_an_entailment_check_is_a_seam_not_a_default() -> None:
    """It costs a model call and its agreement has not been measured (OD4)."""
    body = "It asks your question [P1].\n"

    kept, _record = verify_body(body, _packet(_item(1)))
    assert "It asks your question" in kept

    refused, record = verify_body(
        body, _packet(_item(1)), entails=lambda _s, _c: False
    )
    assert "It asks your question" not in refused
    assert record.removed_sentences[0].check == "entailment"


def test_the_footer_says_what_was_checked() -> None:
    _kept, record = verify_body(
        "It asks your question [P1]. It cites 47 studies [P1].\n",
        _packet(_item(1)),
    )

    footer = record.footer()
    assert "2 claims" in footer
    assert "1 supported" in footer
    assert "1 removed as unsupported" in footer


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
def test_the_frame_is_rendered_by_code_around_the_model_body() -> None:
    packet = _packet(
        _item(1, source="arXiv", kind="paper"),
        timeline_rows=[
            {
                "due_date": "2026-11-13",
                "venue": "SOT 2027 abstract",
                "status": "fits",
                "buffer_days": 14,
                "buffer_source": "you",
                "anticipated": False,
            }
        ],
    )
    packet.deadline_horizon = packet.projects[0].timeline_rows

    body, record, origin = compose_weekly(
        packet, complete=lambda _s, _p: "It asks your question [P1]."
    )

    assert origin == "llm"
    assert "## Deadline horizon · next 10 weeks" in body
    assert "SOT 2027 abstract" in body
    assert "## References" in body
    assert "- **[P1]** Paper 1 · arXiv · paper" in body
    assert record.footer() in body


def test_a_model_that_is_down_still_produces_a_grounded_weekly() -> None:
    """The fallback says less, and says nothing the packet does not contain."""
    packet = _packet(_item(1), entered=3)

    def down(_system, _prompt):
        raise RuntimeError("connection refused")

    body, _record, origin = compose_weekly(packet, complete=down)

    assert origin == "fallback"
    assert "3 item(s) entered" in body
    assert "%" not in body


def test_structural_deviation_still_delivers() -> None:
    """Plan §4.2 / invariant 10: a report is never withheld for its shape."""
    packet = _packet(_item(1))

    body, _record, _origin = compose_weekly(
        packet, complete=lambda _s, _p: "Just one line, no headings at all."
    )

    assert "Just one line" in body
    assert "## References" in body


def test_a_quiet_project_gets_two_lines_and_never_a_model_call() -> None:
    """A project that vanishes from the weekly reads as one that was dropped."""
    calls = []

    def ask(_s, _p):
        calls.append(1)
        return "prose"

    body, _record, _origin = compose_weekly(_packet(), complete=ask)

    assert "Nothing moved for this project this week." in body
    # The overview still runs; the project section did not.
    assert len(calls) <= 1


def test_a_long_section_is_trimmed_on_a_sentence_boundary() -> None:
    """Plan H5. A section that stops mid-clause reads as a bug in the product."""
    long_prose = " ".join(["This sentence has six words here."] * 300)

    body, _record, _origin = compose_weekly(
        _packet(_item(1)), complete=lambda _s, _p: long_prose
    )

    # The project section alone, not the overview beside it: each is capped at
    # 700 words in its own right.
    section = body.split("## Project · Synapse")[1].split("## References")[0]
    assert len(section.split()) <= 700
    assert section.rstrip().endswith(".")


def test_a_lab_weekly_may_name_a_member_but_never_their_eligibility() -> None:
    """Plan D6 reverses the no-names rule for the weekly; invariant 7 does not."""
    packet = _packet(
        _item(1),
        team_gaps=[
            {
                "content_id": "c1",
                "requirement": "knowledge graphs",
                "is_gap": False,
                "covered_by": [{"name": "Brendon", "stated": "knowledge graphs"}],
            },
            {
                "content_id": "c1",
                "requirement": "environmental health",
                "is_gap": True,
                "covered_by": [],
            },
        ],
    )

    body, _record, _origin = compose_weekly(packet, complete=lambda _s, _p: "")

    assert "Best suited to knowledge graphs: Brendon." in body
    assert "nobody on the team lists: environmental health" in body
    assert "citizen" not in body.lower()


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #
@pytest.fixture
def reader(db) -> User:
    user = User.objects.create_user("reader", password="p")
    WatchPreference.objects.create(user=user, categories=["papers"])
    return user


@pytest.mark.django_db
def test_a_weekly_packet_marks_what_was_already_alerted(reader: User) -> None:
    """Plan 6.6: the weekly reports status, it does not raise it again."""
    project = Project.objects.create(name="Synapse", scope_user=reader)
    ProjectState.objects.create(project=project).apply(
        {"slow": {"claimed_contribution": "A measurement-validity study"}}
    ).save()
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="arXiv",
        external_id="p1",
        source_url="https://example.org/p1",
        metadata={"title": "A corruption study"},
    )
    RelevanceScore.objects.create(
        content=item,
        target_project=project,
        score=0.8,
        signals={
            "suggested": True,
            "top_rank": 1,
            "entered_top_on": MONDAY.isoformat(),
            "is_new_top": True,
        },
    )
    ProjectAlert.objects.create(
        target_user=reader,
        project=project,
        content=item,
        trigger=ProjectAlert.Trigger.OVERLAP_RISK,
        fired_on=MONDAY,
    )
    project.refresh_from_db()

    packet = build_weekly_packet(
        target_filter={"target_user": reader},
        projects=[project],
        reader=reader,
        surface=SURFACE_DM,
        label=str(reader.id),
        today=MONDAY,
    )

    assert packet.projects[0].already_alerted == [
        {"item": str(item.id), "trigger": "overlap_risk", "on": MONDAY.isoformat()}
    ]
    assert packet.projects[0].items[0].matchers == ["overlap_risk"]
    # Numbering runs across the packet, so [P1] means one thing in the document.
    assert packet.numbers() == {1}
    assert packet.references()[0]["title"] == "A corruption study"


@pytest.mark.django_db
def test_the_weekly_is_a_second_row_beside_mondays_daily(reader: User) -> None:
    """Cadence governs push, not computation: Monday still writes a daily."""
    from apps.content.briefing import generate_briefing_for_user

    generate_briefing_for_user(reader, complete=lambda _s, _u: None)
    weekly = generate_weekly_for_user(
        reader, complete=lambda _s, _p: "", today=MONDAY
    )

    assert weekly.kind == DailyBriefing.Kind.WEEKLY
    assert weekly.generated_on == MONDAY
    assert DailyBriefing.objects.filter(user=reader).count() == 2
    # Every existing reader keeps reading dailies without asking.
    assert DailyBriefing.latest_for(user=reader).kind == DailyBriefing.Kind.DAILY


@pytest.mark.django_db
def test_rerunning_the_weekly_replaces_the_week_rather_than_adding_one(
    reader: User,
) -> None:
    generate_weekly_for_user(reader, complete=lambda _s, _p: "", today=MONDAY)
    generate_weekly_for_user(reader, complete=lambda _s, _p: "", today=WEDNESDAY)

    rows = DailyBriefing.objects.filter(
        user=reader, kind=DailyBriefing.Kind.WEEKLY
    )
    assert rows.count() == 1
    assert rows.get().generated_on == MONDAY


@pytest.mark.django_db
def test_a_lab_weekly_covers_shared_projects_only(db) -> None:
    """Plan H4: a packet contains only what every reader of that surface may see."""
    from apps.content.weekly import generate_weekly_for_lab

    lab = Lab.objects.create(name="Pulse", slug="pulse")
    Project.objects.create(
        scope_lab=lab, name="Ariadne", share_in_lab_reports=True
    )
    Project.objects.create(scope_lab=lab, name="Unpublished Coral Genome")

    weekly = generate_weekly_for_lab(lab, complete=lambda _s, _p: "", today=MONDAY)

    assert "Unpublished Coral Genome" not in weekly.body
    assert "1 private project not shown" in weekly.body


@pytest.mark.django_db
def test_the_verification_record_is_stored_on_the_row(reader: User) -> None:
    project = Project.objects.create(name="Synapse", scope_user=reader)
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="arXiv",
        external_id="p1",
        metadata={"title": "A paper"},
    )
    RelevanceScore.objects.create(
        content=item,
        target_project=project,
        score=0.8,
        signals={"suggested": True, "top_rank": 1, "is_new_top": True},
    )

    weekly = generate_weekly_for_user(
        reader,
        complete=lambda _s, _p: "It cites 47 studies [P9].",
        today=MONDAY,
    )

    assert weekly.verification["claims"] >= 1
    assert weekly.verification["removed"] >= 1
    assert weekly.verification["removed_sentences"][0]["check"] == (
        "unresolved_citation"
    )


@pytest.mark.django_db
def test_no_weekly_body_ever_carries_a_percentage(reader: User) -> None:
    """Plan S9 / invariant 4."""
    weekly = generate_weekly_for_user(
        reader, complete=lambda _s, _p: "An 88% match for you.", today=MONDAY
    )

    assert "%" not in weekly.body
    assert "cosine" not in weekly.body.lower()


def test_the_weekly_version_is_stamped() -> None:
    assert weekly_module.WEEKLY_VERSION
    assert timezone is not None
