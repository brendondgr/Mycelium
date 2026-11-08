"""Daily report → Discord DM: multipart upload, send path, and recipient gating.

The transport is faked (``discord_api._request``) so the real multipart body-building
runs — letting us assert the ``payload_json`` part carries ``allowed_mentions.parse ==
[]`` and the file part is present — without a live bot.
"""

from __future__ import annotations

import json

import pytest
from apps.integrations.models import DiscordIdentity
from apps.integrations.services import discord_api, outbox, resolve
from apps.integrations.services.discord_api import (
    RawResponse,
    create_message_with_attachment,
)
from django.contrib.auth.models import User

from tools.delivery.reminders_discord import send_personal_report


class _Transport:
    def __init__(self):
        self.calls: list[dict] = []
        self.dm = RawResponse(200, {"id": "dm-chan"})
        self.message = RawResponse(200, {"id": "msg-1"})

    def __call__(self, method, path, *, auth=None, json_body=None, raw_body=None, **kw):
        self.calls.append(
            {"path": path, "json_body": json_body, "raw_body": raw_body,
             "content_type": kw.get("content_type")}
        )
        if path == "/users/@me/channels":
            return self.dm
        if path.endswith("/messages"):
            return self.message
        return RawResponse(404, {})

    def last_message(self) -> dict:
        return [c for c in self.calls if c["path"].endswith("/messages")][-1]


@pytest.fixture
def transport(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    stub = _Transport()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


def _parse_payload_json(raw_body: bytes) -> dict:
    """Pull the payload_json part out of the multipart body."""
    text = raw_body.decode("utf-8", "replace")
    marker = 'name="payload_json"'
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[brace : i + 1])
    raise AssertionError("no payload_json object found")


# --------------------------------------------------------------------------- #
# Multipart building
# --------------------------------------------------------------------------- #
def test_attachment_body_is_multipart_with_parse_empty(transport) -> None:
    create_message_with_attachment(
        "chan",
        filename="report.pdf",
        file_bytes=b"%PDF-1.7 hello",
        content="@everyone look",
        embed={"title": "Report"},
    )
    call = transport.last_message()
    assert call["content_type"].startswith("multipart/form-data; boundary=")
    assert b'name="files[0]"; filename="report.pdf"' in call["raw_body"]
    assert b"%PDF-1.7 hello" in call["raw_body"]
    payload = _parse_payload_json(call["raw_body"])
    assert payload["allowed_mentions"] == {"parse": []}  # never pings @everyone
    assert payload["attachments"] == [{"id": 0, "filename": "report.pdf"}]
    assert payload["embeds"] == [{"title": "Report"}]


# --------------------------------------------------------------------------- #
# send_personal_report
# --------------------------------------------------------------------------- #
def _active_identity(user, *, dm_ok=True, channel="dm-chan", opt_out=False):
    return DiscordIdentity.objects.create(
        user=user,
        discord_user_id=f"snow-{user.id}",
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        state=DiscordIdentity.State.ACTIVE,
        dm_ok=dm_ok,
        dm_channel_id=channel,
        daily_report_opt_out=opt_out,
    )


@pytest.mark.django_db
def test_send_personal_report_dms_the_pdf(transport, tmp_path) -> None:
    """Queued now, so the bytes are read from disk when the drain gets to it."""
    user = User.objects.create_user("rpt")
    _active_identity(user)
    pdf = tmp_path / "mylo.pdf"
    pdf.write_bytes(b"%PDF-xyz")

    outcome = send_personal_report(
        user,
        title="Daily report",
        body="Mylo found 3 papers.",
        filename="mylo.pdf",
        attachment_path=str(pdf),
        dedupe_key="daily_report:1:2026-07-16",
    )
    assert outcome.ok and outcome.queued
    outbox.drain()

    call = transport.last_message()
    assert b"%PDF-xyz" in call["raw_body"]


@pytest.mark.django_db
def test_a_report_whose_file_vanished_is_not_retried_forever(
    transport, tmp_path
) -> None:
    """A missing attachment is permanent: no retry can conjure the bytes back."""
    from apps.integrations.models import DiscordOutboxMessage

    user = User.objects.create_user("gone")
    _active_identity(user)
    send_personal_report(
        user,
        title="t",
        body="b",
        filename="f.pdf",
        attachment_path=str(tmp_path / "never-written.pdf"),
        dedupe_key="daily_report:9:2026-07-16",
    )

    outbox.drain()

    row = DiscordOutboxMessage.objects.get()
    assert row.status == DiscordOutboxMessage.Status.FAILED
    assert row.last_error_reason == "attachment_gone"


@pytest.mark.django_db
def test_send_personal_report_unreachable_when_no_identity(transport) -> None:
    user = User.objects.create_user("noident")
    outcome = send_personal_report(
        user, title="t", body="b", filename="f.pdf",
        attachment_path="/tmp/x.pdf", dedupe_key="k1",
    )
    assert not outcome.ok
    assert outcome.unreachable


@pytest.mark.django_db
def test_send_personal_report_no_token_is_soft(monkeypatch, settings) -> None:
    settings.DISCORD_BOT_TOKEN = ""
    user = User.objects.create_user("notoken")
    _active_identity(user)
    outcome = send_personal_report(
        user, title="t", body="b", filename="f.pdf",
        attachment_path="/tmp/x.pdf", dedupe_key="k2",
    )
    assert not outcome.ok
    assert outcome.unreachable
    assert outcome.not_configured


# --------------------------------------------------------------------------- #
# Recipient gating (resolve boundary)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_report_recipient_filtering() -> None:
    ok = User.objects.create_user("ok")
    opted_out = User.objects.create_user("opted")
    blocked = User.objects.create_user("blocked")
    revoked = User.objects.create_user("revoked")
    nolink = User.objects.create_user("nolink")

    _active_identity(ok)
    _active_identity(opted_out, opt_out=True)
    _active_identity(blocked, dm_ok=False)
    DiscordIdentity.objects.create(
        user=revoked,
        discord_user_id="snow-rev",
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        state=DiscordIdentity.State.REVOKED,
    )

    ids = resolve.report_recipient_user_ids(
        [ok, opted_out, blocked, revoked, nolink]
    )
    assert ids == {ok.id}


@pytest.mark.django_db
def test_set_daily_report_opt_out_toggles() -> None:
    user = User.objects.create_user("toggler")
    identity = _active_identity(user)
    resolve.set_daily_report_opt_out(identity, opt_out=True)
    identity.refresh_from_db()
    assert identity.daily_report_opt_out is True
    assert resolve.report_recipient_user_ids([user]) == set()
    resolve.set_daily_report_opt_out(identity, opt_out=False)
    assert resolve.report_recipient_user_ids([user]) == {user.id}
