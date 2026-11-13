"""A department works like a lab (settings plan, Phase 3).

The four feeds, the daily briefing, the Discord post with its PDF and the Monday
weekly all reach a department through the lab's own functions — generalised to
take an org, not forked — and a department is scored on the lab's terms rather
than only while its announcements are on.
"""

from __future__ import annotations

from datetime import date

import pytest
from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
from apps.billing.models import AddOn, Subscription, SubscriptionAddOn, Tier
from apps.integrations.models import DiscordOutboxMessage
from apps.integrations.testing import bind
from apps.integrations.tests.base import clear_discord_cache, discord_test_settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery.briefing import generate_briefing_for_lab
from tools.delivery.daily_report import compile_report_for_lab
from tools.delivery.lab_digest import eligible_labs, queue_lab_digest, queue_lab_report
from tools.delivery.models import DailyBriefing
from tools.delivery.weekly import generate_weekly_for_lab
from tools.delivery.weekly_send import send_lab_weeklies
from tools.recommendation.models import RelevanceScore
from tools.recommendation.tasks import select_departments
from tools.retrieval.models import ContentItem

TODAY = timezone.now().date().isoformat()
POST_DAY = date(2026, 7, 16)


@pytest.fixture(autouse=True)
def _discord_settings():
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def _department(name="Earth Sciences", *, active=True) -> Department:
    head = User.objects.create_user(username=f"head-{name[:5].lower()}", password="p")
    department = Department.objects.create(owner=head, name=name)
    subscription = Subscription.objects.create(
        tier=Tier.CANOPY,
        scope_department=department,
        status=Subscription.Status.ACTIVE if active else Subscription.Status.INACTIVE,
    )
    # Mylo in the server is an add-on on the plan, for a department as for a lab.
    addon, _ = AddOn.objects.get_or_create(
        slug="bot_server",
        defaults={"name": "Mylo for your server", "feature": "bot_server"},
    )
    SubscriptionAddOn.objects.create(subscription=subscription, add_on=addon)
    return department


def _content(ctype: str, title: str) -> ContentItem:
    return ContentItem.objects.create(
        type=ctype, source="test", external_id=title, metadata={"title": title}
    )


def _dept_score(department, content, *, rank=1) -> RelevanceScore:
    return RelevanceScore.objects.create(
        content=content,
        target_department=department,
        score=0.8,
        signals={
            "suggested": True,
            "run_at": f"{TODAY}T06:00:00",
            "rank": rank,
            "headline": f"Headline {content.metadata['title']}",
            "reason": f"Why {content.metadata['title']} fits.",
            "verdict": "read",
            "first_seen": TODAY,
            "embedding_match": 0.8,
            "top_rank": rank,
            "entered_top_on": TODAY,
            "is_new_top": True,
            "cluster_slates": {
                "c-all": {
                    "label": "",
                    "rank": rank,
                    "entered_on": TODAY,
                    "is_new": True,
                }
            },
        },
    )


# --------------------------------------------------------------------------- #
# Scoring — on the lab's terms, not only while announcements are on
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_an_active_department_is_scored_with_announcements_off() -> None:
    active = _department("Earth Sciences")
    _department("Biology", active=False)

    assert select_departments(None) == [active]
    # A targeted run stays user-scoped, as it does for labs.
    assert select_departments(["someone"]) == []


@pytest.mark.django_db
def test_the_paper_run_scores_departments(monkeypatch) -> None:
    """Papers are added to the department run: the nightly paper pass hands its
    departments to the batch beside the labs."""
    from tools.recommendation.pipeline import BatchResult

    department = _department()
    sink: dict = {}

    def fake(users, *, labs=(), departments=(), projects=(), **kwargs):
        sink["departments"] = list(departments)
        return BatchResult()

    monkeypatch.setattr(
        "tools.recommendation.management.commands.run_daily_suggestions."
        "run_daily_batch",
        fake,
    )
    call_command("run_daily_suggestions", "--no-llm")

    assert sink["departments"] == [department]


@pytest.mark.django_db
def test_run_daily_batch_ranks_papers_for_a_department(monkeypatch) -> None:
    from tools.recommendation import pipeline

    department = _department()
    seen: list = []

    def fake_recommend(target, **kwargs):
        seen.append((target.kind, target.persist_kwargs))
        return pipeline.RunResult(target.key, "ok")

    monkeypatch.setattr(pipeline, "recommend_for_target", fake_recommend)
    pipeline.run_daily_batch([], departments=[department], embed=False)

    assert seen == [("department", {"target_department": department})]


@pytest.mark.django_db
def test_a_department_is_entitled_to_model_writeups_on_its_own_plan() -> None:
    from tools.recommendation.theme_run import target_is_entitled

    assert target_is_entitled({"target_department": _department("Physics")})
    assert not target_is_entitled(
        {"target_department": _department("Chemistry", active=False)}
    )


# --------------------------------------------------------------------------- #
# The daily briefing, through the lab's function
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_department_briefing_is_keyed_to_the_department() -> None:
    department = _department()
    _dept_score(department, _content(ContentItem.Type.PAPER, "Dept Paper"))
    _dept_score(department, _content(ContentItem.Type.GRANT, "Dept Grant"))

    briefing = generate_briefing_for_lab(
        department, complete=lambda system, user: "department body"
    )

    assert briefing.department_id == department.id
    assert briefing.lab_id is None and briefing.user_id is None
    assert briefing.counts.get("papers") == 1
    assert briefing.counts.get("grants") == 1
    # The org's own part is named after it, never "Personal".
    assert briefing.project_summary[0]["label"] == department.name
    assert DailyBriefing.latest_for(department=department) == briefing


@pytest.mark.django_db
def test_the_briefing_command_briefs_departments() -> None:
    department = _department()
    _dept_score(department, _content(ContentItem.Type.PAPER, "Dept Paper"))

    call_command("generate_daily_briefing")

    assert DailyBriefing.objects.filter(department=department).count() == 1


@pytest.mark.django_db
def test_a_department_report_covers_only_its_shared_projects() -> None:
    from apps.research.models import Project

    department = _department()
    Project.objects.create(
        name="Shared survey", scope_department=department, share_in_lab_reports=True
    )
    Project.objects.create(name="Private plan", scope_department=department)

    data = compile_report_for_lab(department)

    assert data.display_name == department.name
    assert data.personal.label == department.name
    assert [part.label for part in data.projects] == ["Shared survey"]
    assert data.private_projects_hidden == 1


# --------------------------------------------------------------------------- #
# The Discord post and its PDF
# --------------------------------------------------------------------------- #
def _bound_department(channel="dept-updates"):
    department = _department()
    bind(department=department, guild_id="g-dept", updates=channel)
    return department


@pytest.mark.django_db
def test_a_bound_department_is_eligible_for_a_daily_post() -> None:
    department = _bound_department()
    assert eligible_labs([department], on=POST_DAY) == [department]
    assert eligible_labs([_department("Unbound")], on=POST_DAY) == []


@pytest.mark.django_db
def test_a_department_post_and_pdf_go_to_its_updates_channel(tmp_path) -> None:
    department = _bound_department()
    _dept_score(department, _content(ContentItem.Type.PAPER, "Dept Paper"))

    data = compile_report_for_lab(department)
    _row, created = queue_lab_digest(department, on=POST_DAY, data=data)
    again = queue_lab_digest(department, on=POST_DAY, data=data)[1]
    attached = queue_lab_report(department, on=POST_DAY, data=data, workdir=tmp_path)

    assert created is True and again is False
    assert attached is True
    rows = list(DiscordOutboxMessage.objects.order_by("id"))
    assert [r.kind for r in rows] == ["dept_digest", "dept_report"]
    assert {r.channel_id for r in rows} == {"dept-updates"}
    assert all(r.lab_id is None for r in rows)
    assert rows[0].dedupe_key == f"dept_digest:{department.pk}:2026-07-16"


@pytest.mark.django_db
def test_the_digest_command_posts_for_departments(monkeypatch) -> None:
    department = _bound_department()
    _dept_score(department, _content(ContentItem.Type.PAPER, "Dept Paper"))
    monkeypatch.setattr(
        "tools.delivery.lab_digest.render_report_pdf", lambda data: b"%PDF-1.4"
    )

    call_command("send_lab_digests")

    kinds = set(DiscordOutboxMessage.objects.values_list("kind", flat=True))
    assert kinds == {"dept_digest", "dept_report"}


# --------------------------------------------------------------------------- #
# The Monday weekly
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_department_weekly_is_written_and_posted(monkeypatch, settings, tmp_path):
    settings.DISCORD_OUTBOX_ATTACHMENT_DIR = str(tmp_path)
    monkeypatch.setattr(
        "tools.delivery.weekly_send.render_report_pdf", lambda data: b"%PDF-1.4"
    )
    # A department has no cadence setting of its own yet, so it takes the daily
    # default; the channel weekly is what a weekly-cadence org receives instead.
    monkeypatch.setattr(
        "tools.delivery.delivery.lab_cadence", lambda target: "weekly"
    )
    department = _bound_department()
    _dept_score(department, _content(ContentItem.Type.PAPER, "Dept Paper"))
    monday = date(2026, 7, 13)

    weekly = generate_weekly_for_lab(
        department, complete=lambda system, user: None, today=monday
    )
    summary = send_lab_weeklies([department], on=monday)

    assert weekly.department_id == department.id
    assert weekly.kind == DailyBriefing.Kind.WEEKLY
    assert summary.sent == 1, summary.error_detail
    kinds = list(DiscordOutboxMessage.objects.values_list("kind", flat=True))
    assert kinds == ["dept_weekly", "dept_weekly"]


# --------------------------------------------------------------------------- #
# The feed endpoints
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_every_department_member_reads_its_four_feeds() -> None:
    department = _department()
    lab = Lab.objects.create(name="Geo Lab", slug="geo-lab", department=department)
    via_lab = User.objects.create_user(username="via-lab", password="p")
    LabMembership.objects.create(user=via_lab, lab=lab, role="member")
    direct = User.objects.create_user(username="direct", password="p")
    DeptMembership.objects.create(user=direct, department=department, role="member")
    outsider = User.objects.create_user(username="outsider", password="p")
    for ctype, title in (
        (ContentItem.Type.PAPER, "P"),
        (ContentItem.Type.GRANT, "G"),
        (ContentItem.Type.FELLOWSHIP, "F"),
        (ContentItem.Type.CONFERENCE, "C"),
    ):
        _dept_score(department, _content(ctype, title))

    url = f"/api/departments/{department.pk}/recommendations/"
    client = APIClient()
    for reader in (department.owner, direct, via_lab):
        client.force_authenticate(reader)
        response = client.get(url)
        assert response.status_code == 200, reader.username
        counts = response.data["counts"]
        # A conference with no dates is not live, so it never reaches a feed.
        assert set(counts) == {"papers", "grants", "conferences", "fellowships"}
        assert (counts["papers"], counts["grants"], counts["fellowships"]) == (
            1,
            1,
            1,
        )
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 403
    # The no-slash form is the same route.
    client.force_authenticate(direct)
    assert client.get(url.rstrip("/")).status_code == 200


@pytest.mark.django_db
def test_the_department_briefing_endpoints() -> None:
    department = _department()
    _dept_score(department, _content(ContentItem.Type.PAPER, "Dept Paper"))
    briefing = generate_briefing_for_lab(department, complete=lambda s, u: "body")
    member = User.objects.create_user(username="reader", password="p")
    DeptMembership.objects.create(user=member, department=department, role="member")
    client = APIClient()
    client.force_authenticate(member)

    current = client.get(f"/api/departments/{department.pk}/daily-briefing/")
    history = client.get(f"/api/departments/{department.pk}/briefings/")
    day = client.get(
        f"/api/departments/{department.pk}/briefings/"
        f"{briefing.generated_on.isoformat()}/"
    )

    assert current.status_code == 200 and current.data["briefing"]["body"]
    assert history.status_code == 200 and len(history.data) == 1
    assert day.status_code == 200

    client.force_authenticate(User.objects.create_user(username="x", password="p"))
    assert (
        client.get(f"/api/departments/{department.pk}/daily-briefing/").status_code
        == 403
    )
