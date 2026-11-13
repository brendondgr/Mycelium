"""Ambient Plan 09 — "What changed" in the weekly, for whom.

A personal change reaches that person only. A change to a lab project the lab
shares reaches the lab weekly and each member's weekly, once each. A change to
a lab project the lab does not share reaches its members and never the lab.
Every ``[O#]`` resolves, and the verifier removes a sentence citing one that
does not. The interpretation line appears only when explorations move the
ranking and one was confirmed this week.
"""

from __future__ import annotations

import pytest
from apps.accounts.models import Lab, LabMembership, Profile
from apps.ambient.models import AppliedChange
from apps.research.models import Project, ProjectMember
from django.contrib.auth.models import User
from django.utils import timezone

from tools.delivery.report_grammar import CHANGE_CITATION, change_citations
from tools.delivery.weekly import generate_weekly_for_lab, generate_weekly_for_user
from tools.delivery.weekly_build import SURFACE_CHANNEL, SURFACE_DM, build_weekly_packet
from tools.delivery.weekly_verify import verify_body, verify_line

TODAY = timezone.localdate()
QUIET = lambda _s, _p: ""  # noqa: E731 - the model says nothing; the frame speaks


@pytest.fixture
def world(db):
    ada = User.objects.create_user("ada", "ada@example.org", "pw", first_name="Ada")
    bo = User.objects.create_user("bo", "bo@example.org", "pw", first_name="Bo")
    cy = User.objects.create_user("cy", "cy@example.org", "pw", first_name="Cy")
    for person in (ada, bo, cy):
        Profile.objects.get_or_create(user=person)
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    LabMembership.objects.create(user=ada, lab=lab, is_lead=True)
    LabMembership.objects.create(user=bo, lab=lab)
    LabMembership.objects.create(user=cy, lab=lab)
    shared = Project.objects.create(
        name="Imaging pipeline", scope_lab=lab, share_in_lab_reports=True
    )
    private = Project.objects.create(name="Grant draft", scope_lab=lab)
    for person in (ada, bo):
        ProjectMember.objects.create(project=shared, user=person)
    ProjectMember.objects.create(project=private, user=ada)
    return {
        "ada": ada,
        "bo": bo,
        "cy": cy,
        "lab": lab,
        "shared": shared,
        "private": private,
    }


def _change(user, kind, topic, **fields):
    return AppliedChange.objects.create(user=user, kind=kind, topic=topic, **fields)


def _packet_for(user=None, lab=None):
    from tools.delivery.briefing import (
        report_projects_for_lab,
        report_projects_for_user,
    )

    if lab is not None:
        return build_weekly_packet(
            target_filter={"target_lab": lab},
            projects=report_projects_for_lab(lab),
            reader=lab,
            surface=SURFACE_CHANNEL,
            label=lab.slug,
            today=TODAY,
        )
    return build_weekly_packet(
        target_filter={"target_user": user},
        projects=report_projects_for_user(user),
        reader=user,
        surface=SURFACE_DM,
        label=str(user.pk),
        today=TODAY,
    )


def test_a_personal_change_reaches_that_person_only(world):
    ada = world["ada"]
    _change(
        ada,
        "profile_edit",
        "clinical research",
        field="interests.trajectory",
        surface="dm",
    )
    _change(ada, "exploration_confirmed", "conformal prediction", surface="web")
    body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    assert "## What changed" in body and "### Your understanding" in body
    assert "**clinical research** — added to your direction on Discord" in body
    assert (
        "**conformal prediction** — in your reports; you confirmed it on the web"
        in body
    )
    for other in ("bo", "cy"):
        assert (
            "clinical research"
            not in generate_weekly_for_user(
                world[other], complete=QUIET, today=TODAY
            ).body
        )
    lab_body = generate_weekly_for_lab(world["lab"], complete=QUIET, today=TODAY).body
    assert "clinical research" not in lab_body
    assert "conformal prediction" not in lab_body


def test_a_shared_lab_project_change_reaches_the_lab_and_each_member_once(world):
    ada, bo = world["ada"], world["bo"]
    _change(
        ada,
        "development_recorded",
        "the scanner dataset arrived",
        project=world["shared"],
        surface="told",
        visibility="lab",
    )
    lab_body = generate_weekly_for_lab(world["lab"], complete=QUIET, today=TODAY).body
    assert lab_body.count("the scanner dataset arrived") == 1
    assert "Ada told Mylo" in lab_body
    ada_body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    assert ada_body.count("the scanner dataset arrived") == 1
    assert "you told Mylo" in ada_body
    bo_body = generate_weekly_for_user(bo, complete=QUIET, today=TODAY).body
    assert bo_body.count("the scanner dataset arrived") == 1
    assert "Ada told Mylo" in bo_body
    # Cy is in the lab but not on the project: the lab weekly is how they hear.
    cy_body = generate_weekly_for_user(world["cy"], complete=QUIET, today=TODAY).body
    assert "the scanner dataset arrived" not in cy_body


def test_an_unshared_lab_project_change_stays_with_its_members(world):
    _change(
        world["ada"],
        "state_edit",
        "annotation budget",
        project=world["private"],
        field="slow.blockers",
        visibility="lab",
    )
    lab_body = generate_weekly_for_lab(world["lab"], complete=QUIET, today=TODAY).body
    assert "annotation budget" not in lab_body
    ada_body = generate_weekly_for_user(world["ada"], complete=QUIET, today=TODAY).body
    assert (
        "the stated blockers changed (annotation budget) — accepted by you" in ada_body
    )


def test_a_private_fact_on_a_shared_project_never_reaches_the_lab(world):
    _change(
        world["ada"],
        "development_recorded",
        "reviewer 2 is my old advisor",
        project=world["shared"],
        surface="told",
        visibility="personal",
    )
    lab_body = generate_weekly_for_lab(world["lab"], complete=QUIET, today=TODAY).body
    assert "reviewer 2" not in lab_body
    assert (
        "reviewer 2"
        not in generate_weekly_for_user(world["bo"], complete=QUIET, today=TODAY).body
    )
    assert (
        "reviewer 2"
        in generate_weekly_for_user(world["ada"], complete=QUIET, today=TODAY).body
    )


def test_every_change_citation_resolves(world):
    ada = world["ada"]
    _change(ada, "exploration_confirmed", "conformal prediction", surface="dm")
    _change(
        ada,
        "development_recorded",
        "the scanner dataset arrived",
        project=world["shared"],
        surface="told",
        visibility="lab",
    )
    packet = _packet_for(ada)
    body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    cited = change_citations(body)
    assert cited and set(cited) <= packet.change_numbers()
    # The project row travels in the project's packet for the model to cite.
    [project] = [p for p in packet.projects if p.label == "Imaging pipeline"]
    assert project.changes[0]["id"].startswith("O")
    assert project.as_dict()["changes"]


def test_the_verifier_removes_a_sentence_citing_a_change_that_is_not_there():
    kept, removed = verify_line(
        "Use it now [P1][O1]. It answers the blocker you closed [P1][O7].",
        allowed={1},
        numbers=set(),
        changes={1},
    )
    assert kept == "Use it now [P1][O1]."
    assert [row.check for row in removed] == ["unresolved_citation"]


def test_a_model_sentence_linking_an_item_to_a_change_survives(world):
    from tools.delivery.weekly_packet import PacketItem

    ada = world["ada"]
    _change(
        ada,
        "development_recorded",
        "the scanner dataset arrived",
        project=world["shared"],
        surface="told",
        visibility="lab",
    )
    packet = _packet_for(ada)
    packet.projects[0].items.append(
        PacketItem(n=1, content_id="c1", title="A scanner study", url="")
    )
    body, record = verify_body(
        "This is the scanner study to use first [P1][O1]. And [O9] too [P1].",
        packet,
    )
    assert "[P1][O1]" in body and "[O9]" not in body
    assert record.unresolved == 1


def test_the_interpretation_line_needs_the_ranking_to_move(world, settings):
    ada = world["ada"]
    _change(ada, "exploration_confirmed", "conformal prediction", surface="dm")
    settings.AMBIENT_DRIFT_ENABLED = False
    # A public origin, so "Tell me" is a link (with none, it is plain text).
    settings.DISCORD_APP_BASE_URL = "https://mycelium.example.edu"
    body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    assert "give it more attention" not in body
    settings.AMBIENT_DRIFT_ENABLED = True
    body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    assert "You confirmed an exploration of **conformal prediction**" in body
    assert "Not right? [Tell me](" in body and "/app/mylo-and-you)" in body


def test_no_interpretation_for_an_exploration_since_undone(world, settings):
    settings.AMBIENT_DRIFT_ENABLED = True
    _change(
        world["ada"],
        "exploration_confirmed",
        "conformal prediction",
        surface="dm",
        undone_at=timezone.now(),
    )
    body = generate_weekly_for_user(world["ada"], complete=QUIET, today=TODAY).body
    assert "give it more attention" not in body
    assert "(since undone)" in body


def test_nothing_changed_means_no_section(world):
    body = generate_weekly_for_user(world["cy"], complete=QUIET, today=TODAY).body
    assert "What changed" not in body


def test_last_weeks_changes_are_not_this_weeks(world):
    row = _change(world["ada"], "exploration_confirmed", "old news", surface="dm")
    AppliedChange.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=8)
    )
    body = generate_weekly_for_user(world["ada"], complete=QUIET, today=TODAY).body
    assert "old news" not in body


def test_answers_and_waiting_proposals_are_counted(world):
    from datetime import timedelta

    from apps.ambient.models import PendingSuggestion

    from tools.delivery.models import ReflectionProposal

    ada = world["ada"]
    for surface in ("dm", "dm", "web"):
        PendingSuggestion.objects.create(
            user=ada,
            kind="interest",
            topic=f"t-{surface}-{timezone.now().timestamp()}",
            state="answered",
            verdict="rejected",
            choice="no",
            answered_on=surface,
            answered_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=14),
        )
    ReflectionProposal.objects.create(
        target_user=ada,
        project=world["shared"],
        kind="close_blocker",
        proposal={"slow": {"blockers": []}},
        evidence={"source": "conversation"},
        expires_on=TODAY + timedelta(days=14),
    )
    body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    assert (
        "You answered 3 of Mylo's questions this week (2 on Discord, 1 on the web)."
        in body
    )
    assert "1 suggested change to a project's stated state is waiting" in body


def test_the_weekly_records_what_it_was_written_against(world):
    briefing = generate_weekly_for_user(world["ada"], complete=QUIET, today=TODAY)
    assert briefing.context_version


def test_the_change_citation_grammar():
    assert CHANGE_CITATION.findall("a [O1] b [P2] c [O12]") == ["1", "12"]
    assert change_citations("[O2] then [O2] and [O3]") == [2, 3]


def test_the_pdf_renders_a_change_citation_as_a_marker():
    from tools.delivery.daily_report_pdf import _inline

    out = _inline("It addresses the blocker [P1][O2].")
    assert "[O2]</font>" in out and "[P1]</font>" in out


# -- the daily's one line (steps 5 and 7) -------------------------------------------


def test_the_daily_says_what_took_effect_since_yesterday(world):
    from tools.delivery.weekly_changes import changed_today

    ada = world["ada"]
    _change(ada, "profile_edit", "kriging", field="interests.skills", surface="dm")
    _change(
        ada,
        "state_edit",
        "annotation budget",
        project=world["shared"],
        field="slow.blockers",
        visibility="lab",
    )
    old = _change(ada, "profile_edit", "old skill", field="interests.skills")
    AppliedChange.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=2)
    )
    lines = changed_today(reader=ada, projects=[world["shared"]], is_lab=False)
    assert "**kriging** — added to your skills; you said yes." in lines
    assert any(
        "stated blockers changed (annotation budget), accepted by you" in line
        for line in lines
    )
    assert not any("old skill" in line for line in lines)
    # The lab hears the accepted state change and nothing personal.
    lab_lines = changed_today(
        reader=world["lab"], projects=[world["shared"]], is_lab=True
    )
    assert lab_lines == [
        "**Imaging pipeline** — the stated blockers changed (annotation budget), "
        "accepted by Ada."
    ]


def test_a_development_that_changes_the_alerts_is_one_line(world):
    from apps.ambient.models import ProjectDevelopment

    from tools.delivery.weekly_changes import changed_today

    ProjectDevelopment.objects.create(
        project=world["shared"],
        speaker=world["ada"],
        change="method_dropped",
        topic="graph neural networks",
        text="Said the lab dropped GNNs.",
        force="fact",
        occurred_on=TODAY,
        status="active",
        origin="told",
        visibility="lab",
    )
    lines = changed_today(reader=world["bo"], projects=[world["shared"]], is_lab=False)
    assert lines == [
        "**Imaging pipeline** — graph neural networks was dropped, so Mylo no "
        "longer flags overlap on it."
    ]
    # OD-09a: the lab channel does not get a same-day line for a development.
    assert (
        changed_today(reader=world["lab"], projects=[world["shared"]], is_lab=True)
        == []
    )


def test_the_changed_today_section_joins_needs_your_attention():
    from tools.delivery.weekly_changes import with_changed_today

    assert with_changed_today("", []) == ""
    assert with_changed_today("", ["**x** — y."]).startswith(
        "## Needs your attention\n\n### Changed today\n- **x** — y."
    )
    assert with_changed_today("## Needs your attention\n\n### A", ["z"]).endswith(
        "### Changed today\n- z"
    )


def test_the_posts_carry_a_changed_today_field(world):
    from tools.delivery.daily_report import compile_report_for_lab
    from tools.delivery.discord_embeds import lab_post_embed

    data = compile_report_for_lab(world["lab"])
    embed = lab_post_embed(
        data, data.stats, changes=["**P** — the stated method changed."]
    )
    [field] = [f for f in embed["fields"] if f["name"] == "Changed today"]
    assert field["value"] == "**P** — the stated method changed."
    quiet = lab_post_embed(data, data.stats)
    assert "Changed today" not in [f["name"] for f in quiet["fields"]]


def test_an_undo_in_the_same_week_is_a_mark_not_a_second_row(world):
    ada = world["ada"]
    original = _change(
        ada, "profile_edit", "kriging", field="interests.skills", surface="dm"
    )
    AppliedChange.objects.filter(pk=original.pk).update(undone_at=timezone.now())
    _change(ada, "undone", "kriging", undo_of=original)
    body = generate_weekly_for_user(ada, complete=QUIET, today=TODAY).body
    assert "**kriging** — added to your skills on Discord" in body
    assert "(since undone)" in body
    assert "**kriging** — undone on" not in body
