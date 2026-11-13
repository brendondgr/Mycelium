"""What a Discord post may name follows the width of the server it lands in.

Plan "Surfaces": a project — its name, team, alerts, and every item scored for
it — appears only where its scope is at least as wide as the place, and a
server's width is decided by everything bound in it. A ``lab`` project never
reaches the department's server, reaches the lab's own server if there is one,
and otherwise reaches only its members.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from apps.accounts.models import Department, Lab, LabMembership
from apps.integrations.models import DiscordOutboxMessage
from apps.integrations.testing import bind
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)
from apps.research.models import Project, ProjectMember
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

from tools.delivery import announce, discord_announcements, smoke_reports
from tools.delivery.alert_report import open_alerts
from tools.delivery.daily_report import compile_report_for_lab
from tools.delivery.discord_embeds import lab_post_embed
from tools.delivery.lab_digest import compile_post_report, post_width, queue_lab_digest
from tools.delivery.models import AnnouncementSettings, DailyBriefing, ProjectAlert
from tools.delivery.views import _lab_envelope
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = date(2026, 7, 16)
RUN_DATE = timezone.now().date().isoformat()


@pytest.fixture(autouse=True)
def _discord_settings():
    # A fresh copy: the shared object cannot be entered twice at once.
    with override_settings(**discord_test_settings.options):
        clear_discord_cache()
        yield
        clear_discord_cache()


@pytest.fixture
def org(db):
    class World:
        pass

    o = World()
    o.head = User.objects.create_user("head", password="x")
    o.pi = User.objects.create_user("pi", password="x")
    o.member = User.objects.create_user("member", password="x")
    o.dept = Department.objects.create(owner=o.head, name="Biology")
    o.lab = Lab.objects.create(name="Reef", slug="reef", department=o.dept)
    o.sibling = Lab.objects.create(name="Kelp", slug="kelp", department=o.dept)
    grant_bot_server(o.lab)
    LabMembership.objects.create(
        user=o.pi, lab=o.lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    LabMembership.objects.create(
        user=o.member, lab=o.lab, role=LabMembership.Role.MEMBER
    )
    o.projects = {
        scope: Project.objects.create(
            scope_lab=o.lab, name=f"Project {scope}", visibility=scope
        )
        for scope in ("invite_only", "lab", "department", "public")
    }
    o.sibling_project = Project.objects.create(
        scope_lab=o.sibling, name="Kelp department", visibility="department"
    )
    for project in o.projects.values():
        ProjectMember.objects.create(project=project, user=o.member)
    return o


def _in_department_server(org):
    """The lab bound only into its department's server."""
    bind(lab=org.lab, guild_id="g-dept", updates="dept-room")
    bind(department=org.dept, guild_id="g-dept")


def _in_own_server(org):
    bind(lab=org.lab, guild_id="g-own", updates="own-room")


def _project_labels(data) -> set:
    return {part.label for part in data.projects}


def _content(title, kind=ContentItem.Type.GRANT):
    return ContentItem.objects.create(
        type=kind, source="pivot", external_id=title, metadata={"title": title}
    )


def _suggest(project, item):
    RelevanceScore.objects.create(
        content=item,
        target_project=project,
        score=0.9,
        signals={"suggested": True, "first_seen": RUN_DATE, "top_rank": 1},
    )


# --------------------------------------------------------------------------- #
# The daily post, its PDF, alerts
# --------------------------------------------------------------------------- #
def test_a_lab_in_its_departments_server_posts_no_lab_project(org):
    _in_department_server(org)
    assert post_width(org.lab) == "department"

    data = compile_post_report(org.lab)
    assert _project_labels(data) == {"Project department", "Project public"}

    _row, created = queue_lab_digest(org.lab, on=TODAY, data=data)
    if created:
        rendered = json.dumps(DiscordOutboxMessage.objects.get().embed)
        assert "Project lab" not in rendered
        assert "Project invite_only" not in rendered


def test_the_labs_own_server_carries_its_lab_projects(org):
    _in_department_server(org)
    _in_own_server(org)
    assert post_width(org.lab) == "lab"
    assert _project_labels(compile_post_report(org.lab)) == {
        "Project lab",
        "Project department",
        "Project public",
    }


def test_the_lab_web_report_stays_lab_wide(org):
    """The web is the lab's own surface whatever server it posts to."""
    _in_department_server(org)
    assert "Project lab" in _project_labels(compile_report_for_lab(org.lab))
    assert "Project invite_only" not in _project_labels(compile_report_for_lab(org.lab))


def test_an_alert_reaches_only_a_place_its_project_allows(org):
    item = _content("Call")
    for project in org.projects.values():
        ProjectAlert.objects.create(
            project=project,
            target_lab=org.lab,
            content=item,
            trigger=ProjectAlert.Trigger.UNBLOCKS,
            fired_on=TODAY,
            status=ProjectAlert.Status.OPEN,
        )

    def names(width):
        return {
            a.project.name
            for a in open_alerts({"target_lab": org.lab}, TODAY, width=width)
        }

    assert names("lab") == {"Project lab", "Project department", "Project public"}
    assert names("department") == {"Project department", "Project public"}
    assert names("public") == {"Project public"}


def test_the_hidden_count_never_reaches_discord(org):
    _in_own_server(org)
    data = compile_report_for_lab(org.lab)
    data.stats.private_projects_hidden = 3
    assert "private" not in json.dumps(lab_post_embed(data, data.stats)).lower()


def test_the_hidden_count_is_the_managers_on_the_web(org):
    briefing = DailyBriefing.objects.create(
        lab=org.lab, body="x", stats={"private_projects_hidden": 2, "entered": 1}
    )
    assert (
        _lab_envelope(briefing, org.pi, org.lab)["stats"]["private_projects_hidden"]
        == 2
    )
    member_stats = _lab_envelope(briefing, org.member, org.lab)["stats"]
    assert "private_projects_hidden" not in member_stats
    assert member_stats["entered"] == 1


# --------------------------------------------------------------------------- #
# Announcements: project teams, department posts, the send-time check
# --------------------------------------------------------------------------- #
def _target(kind, obj):
    row = AnnouncementSettings.objects.create(
        **({"target_lab": obj} if kind == "lab" else {"target_department": obj})
    )
    return announce.Target(kind, obj, row)


def test_announcement_teams_follow_the_widest_server(org):
    item = _content("Reef grant")
    for project in org.projects.values():
        _suggest(project, item)
    target = _target("lab", org.lab)

    _in_own_server(org)
    names = {t["name"] for t in announce._project_teams(target, item.id)}
    assert names == {"Project lab", "Project department", "Project public"}

    _in_department_server(org)  # now also posted into the department's server
    names = {t["name"] for t in announce._project_teams(target, item.id)}
    assert names == {"Project department", "Project public"}


def test_a_department_post_may_name_department_and_public_projects(org):
    item = _content("Dept grant")
    for project in [*org.projects.values(), org.sibling_project]:
        _suggest(project, item)
    target = _target("department", org.dept)
    row = RelevanceScore.objects.create(
        content=item, target_department=org.dept, score=0.9, signals={}
    )

    alignment = announce.align(target, row, [], labs=[])
    assert set(alignment["projects"]) == {
        "Project department",
        "Project public",
        "Kelp department",
    }
    # A department post names labs, never people.
    assert all(t["members"] == [] for t in alignment["project_teams"])

    # A department server that also holds a lab of another department is public.
    other = Department.objects.create(owner=org.head, name="Physics")
    bind(department=org.dept, guild_id="g-mixed")
    bind(
        lab=Lab.objects.create(name="Optics", slug="optics", department=other),
        guild_id="g-mixed",
    )
    alignment = announce.align(target, row, [], labs=[])
    assert alignment["projects"] == ["Project public"]


def test_a_thread_is_not_opened_in_a_server_too_wide_for_its_projects(org):
    own = bind(lab=org.lab, guild_id="g-own")
    in_dept = bind(lab=org.lab, guild_id="g-dept")
    bind(department=org.dept, guild_id="g-dept")
    ann = SimpleNamespace(
        alignment={"project_teams": [{"project_id": str(org.projects["lab"].id)}]}
    )
    assert discord_announcements.may_post_in(ann, own) is True
    assert discord_announcements.may_post_in(ann, in_dept) is False
    wide = SimpleNamespace(
        alignment={
            "project_teams": [{"project_id": str(org.projects["department"].id)}]
        }
    )
    assert discord_announcements.may_post_in(wide, in_dept) is True
    assert discord_announcements.may_post_in(SimpleNamespace(alignment={}), in_dept)


# --------------------------------------------------------------------------- #
# smoke_reports: one check per width
# --------------------------------------------------------------------------- #
def test_smoke_checks_each_width(org):
    today = timezone.localdate()
    _in_department_server(org)
    for width in ("lab", "department", "public"):
        assert (
            smoke_reports.check_place_width(today, width).status == smoke_reports.SKIP
        )

    DiscordOutboxMessage.objects.create(
        dedupe_key="lab_digest:x",
        kind="lab_digest",
        channel_id="dept-room",
        lab=org.lab,
        embed={"title": "Mentions Project department only"},
        target_type="channel",
        next_attempt_at=timezone.now(),
    )
    assert smoke_reports.check_place_width(today, "department").status == "PASS"

    DiscordOutboxMessage.objects.create(
        dedupe_key="lab_digest:y",
        kind="lab_digest",
        channel_id="dept-room",
        lab=org.lab,
        embed={"title": "Mentions Project lab"},
        target_type="channel",
        next_attempt_at=timezone.now(),
    )
    check = smoke_reports.check_place_width(today, "department")
    assert check.status == "FAIL" and "Project lab" in check.detail
    assert smoke_reports.check_place_width(today, "lab").status == smoke_reports.SKIP
