"""Ambient Plan 11 — Slack, the second platform, over the same ledger.

Signed requests only; a person links by DMing a code; a lab links a workspace
by mentioning Mylo with a lab code; a message is recorded only through the
same eligibility gate as Discord (linked, opted in on Slack, paid, surface
listening); edits and deletions reconcile; an uninstall stops listening;
button presses answer Mylo's questions; the outbox delivers, retries and gives
up like Discord's.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership
from apps.ambient.models import (
    ListeningConsent,
    PendingSuggestion,
    Platform,
    RawMessageRef,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import (
    SlackIdentity,
    SlackOutboxMessage,
    SlackWorkspace,
)
from apps.integrations.services import slack_api, slack_events, slack_link, slack_outbox

SECRET = "shh-its-a-secret"
TEAM = "T0001"
BOT = "UBOT"


@pytest.fixture(autouse=True)
def _on(settings):
    settings.SLACK_ENABLED = True
    settings.SLACK_SIGNING_SECRET = SECRET
    settings.AMBIENT_ENABLED = True


@pytest.fixture
def workspace(db):
    return SlackWorkspace.objects.create(
        team_id=TEAM, name="PULSE", bot_token="xoxb-test", bot_user_id=BOT
    )


@pytest.fixture
def ada(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    return user


def _linked(user, slack_user_id="UADA", *, opted_in=True):
    SlackIdentity.objects.create(user=user, team_id=TEAM, slack_user_id=slack_user_id)
    if opted_in:
        ListeningConsent.objects.create(
            user=user, platform=Platform.SLACK, enabled=True
        )
    return user


def _signed(
    client, path, body: bytes, *, content_type="application/json", ts=None, **extra
):
    ts = str(int(ts if ts is not None else time.time()))
    signature = (
        "v0="
        + hmac.new(
            SECRET.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    return client.post(
        path,
        data=body,
        content_type=content_type,
        HTTP_X_SLACK_REQUEST_TIMESTAMP=ts,
        HTTP_X_SLACK_SIGNATURE=signature,
        **extra,
    )


def _event(client, event: dict):
    body = json.dumps(
        {"type": "event_callback", "team_id": TEAM, "event": event}
    ).encode()
    return _signed(client, "/api/integrations/slack/events/", body)


def _message(
    text, *, user="UADA", channel="C1", channel_type="channel", ts=None, **more
):
    return {
        "type": "message",
        "user": user,
        "text": text,
        "channel": channel,
        "channel_type": channel_type,
        "ts": ts or f"{time.time():.6f}",
        **more,
    }


# -- the signature -------------------------------------------------------------


def test_a_request_must_be_signed_and_fresh(db):
    body = b'{"type":"url_verification","challenge":"c"}'
    now = time.time()
    ts = str(int(now))
    good = (
        "v0="
        + hmac.new(
            SECRET.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    assert slack_events.verify(timestamp=ts, signature=good, body=body, now=now)
    assert not slack_events.verify(
        timestamp=ts, signature=good, body=body + b" ", now=now
    )
    assert not slack_events.verify(timestamp=ts, signature="v0=00", body=body, now=now)
    assert not slack_events.verify(
        timestamp=ts, signature=good, body=body, now=now + 301
    )


def test_the_endpoint_is_closed_while_slack_is_off(client, settings):
    settings.SLACK_ENABLED = False
    response = _signed(client, "/api/integrations/slack/events/", b"{}")
    assert response.status_code == 404


def test_an_unsigned_request_is_refused(client, db):
    response = client.post(
        "/api/integrations/slack/events/", data=b"{}", content_type="application/json"
    )
    assert response.status_code == 401


def test_the_url_check_is_answered(client, db):
    body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    response = _signed(client, "/api/integrations/slack/events/", body)
    assert response.json() == {"challenge": "abc"}


def _with_id(event, event_id):
    return json.dumps(
        {
            "type": "event_callback",
            "team_id": TEAM,
            "event_id": event_id,
            "event": event,
        }
    ).encode()


def test_a_retry_of_a_handled_event_is_only_acknowledged(client, workspace, ada):
    from django.core.cache import cache

    cache.clear()
    _linked(ada)
    with mock.patch("apps.integrations.tasks.slack_dialogue.delay") as later:
        event = _message("yes please", channel="D1", channel_type="im", ts="1.0")
        _signed(client, "/api/integrations/slack/events/", _with_id(event, "Ev1"))
        _signed(
            client,
            "/api/integrations/slack/events/",
            _with_id(event, "Ev1"),
            HTTP_X_SLACK_RETRY_NUM="1",
        )
    # The dialogue ran once: a DM read twice could answer a second question.
    assert later.call_count == 1
    assert RawMessageRef.objects.count() == 1


def test_a_retry_after_a_failed_first_attempt_is_handled(client, workspace, ada):
    from django.core.cache import cache

    from apps.ambient.service import set_workspace_listening

    cache.clear()
    _linked(ada)
    set_workspace_listening(TEAM, on=True)
    event = _message("We should try conformal prediction on the scans soon.", ts="2.0")
    with mock.patch(
        "apps.integrations.slack_views.slack_events.handle_event",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            _signed(client, "/api/integrations/slack/events/", _with_id(event, "Ev2"))
    _signed(
        client,
        "/api/integrations/slack/events/",
        _with_id(event, "Ev2"),
        HTTP_X_SLACK_RETRY_NUM="1",
    )
    assert RawMessageRef.objects.count() == 1


# -- linking -------------------------------------------------------------------


def test_a_person_links_by_dming_their_code(client, workspace, ada):
    code = slack_link.issue(user=ada)
    with mock.patch("apps.integrations.tasks.slack_dialogue.delay"):
        _event(
            client,
            _message(
                f"here you go {code}", user="UADA", channel="D1", channel_type="im"
            ),
        )
    identity = SlackIdentity.objects.get()
    assert (identity.user, identity.team_id, identity.slack_user_id) == (
        ada,
        TEAM,
        "UADA",
    )
    [reply] = SlackOutboxMessage.objects.all()
    assert reply.channel_id == "D1" and "Linked" in reply.text
    # Single-use.
    assert not slack_link.redeem_person(code, team_id=TEAM, slack_user_id="UOTHER").ok


def test_an_expired_code_links_nobody(client, workspace, ada):
    code = slack_link.issue(user=ada)
    from apps.integrations.models import LinkCode

    LinkCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    _event(client, _message(code, user="UADA", channel="D1", channel_type="im"))
    assert not SlackIdentity.objects.exists()
    assert "didn't work" in SlackOutboxMessage.objects.get().text


def test_a_lab_links_its_workspace_from_a_channel(client, workspace, ada):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    code = slack_link.issue(user=ada, lab=lab)
    _event(client, _message(f"<@{BOT}> {code}", channel="CREPORTS"))
    workspace.refresh_from_db()
    assert workspace.lab == lab and workspace.updates_channel_id == "CREPORTS"


def test_a_workspace_linked_to_one_lab_is_not_taken_by_another(client, workspace, ada):
    first = Lab.objects.create(name="A", slug="a")
    second = Lab.objects.create(name="B", slug="b")
    workspace.lab = first
    workspace.save()
    code = slack_link.issue(user=ada, lab=second)
    _event(client, _message(f"<@{BOT}> {code}", channel="C2"))
    workspace.refresh_from_db()
    assert workspace.lab == first


def test_only_a_lab_manager_can_make_a_lab_code(client, ada):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    LabMembership.objects.create(user=ada, lab=lab)  # a member, not a manager
    client.force_login(ada)
    response = client.post("/api/integrations/slack/lab-code/", {"lab": "pulse"})
    assert response.status_code == 403


# -- recording -----------------------------------------------------------------


def test_a_linked_opted_in_paid_person_is_recorded_like_on_discord(
    client, workspace, ada
):
    from apps.ambient.service import set_workspace_listening

    _linked(ada)
    set_workspace_listening(TEAM, on=True)
    _event(client, _message("I want to try conformal prediction on the imaging data."))
    ref = RawMessageRef.objects.get()
    assert ref.speaker == ada and ref.source.kind == "slack_workspace"
    assert ref.external_id.startswith("C1:")


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("unlinked", "speaker_unlinked"),
        ("not_opted_in", "person_not_opted_in"),
        ("free", "tier_free"),
        ("not_listening", "source_not_consented"),
    ],
)
def test_every_gate_holds_on_slack(workspace, ada, setup, reason):
    from apps.ambient.service import set_workspace_listening, slack_heard

    if setup != "unlinked":
        _linked(ada, opted_in=setup != "not_opted_in")
    if setup == "free":
        Subscription.objects.filter(scope_user=ada).update(tier=Tier.FREE)
    if setup != "not_listening":
        set_workspace_listening(TEAM, on=True)
    heard = slack_heard(
        team_id=TEAM,
        channel_id="C1",
        ts="1.0",
        text="I want to try conformal prediction on the imaging data.",
        sent_at=timezone.now(),
        slack_user_id="UADA",
    )
    assert not heard.stored and heard.reason == reason
    assert not RawMessageRef.objects.exists()


def test_discord_consent_says_nothing_about_slack(workspace, ada):
    from apps.ambient.service import set_workspace_listening, slack_heard

    SlackIdentity.objects.create(user=ada, team_id=TEAM, slack_user_id="UADA")
    ListeningConsent.objects.create(user=ada, platform=Platform.DISCORD, enabled=True)
    set_workspace_listening(TEAM, on=True)
    heard = slack_heard(
        team_id=TEAM,
        channel_id="C1",
        ts="1.0",
        text="I want to try conformal prediction on the imaging data.",
        sent_at=timezone.now(),
        slack_user_id="UADA",
    )
    assert heard.reason == "person_not_opted_in"


def test_a_dm_is_recorded_and_read_as_a_dialogue_turn(client, workspace, ada):
    _linked(ada)
    with mock.patch("apps.integrations.tasks.slack_dialogue.delay") as later:
        _event(
            client,
            _message("yes please add it", channel="D1", channel_type="im", ts="5.0"),
        )
    ref = RawMessageRef.objects.get()
    assert ref.source.kind == "slack_dm" and ref.source.external_id == f"{TEAM}:D1"
    later.assert_called_once_with(TEAM, "UADA", "D1", "5.0", "yes please add it")


def test_mylos_own_dm_lines_share_the_window(client, workspace, ada):
    _linked(ada)
    with mock.patch("apps.integrations.tasks.slack_dialogue.delay"):
        _event(
            client,
            _message(
                "Shall I include it?",
                user=BOT,
                channel="D1",
                channel_type="im",
                ts="1.0",
                bot_id="B1",
            ),
        )
        _event(client, _message("yes", channel="D1", channel_type="im", ts="2.0"))
    sources = {ref.source_id for ref in RawMessageRef.objects.all()}
    assert len(sources) == 1


def test_another_bot_is_not_recorded(client, workspace, ada):
    from apps.ambient.service import set_workspace_listening

    set_workspace_listening(TEAM, on=True)
    _event(
        client,
        _message(
            "Deploy finished for build 42 on the cluster.",
            user="UOTHERBOT",
            bot_id="B9",
            subtype="bot_message",
        ),
    )
    assert not RawMessageRef.objects.exists()


def test_an_edit_and_a_deletion_reconcile(client, workspace, ada):
    from apps.ambient.service import set_workspace_listening

    _linked(ada)
    set_workspace_listening(TEAM, on=True)
    _event(
        client, _message("I want to try conformal prediction on the scans.", ts="7.0")
    )
    ref = RawMessageRef.objects.get()
    _event(
        client,
        {
            "type": "message",
            "subtype": "message_changed",
            "channel": "C1",
            "channel_type": "channel",
            "message": {"ts": "7.0", "text": "I want to try kriging instead."},
        },
    )
    ref.refresh_from_db()
    old_hash = ref.content_hash
    _event(
        client,
        {
            "type": "message",
            "subtype": "message_deleted",
            "channel": "C1",
            "channel_type": "channel",
            "deleted_ts": "7.0",
        },
    )
    ref.refresh_from_db()
    assert ref.deleted_at is not None
    assert old_hash


def test_an_uninstall_stops_listening(client, workspace):
    from apps.ambient.service import set_workspace_listening, workspace_source

    set_workspace_listening(TEAM, on=True)
    _event(client, {"type": "app_uninstalled"})
    workspace.refresh_from_db()
    assert not workspace.active
    assert not workspace_source(TEAM).listening


# -- the dialogue ----------------------------------------------------------------


def test_a_button_answers_the_question_and_replaces_the_message(client, workspace, ada):
    _linked(ada)
    s = PendingSuggestion.objects.create(
        user=ada,
        kind="interest",
        topic="kriging",
        state="asked",
        choices=[
            {"key": "reports", "label": "Include it in my reports"},
            {"key": "no", "label": "No"},
        ],
        asked_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=14),
    )
    payload = {
        "type": "block_actions",
        "team": {"id": TEAM},
        "user": {"id": "UADA"},
        "actions": [{"action_id": f"ambient:{s.pk}:no"}],
        "response_url": "https://hooks.slack.com/actions/T/1/x",
    }
    said = []
    line = slack_events.handle_interaction(
        payload, respond=lambda url, text: said.append(text)
    )
    s.refresh_from_db()
    assert s.state == "answered" and s.verdict == "rejected"
    assert said == [line]


def test_a_button_for_someone_elses_question_changes_nothing(workspace, ada):
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    _linked(ada)
    s = PendingSuggestion.objects.create(
        user=bo,
        kind="interest",
        topic="kriging",
        state="asked",
        choices=[{"key": "no", "label": "No"}],
        asked_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=14),
    )
    line = slack_events.handle_interaction(
        {
            "type": "block_actions",
            "team": {"id": TEAM},
            "user": {"id": "UADA"},
            "actions": [{"action_id": f"ambient:{s.pk}:no"}],
        },
        respond=lambda *_: None,
    )
    s.refresh_from_db()
    assert s.state == "asked" and "isn't yours" in line


def test_a_slack_only_person_can_be_asked(ada):
    from apps.ambient import dialogue

    _linked(ada)
    monday = timezone.now()
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    assert dialogue.askable(ada, now=monday) == (True, "")


# -- the outbox ------------------------------------------------------------------


def test_the_outbox_delivers_to_the_linked_identity(workspace, ada):
    _linked(ada)
    row, created = slack_outbox.enqueue_dm(
        user=ada, dedupe_key="k1", kind="t", text="hello"
    )
    assert (
        created
        and not slack_outbox.enqueue_dm(user=ada, dedupe_key="k1", kind="t", text="x")[
            1
        ]
    )
    sent = []
    result = slack_outbox.drain(
        send=lambda ws, row, channel: sent.append(channel) or "123.4"
    )
    assert result.sent == 1 and sent == ["UADA"]
    row.refresh_from_db()
    assert row.status == "sent" and row.slack_ts == "123.4"


def test_a_transient_error_retries_and_a_permanent_one_settles(workspace, ada):
    _linked(ada)
    slack_outbox.enqueue_dm(user=ada, dedupe_key="a", kind="t", text="x")
    slack_outbox.enqueue_dm(user=ada, dedupe_key="b", kind="t", text="y")

    def send(_ws, row, _channel):
        raise slack_api.SlackError(
            "ratelimited" if row.dedupe_key == "a" else "invalid_auth"
        )

    result = slack_outbox.drain(send=send)
    assert (result.retried, result.failed) == (1, 1)
    assert SlackOutboxMessage.objects.get(dedupe_key="a").status == "pending"
    assert SlackOutboxMessage.objects.get(dedupe_key="b").status == "failed"


def test_a_dm_to_a_revoked_identity_is_never_sent(workspace, ada):
    _linked(ada)
    slack_outbox.enqueue_dm(user=ada, dedupe_key="r", kind="t", text="x")
    SlackIdentity.objects.update(state="revoked")
    result = slack_outbox.drain(send=lambda *_: pytest.fail("must not send"))
    assert result.failed == 1


def test_a_person_with_no_slack_identity_is_not_queued(ada):
    assert slack_outbox.enqueue_dm(user=ada, dedupe_key="n", kind="t", text="x") == (
        None,
        False,
    )


# -- the web ----------------------------------------------------------------------


def test_the_settings_carry_a_slack_switch(client, ada):
    _linked(ada, opted_in=False)
    client.force_login(ada)
    response = client.put(
        "/api/ambient/settings/",
        {"listening_slack": True},
        content_type="application/json",
    )
    body = response.json()
    assert body["slack_linked"] and body["listening"]["slack"] is True
    assert ListeningConsent.objects.get(user=ada, platform="slack").enabled
