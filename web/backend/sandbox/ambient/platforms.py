"""EXP-2026-09-021: does a second and third platform change anything past the
adapter? (ambient Plan 11)

The same corpus is replayed three times, each inside a transaction that is
rolled back, so each platform starts from the same seeded world:

- **Discord**, through the gateway door (``service.heard``), as every
  earlier experiment did;
- **Slack**, as signed Events API requests to the real endpoint;
- **Teams**, as Bot Framework activities with a real RS256 token (a key made
  here), to the real endpoint.

For each platform the mirror of the world is built: the same people linked
(a Slack or Teams identity for each Discord one), the same opt-ins on that
platform, and the same surfaces listening. What is compared is read back
from the ledger itself — the messages kept, by speaker and content hash, and
the drop counters by reason — never from the platforms' own return values.

One difference is expected and reported rather than hidden: Teams does not
deliver a bot's own messages back to it, so Mylo's lines in a personal chat
are not buffered there.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import Counter
from unittest import mock

from django.conf import settings
from django.db import transaction

from .world import World

SIGNING = "sandbox-signing-secret"
APP_ID = "sandbox-teams-app"
SERVICE = "https://smba.trafficmanager.net/sandbox/"
BOT_SLACK = "UMYLO"
BOT_TEAMS = "28:sandbox-teams-app"


class _Rollback(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _teams_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {
        "kid": "sandbox",
        "kty": "RSA",
        "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64(numbers.e.to_bytes(3, "big")),
    }
    return key, {"sandbox": jwk}


def _teams_token(key) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    now = time.time()
    header = _b64(json.dumps({"alg": "RS256", "kid": "sandbox"}).encode())
    payload = _b64(
        json.dumps(
            {
                "iss": settings.TEAMS_TOKEN_ISSUER,
                "aud": APP_ID,
                "exp": now + 3600,
                "nbf": now - 60,
                "serviceurl": SERVICE,
            }
        ).encode()
    )
    signature = key.sign(
        f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    return f"Bearer {header}.{payload}.{_b64(signature)}"


def _messages(world: World, written: list[dict]):
    """Every message, as (id, lab, place, day-hour-minute, speaker or None,
    is_mylo, dm_person, text). Unknown speakers are kept: the unlinked drop is
    part of what is compared."""
    from .run import _when

    names = {(lab.slug, p.name): p for lab in world.labs for p in lab.people}
    hour_of: dict[tuple, int] = {}
    for conv in written:
        slot = (conv["lab"], conv["day"], conv["place"])
        hour = 9 + 2 * hour_of.get(slot, 0)
        hour_of[slot] = hour_of.get(slot, 0) + 1
        for index, message in enumerate(conv["messages"]):
            is_mylo = message["speaker"] == "Mylo"
            person = names.get((conv["lab"], message["speaker"]))
            yield {
                "id": f"{conv['id']}#{index}",
                "lab": conv["lab"],
                "place": conv["place"],
                "sent": _when(conv["day"], hour, 2 * index),
                "person": person,
                "stranger": None if (person or is_mylo) else message["speaker"],
                "is_mylo": is_mylo,
                "dm_person": conv.get("dm_person"),
                "text": message["text"],
            }


def _mirror(world: World, platform: str) -> None:
    """The world's Discord links, consent and listening, on ``platform``."""
    from apps.accounts.models import Lab
    from apps.ambient import service
    from apps.ambient.models import ListeningConsent
    from apps.integrations.models import (
        DiscordIdentity,
        SlackIdentity,
        SlackWorkspace,
        TeamsIdentity,
        TeamsTeamLink,
    )

    labs = {lab.slug: lab for lab in Lab.objects.filter(slug__startswith="amb-")}
    for spec in world.labs:
        lab = labs[spec.slug]
        if platform == "slack":
            SlackWorkspace.objects.create(
                team_id=f"T{spec.slug}",
                bot_token="xoxb",
                bot_user_id=BOT_SLACK,
                lab=lab,
            )
            service.set_workspace_listening(f"T{spec.slug}", on=True, lab=lab)
        else:
            TeamsTeamLink.objects.create(
                team_id=f"19:{spec.slug}@thread",
                tenant_id=f"tenant-{spec.slug}",
                service_url=SERVICE,
                lab=lab,
            )
            service.set_team_listening(f"19:{spec.slug}@thread", on=True, lab=lab)
        for person in spec.people:
            identity = DiscordIdentity.objects.filter(
                discord_user_id=person.snowflake, state="active"
            ).first()
            if identity is None:
                continue
            if platform == "slack":
                SlackIdentity.objects.create(
                    user=identity.user,
                    team_id=f"T{spec.slug}",
                    slack_user_id=f"U{person.username}",
                )
            else:
                TeamsIdentity.objects.create(
                    user=identity.user,
                    tenant_id=f"tenant-{spec.slug}",
                    aad_object_id=f"aad-{person.username}",
                    service_url=SERVICE,
                    conversation_id=f"a:{person.username}",
                )
            discord = ListeningConsent.objects.filter(
                user=identity.user, platform="discord"
            ).first()
            if discord is not None:
                ListeningConsent.objects.create(
                    user=identity.user, platform=platform, enabled=discord.enabled
                )


def _replay_discord(msgs) -> None:
    from apps.ambient import service

    guilds = {}
    for msg in msgs:
        guild = guilds.setdefault(msg["lab"], msg["guild"])
        author = (
            msg["person"].snowflake
            if msg["person"]
            else (
                msg["owner"].snowflake
                if msg["is_mylo"]
                else f"9{abs(hash(msg['stranger'])) % 10**17}"
            )
        )
        if msg["place"] == "dm":
            service.heard(
                guild_id="",
                message_id=msg["id"],
                text=msg["text"],
                sent_at=msg["sent"],
                author_id=msg["owner"].snowflake if msg["is_mylo"] else author,
                is_dm=True,
                is_bot=msg["is_mylo"],
                from_mylo=msg["is_mylo"],
                explicit=not msg["is_mylo"],
            )
        else:
            service.heard(
                guild_id=guild,
                message_id=msg["id"],
                text=msg["text"],
                sent_at=msg["sent"],
                author_id=author,
                place_id=f"{msg['lab']}-{msg['place']}",
                place_label=msg["place"],
            )


def _replay_slack(msgs, client) -> None:
    for msg in msgs:
        team = f"T{msg['lab']}"
        dm = msg["place"] == "dm"
        owner = msg["owner"].username if msg["owner"] else ""
        user = (
            BOT_SLACK
            if msg["is_mylo"]
            else (
                f"U{msg['person'].username}"
                if msg["person"]
                else f"UX{abs(hash(msg['stranger'])) % 10**8}"
            )
        )
        event = {
            "type": "message",
            "user": user,
            "text": msg["text"],
            "channel": f"D{owner}" if dm else f"C{msg['lab']}-{msg['place']}",
            "channel_type": "im" if dm else "channel",
            "ts": f"{msg['sent'].timestamp():.6f}",
            **({"bot_id": "BMYLO"} if msg["is_mylo"] else {}),
        }
        body = json.dumps(
            {"type": "event_callback", "team_id": team, "event": event}
        ).encode()
        stamp = str(int(time.time()))
        signature = (
            "v0="
            + hmac.new(
                SIGNING.encode(), b"v0:" + stamp.encode() + b":" + body, hashlib.sha256
            ).hexdigest()
        )
        response = client.post(
            "/api/integrations/slack/events/",
            data=body,
            content_type="application/json",
            HTTP_X_SLACK_REQUEST_TIMESTAMP=stamp,
            HTTP_X_SLACK_SIGNATURE=signature,
        )
        assert response.status_code == 200, response.status_code


def _replay_teams(msgs, client, token) -> int:
    skipped = 0
    for msg in msgs:
        if msg["is_mylo"]:
            skipped += 1  # Teams never delivers a bot's own messages to it
            continue
        dm = msg["place"] == "dm"
        aad = (
            f"aad-{msg['person'].username}"
            if msg["person"]
            else f"aad-stranger-{abs(hash(msg['stranger'])) % 10**8}"
        )
        activity = {
            "type": "message",
            "id": msg["id"],
            "serviceUrl": SERVICE,
            "timestamp": msg["sent"].isoformat(),
            "text": msg["text"],
            "from": {"id": f"29:{aad}", "aadObjectId": aad},
            "recipient": {"id": BOT_TEAMS},
            "conversation": {
                "id": f"a:{msg['owner'].username}"
                if dm and msg["owner"]
                else f"19:{msg['lab']}-{msg['place']}@thread;messageid={msg['id']}",
                "conversationType": "personal" if dm else "channel",
            },
            "channelData": {
                "tenant": {"id": f"tenant-{msg['lab']}"},
                **(
                    {}
                    if dm
                    else {
                        "team": {"id": f"19:{msg['lab']}@thread"},
                        "channel": {"id": f"19:{msg['lab']}-{msg['place']}"},
                    }
                ),
            },
        }
        response = client.post(
            "/api/integrations/teams/messages/",
            data=json.dumps(activity),
            content_type="application/json",
            HTTP_AUTHORIZATION=token,
        )
        assert response.status_code == 200, response.status_code
    return skipped


def _ledger() -> dict:
    """What was kept, from the ledger: (speaker or 'mylo', content hash) and the
    drop counters, for this world's sources only."""
    from apps.ambient.models import RawMessageRef, SourceActivity

    kept = Counter(
        (ref.speaker.username if ref.speaker_id else "mylo", ref.content_hash)
        for ref in RawMessageRef.objects.filter(sent_at__isnull=False).select_related(
            "speaker"
        )
        if (ref.speaker_id is None or ref.speaker.username.startswith("amb_"))
    )
    drops = Counter()
    for row in SourceActivity.objects.all().values():
        for key, value in row.items():
            if key.startswith("dropped_") and value:
                drops[key] += value
    return {"kept": kept, "drops": drops}


def compare(world: World, written: list[dict]) -> dict:
    from django.test import Client

    from apps.ambient.models import RawMessageRef

    from . import run

    settings.SLACK_ENABLED = True
    settings.SLACK_SIGNING_SECRET = SIGNING
    settings.TEAMS_ENABLED = True
    settings.TEAMS_APP_ID = APP_ID
    settings.ALLOWED_HOSTS = ["*"]
    key, keys = _teams_keys()
    token = _teams_token(key)
    guild = {lab.slug: lab.guild for lab in world.labs}
    by_username = {p.username: p for lab in world.labs for p in lab.people}
    msgs = []
    for msg in _messages(world, written):
        msg["guild"] = guild[msg["lab"]]
        msg["owner"] = by_username.get(msg["dm_person"] or "")
        msgs.append(msg)

    results = {}
    for platform in ("discord", "slack", "teams"):
        started = time.monotonic()
        with (
            mock.patch("apps.integrations.tasks.slack_dialogue.delay"),
            mock.patch("apps.integrations.tasks.teams_dialogue.delay"),
            mock.patch(
                "apps.integrations.services.teams_auth._keys",
                lambda refresh=False: keys,
            ),
        ):
            try:
                with transaction.atomic():
                    run.seed(world)
                    skipped = 0
                    if platform == "discord":
                        _replay_discord(msgs)
                    else:
                        _mirror(world, platform)
                        client = Client()
                        if platform == "slack":
                            _replay_slack(msgs, client)
                        else:
                            skipped = _replay_teams(msgs, client, token)
                    ledger = _ledger()
                    results[platform] = {
                        "kept": ledger["kept"],
                        "drops": ledger["drops"],
                        "refs": RawMessageRef.objects.count(),
                        "mylo_not_delivered": skipped,
                        "seconds": round(time.monotonic() - started, 1),
                    }
                    raise _Rollback
            except _Rollback:
                pass

    base = results["discord"]
    out = {"messages": len(msgs), "platforms": {}}
    for platform, result in results.items():
        people = Counter({k: v for k, v in result["kept"].items() if k[0] != "mylo"})
        base_people = Counter({k: v for k, v in base["kept"].items() if k[0] != "mylo"})
        mylo = sum(v for k, v in result["kept"].items() if k[0] == "mylo")
        out["platforms"][platform] = {
            "refs": result["refs"],
            "people_kept": sum(people.values()),
            "people_kept_differ_from_discord": sum(
                ((people - base_people) + (base_people - people)).values()
            ),
            "mylo_lines_kept": mylo,
            "mylo_not_delivered": result["mylo_not_delivered"],
            "drops": dict(result["drops"]),
            "drops_equal_discord": dict(result["drops"]) == dict(base["drops"]),
            "seconds": result["seconds"],
        }
    return out
