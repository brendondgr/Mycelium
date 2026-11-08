"""Ambient Plan 11 on the content side: reports and questions reach Slack.

A person linked only on Slack gets their report and Mylo's questions there; a
person on both keeps Discord; a lab whose Slack workspace is primary gets its
posts there and not on Discord; while Slack is off, nothing is queued.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from apps.accounts.models import Lab
from apps.ambient.models import PendingSuggestion
from apps.integrations.models import (
    DiscordIdentity,
    SlackIdentity,
    SlackOutboxMessage,
    SlackWorkspace,
)
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from tools.delivery import slack_reports

TUESDAY = date(2026, 9, 22)


@pytest.fixture(autouse=True)
def _on(settings):
    settings.SLACK_ENABLED = True
    settings.AMBIENT_ENABLED = True


@pytest.fixture
def workspace(db):
    return SlackWorkspace.objects.create(
        team_id="T1", bot_token="xoxb", bot_user_id="UBOT"
    )


def _slack_person(name="ada"):
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    SlackIdentity.objects.create(user=user, team_id="T1", slack_user_id=f"U{name}")
    return user


def test_an_embed_becomes_block_kit():
    blocks = slack_reports.embed_to_blocks(
        {
            "title": "Your daily research report · 2026-09-22",
            "description": "**Two** papers — see [the list](https://example.org/x).",
            "fields": [{"name": "Needs attention (1)", "value": "Synapse · overlap"}],
        },
        link="https://example.org/app/reports",
    )
    assert blocks[0]["type"] == "header"
    assert (
        blocks[1]["text"]["text"]
        == "*Two* papers — see <https://example.org/x|the list>."
    )
    assert blocks[2]["text"]["text"].startswith("*Needs attention (1)*\n")
    assert blocks[-1]["elements"][0]["url"] == "https://example.org/app/reports"


def test_a_slack_only_reader_gets_their_daily_on_slack(workspace, monkeypatch):
    ada = _slack_person()
    monkeypatch.setattr("tools.recommendation.tasks.select_users", lambda _names: [ada])
    monkeypatch.setattr(
        "tools.delivery.daily_report.compile_report_for_user",
        lambda _user: SimpleNamespace(stats=SimpleNamespace(is_quiet=False)),
    )
    monkeypatch.setattr(
        "tools.delivery.discord_embeds.personal_report_embed",
        lambda *_a, **_k: {"title": "Your daily research report", "fields": []},
    )
    counts = slack_reports.send(on=TUESDAY)
    assert counts["people"] == 1
    row = SlackOutboxMessage.objects.get()
    assert row.recipient_user == ada and row.target_type == "dm"
    assert row.dedupe_key == f"slack_daily_report:{ada.pk}:2026-09-22"
    # Re-running is a no-op.
    assert slack_reports.send(on=TUESDAY)["people"] == 0


def test_a_reader_on_both_platforms_keeps_discord(workspace, monkeypatch):
    ada = _slack_person()
    DiscordIdentity.objects.create(
        user=ada,
        discord_user_id="111",
        link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        state=DiscordIdentity.State.ACTIVE,
    )
    monkeypatch.setattr("tools.recommendation.tasks.select_users", lambda _names: [ada])
    assert slack_reports.send(on=TUESDAY)["people"] == 0


def test_nothing_is_queued_while_slack_is_off(settings, workspace):
    settings.SLACK_ENABLED = False
    assert slack_reports.send(on=TUESDAY) == {"enabled": False}
    assert not SlackOutboxMessage.objects.exists()


def test_a_lab_whose_slack_is_primary_is_skipped_on_discord(workspace, monkeypatch):
    from tools.delivery.lab_digest import eligible_labs

    lab = Lab.objects.create(name="PULSE", slug="pulse")
    workspace.lab = lab
    workspace.updates_channel_id = "CREPORTS"
    workspace.reports_primary = True
    workspace.save()
    monkeypatch.setattr(
        "apps.billing.entitlements.lab_has_feature", lambda *_a, **_k: True
    )
    assert slack_reports.slack_is_primary(lab)
    assert eligible_labs([lab], on=TUESDAY) == []


def test_a_lab_with_no_discord_channel_posts_to_slack(workspace, monkeypatch):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    workspace.lab = lab
    workspace.updates_channel_id = "CREPORTS"
    workspace.save()
    monkeypatch.setattr(
        "apps.billing.entitlements.lab_has_feature", lambda *_a, **_k: True
    )
    monkeypatch.setattr("tools.recommendation.tasks.select_users", lambda _names: [])
    monkeypatch.setattr(
        "tools.delivery.daily_report.compile_report_for_lab",
        lambda _lab: SimpleNamespace(stats=SimpleNamespace(is_quiet=False)),
    )
    monkeypatch.setattr(
        "tools.delivery.discord_embeds.lab_post_embed",
        lambda *_a, **_k: {"title": "PULSE · Mylo daily", "fields": []},
    )
    assert slack_reports.send(on=TUESDAY)["labs"] == 1
    row = SlackOutboxMessage.objects.get()
    assert row.target_type == "channel" and row.channel_id == "CREPORTS"


def test_a_slack_only_person_is_asked_on_slack_with_buttons(workspace):
    ada = _slack_person()
    PendingSuggestion.objects.create(
        user=ada,
        kind="interest",
        topic="kriging",
        explanation="You brought this up on two days.",
        choices=[
            {"key": "reports", "label": "Include it in my reports"},
            {"key": "no", "label": "No"},
        ],
        expires_at=timezone.now() + timedelta(days=14),
    )
    call_command("deliver_ambient_questions")
    row = SlackOutboxMessage.objects.get()
    assert row.kind == "ambient_question" and row.recipient_user == ada
    [section, actions] = row.blocks
    assert "*kriging*" in section["text"]["text"]
    ids = [button["action_id"] for button in actions["elements"]]
    s = PendingSuggestion.objects.get()
    assert ids == [f"ambient:{s.pk}:reports", f"ambient:{s.pk}:no"]
    assert s.state == "asked"


# -- Teams -----------------------------------------------------------------------


def _teams_person(name="tia"):
    from apps.integrations.models import TeamsIdentity

    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    TeamsIdentity.objects.create(
        user=user,
        tenant_id="t1",
        aad_object_id=f"aad-{name}",
        service_url="https://smba.trafficmanager.net/x/",
        conversation_id=f"a:{name}",
    )
    return user


def test_a_teams_only_reader_gets_their_daily_in_teams(settings, monkeypatch, db):
    from apps.integrations.models import TeamsOutboxMessage

    settings.SLACK_ENABLED = False
    settings.TEAMS_ENABLED = True
    tia = _teams_person()
    monkeypatch.setattr("tools.recommendation.tasks.select_users", lambda _names: [tia])
    monkeypatch.setattr(
        "tools.delivery.daily_report.compile_report_for_user",
        lambda _user: SimpleNamespace(stats=SimpleNamespace(is_quiet=False)),
    )
    monkeypatch.setattr(
        "tools.delivery.discord_embeds.personal_report_embed",
        lambda *_a, **_k: {"title": "Your daily research report", "fields": []},
    )
    assert slack_reports.send(on=TUESDAY)["people"] == 1
    row = TeamsOutboxMessage.objects.get()
    assert row.conversation_id == "a:tia" and "Read the full report" in row.text


def test_a_lab_whose_team_is_primary_is_skipped_on_discord(settings, monkeypatch, db):
    from apps.integrations.models import TeamsTeamLink

    from tools.delivery.lab_digest import eligible_labs

    settings.TEAMS_ENABLED = True
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    TeamsTeamLink.objects.create(
        team_id="19:t",
        tenant_id="t1",
        service_url="https://smba.trafficmanager.net/x/",
        lab=lab,
        updates_conversation_id="19:t;messageid=1",
        reports_primary=True,
    )
    monkeypatch.setattr(
        "apps.billing.entitlements.lab_has_feature", lambda *_a, **_k: True
    )
    assert slack_reports.slack_is_primary(lab)
    assert eligible_labs([lab], on=TUESDAY) == []


def test_a_teams_only_person_is_asked_with_an_adaptive_card(settings, db):
    from apps.integrations.models import TeamsOutboxMessage

    tia = _teams_person()
    PendingSuggestion.objects.create(
        user=tia,
        kind="interest",
        topic="kriging",
        explanation="You brought this up on two days.",
        choices=[{"key": "reports", "label": "Include it in my reports"}],
        expires_at=timezone.now() + timedelta(days=14),
    )
    call_command("deliver_ambient_questions")
    row = TeamsOutboxMessage.objects.get()
    [card] = row.attachments
    s = PendingSuggestion.objects.get()
    assert card["content"]["actions"][0]["data"] == {"ambient": f"{s.pk}:reports"}
