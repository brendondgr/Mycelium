"""Ambient Plan 11 — Microsoft Teams, over the same ledger.

Every activity carries a Bot Framework JWT, verified here against a key made
for the test (RS256, issuer, audience, expiry, and the serviceUrl claim);
the bot token is only ever sent to Microsoft's hosts; a team is remembered at
install; people and labs link with codes good on Teams only; messages pass
the same gate as every platform; Adaptive Card choices answer questions.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import timedelta
from unittest import mock

import pytest
from cryptography.hazmat.primitives import hashes, serialization  # noqa: F401
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient.models import (
    ListeningConsent,
    PendingSuggestion,
    Platform,
    RawMessageRef,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import TeamsIdentity, TeamsOutboxMessage, TeamsTeamLink
from apps.integrations.services import slack_link, teams_api, teams_auth, teams_outbox

APP_ID = "app-123"
SERVICE = "https://smba.trafficmanager.net/emea/"
TENANT = "tenant-1"
TEAM = "19:team@thread.tacv2"
BOT = "28:app-123"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwk():
    numbers = KEY.public_key().public_numbers()
    return {
        "kid": "k1",
        "kty": "RSA",
        "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64(numbers.e.to_bytes(3, "big")),
    }


def _token(**claims) -> str:
    now = time.time()
    body = {
        "iss": "https://api.botframework.com",
        "aud": APP_ID,
        "exp": now + 3600,
        "nbf": now - 60,
        "serviceurl": SERVICE,
        **claims,
    }
    header = _b64(json.dumps({"alg": "RS256", "kid": "k1", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(body).encode())
    signature = KEY.sign(
        f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    return f"Bearer {header}.{payload}.{_b64(signature)}"


@pytest.fixture(autouse=True)
def _on(settings):
    settings.TEAMS_ENABLED = True
    settings.TEAMS_APP_ID = APP_ID
    settings.AMBIENT_ENABLED = True


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setattr(teams_auth, "_keys", lambda refresh=False: {"k1": _jwk()})


@pytest.fixture
def ada(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    return user


def _post(client, activity, *, token=None):
    return client.post(
        "/api/integrations/teams/messages/",
        data=json.dumps({"serviceUrl": SERVICE, **activity}),
        content_type="application/json",
        HTTP_AUTHORIZATION=token if token is not None else _token(),
    )


def _message(text, *, personal=False, aad="aad-ada", entities=None, **more):
    return {
        "type": "message",
        "id": more.pop("id", f"m{time.time_ns()}"),
        "timestamp": "2026-09-17T14:00:00Z",
        "text": text,
        "from": {"id": "29:ada", "aadObjectId": aad},
        "recipient": {"id": BOT},
        "conversation": {
            "id": "a:personal-chat" if personal else f"{TEAM};messageid=1",
            "conversationType": "personal" if personal else "channel",
        },
        "channelData": {
            "tenant": {"id": TENANT},
            **({} if personal else {"team": {"id": TEAM}, "channel": {"id": "19:ch"}}),
        },
        "entities": entities or [],
        **more,
    }


def _link(user, *, opted_in=True):
    TeamsIdentity.objects.create(
        user=user,
        tenant_id=TENANT,
        aad_object_id="aad-ada",
        service_url=SERVICE,
        conversation_id="a:personal-chat",
    )
    if opted_in:
        ListeningConsent.objects.create(
            user=user, platform=Platform.TEAMS, enabled=True
        )


# -- the token -------------------------------------------------------------------


def test_a_valid_token_verifies():
    claims = teams_auth.verify(_token(), service_url=SERVICE)
    assert claims["aud"] == APP_ID


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"exp": time.time() - 3600},
        {"nbf": time.time() + 3600},
        {"serviceurl": "https://evil.example/"},
    ],
)
def test_a_wrong_claim_is_refused(claims):
    with pytest.raises(teams_auth.InvalidToken):
        teams_auth.verify(_token(**claims), service_url=SERVICE)


def test_a_forged_signature_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _token()
    header, payload, _sig = token[len("Bearer ") :].split(".")
    forged = other.sign(
        f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    with pytest.raises(teams_auth.InvalidToken):
        teams_auth.verify(
            f"Bearer {header}.{payload}.{_b64(forged)}", service_url=SERVICE
        )


def test_no_token_no_entry(client, db):
    assert _post(client, _message("hi"), token="").status_code == 401


def test_the_endpoint_is_closed_while_teams_is_off(client, settings, db):
    settings.TEAMS_ENABLED = False
    assert _post(client, _message("hi")).status_code == 404


def test_the_bot_token_goes_only_to_microsoft():
    assert teams_api.trusted_service_url(SERVICE)
    assert teams_api.trusted_service_url("https://smba.botframework.com/x")
    assert not teams_api.trusted_service_url("http://smba.trafficmanager.net/x")
    assert not teams_api.trusted_service_url("https://evil.example/")
    assert not teams_api.trusted_service_url("https://trafficmanager.net.evil.example/")
    with pytest.raises(teams_api.TeamsError):
        teams_api.send_activity("https://evil.example/", "c", token="t", text="x")


# -- install and linking --------------------------------------------------------------


def test_installing_in_a_team_remembers_it(client, db):
    _post(
        client,
        {
            "type": "conversationUpdate",
            "channelData": {
                "tenant": {"id": TENANT},
                "team": {"id": TEAM, "name": "PULSE"},
            },
            "conversation": {"id": TEAM},
        },
    )
    link = TeamsTeamLink.objects.get()
    assert (link.team_id, link.service_url, link.name) == (TEAM, SERVICE, "PULSE")


def test_a_person_links_from_their_personal_chat(client, ada):
    code = slack_link.issue(user=ada, platform="teams")
    with mock.patch("apps.integrations.tasks.teams_dialogue.delay"):
        _post(client, _message(f"link {code}", personal=True))
    identity = TeamsIdentity.objects.get()
    assert identity.user == ada and identity.conversation_id == "a:personal-chat"
    assert "Linked" in TeamsOutboxMessage.objects.get().text


def test_a_slack_code_does_not_link_on_teams(client, ada):
    code = slack_link.issue(user=ada)  # a Slack code
    _post(client, _message(f"link {code}", personal=True))
    assert not TeamsIdentity.objects.exists()


def test_a_lab_links_its_team_from_a_channel(client, ada):
    TeamsTeamLink.objects.create(team_id=TEAM, tenant_id=TENANT, service_url=SERVICE)
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    code = slack_link.issue(user=ada, lab=lab, platform="teams")
    _post(
        client,
        _message(
            f"<at>Mylo</at> {code}",
            entities=[{"type": "mention", "mentioned": {"id": BOT}}],
        ),
    )
    link = TeamsTeamLink.objects.get()
    assert link.lab == lab and link.updates_conversation_id.startswith(TEAM)


# -- recording ----------------------------------------------------------------------


def test_a_channel_message_passes_the_same_gate(client, ada):
    from apps.ambient.service import set_team_listening

    _link(ada)
    TeamsTeamLink.objects.create(team_id=TEAM, tenant_id=TENANT, service_url=SERVICE)
    set_team_listening(TEAM, on=True)
    _post(client, _message("I want to try conformal prediction on the <b>scans</b>."))
    ref = RawMessageRef.objects.get()
    assert ref.speaker == ada and ref.source.kind == "teams_team"


def test_not_opted_in_on_teams_means_nothing_is_kept(client, ada):
    from apps.ambient.service import set_team_listening

    _link(ada, opted_in=False)
    ListeningConsent.objects.create(user=ada, platform=Platform.SLACK, enabled=True)
    set_team_listening(TEAM, on=True)
    _post(client, _message("I want to try conformal prediction on the scans."))
    assert not RawMessageRef.objects.exists()


def test_a_group_chat_is_not_listened_to(client, ada):
    _link(ada)
    activity = _message("anything at all worth reading here")
    activity["conversation"]["conversationType"] = "groupChat"
    _post(client, activity)
    assert not RawMessageRef.objects.exists()


def test_a_personal_message_is_recorded_and_read_as_a_turn(client, ada):
    _link(ada)
    with mock.patch("apps.integrations.tasks.teams_dialogue.delay") as later:
        _post(client, _message("yes please", personal=True, id="p1"))
    ref = RawMessageRef.objects.get()
    assert ref.source.kind == "teams_chat"
    later.assert_called_once_with(
        TENANT, "aad-ada", SERVICE, "a:personal-chat", "p1", "yes please"
    )


def test_a_deletion_reconciles(client, ada):
    from apps.ambient.service import set_team_listening

    _link(ada)
    set_team_listening(TEAM, on=True)
    _post(client, _message("I want to try conformal prediction on the scans.", id="d1"))
    _post(
        client,
        {
            "type": "messageDelete",
            "id": "d1",
            "conversation": {
                "id": f"{TEAM};messageid=1",
                "conversationType": "channel",
            },
            "channelData": {"tenant": {"id": TENANT}, "team": {"id": TEAM}},
            "from": {"aadObjectId": "aad-ada"},
        },
    )
    assert RawMessageRef.objects.get().deleted_at is not None


# -- the dialogue ---------------------------------------------------------------------


def test_an_adaptive_card_choice_answers_the_question(client, ada):
    _link(ada)
    s = PendingSuggestion.objects.create(
        user=ada,
        kind="interest",
        topic="kriging",
        state="asked",
        choices=[{"key": "no", "label": "No"}],
        asked_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=14),
    )
    _post(client, _message("", personal=True, value={"ambient": f"{s.pk}:no"}))
    s.refresh_from_db()
    assert s.state == "answered" and s.verdict == "rejected"
    assert TeamsOutboxMessage.objects.get().kind == "ambient_reply"


def test_the_outbox_delivers_retries_and_gives_up(ada):
    _link(ada)
    teams_outbox.enqueue_dm(user=ada, dedupe_key="a", kind="t", text="x")
    teams_outbox.enqueue_dm(user=ada, dedupe_key="b", kind="t", text="y")

    def send(row):
        if row.dedupe_key == "a":
            raise teams_api.TeamsError("http_503", 503)
        return "id"

    counts = teams_outbox.drain(send=send)
    assert (counts["sent"], counts["retried"]) == (1, 1)
    assert TeamsOutboxMessage.objects.get(dedupe_key="a").status == "pending"


def test_a_teams_only_person_can_be_asked(ada):
    from apps.ambient import dialogue

    _link(ada)
    monday = timezone.now()
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    assert dialogue.askable(ada, now=monday) == (True, "")
