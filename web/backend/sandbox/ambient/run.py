"""Seed the ambient world, feed it the conversations, and run Plan 04.

Messages enter exactly as the gateway's would — through
``apps.ambient.service.heard`` — so eligibility, filtering, the buffer and
attribution on arrival are the real ones. Then the hourly read, deliberation
and explanation run with the real model and the real embedder, at the
shipped defaults. Only the buffer is swapped for an in-process cache, and the
harness settings (``AMBIENT_ENABLED``, deliberation on, concurrency) are set
on this process alone.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from .world import World

logger = logging.getLogger(__name__)


def configure(workers: int) -> None:
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_DELIBERATE_ENABLED = True
    settings.AMBIENT_EXTRACT_CONCURRENCY = workers
    settings.AMBIENT_EXTRACT_DAILY_CAP_PER_LAB = 10_000
    settings.AMBIENT_EXPLAIN_NIGHTLY_CAP = 10_000
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sandbox-ambient",
            "TIMEOUT": 60 * 60 * 6,
            # Django's local-memory cache culls past 300 entries by default;
            # Redis never evicts a body before its TTL. Without this the
            # harness, not the pipeline, loses most of the text (EXP-013 run 2).
            "OPTIONS": {"MAX_ENTRIES": 1_000_000, "CULL_FREQUENCY": 0},
        },
    }


def clear() -> None:
    """Remove a previous run's world. Only rows the harness made (``amb``)."""
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Lab
    from apps.ambient.models import Source

    Source.objects.filter(lab__slug__startswith="amb-").delete()
    from apps.integrations.models import DiscordIdentity

    users = get_user_model().objects.filter(username__startswith="amb_")
    Source.objects.filter(
        kind=Source.Kind.DISCORD_DM,
        external_id__in=list(
            DiscordIdentity.objects.filter(user__in=users).values_list(
                "discord_user_id", flat=True
            )
        ),
    ).delete()
    Lab.objects.filter(slug__startswith="amb-").delete()
    users.delete()


def seed(world: World) -> dict:
    """Labs, people, subscriptions, identities, consent, profiles, projects."""
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Lab, Profile
    from apps.ambient import service
    from apps.ambient.models import ListeningConsent, Platform
    from apps.billing.models import Subscription, Tier
    from apps.integrations.models import DiscordIdentity
    from apps.knowledge.service import project_declared
    from apps.research.models import Project, ProjectMember

    User = get_user_model()
    clear()
    counts = {"people": 0, "projects": 0}
    for spec in world.labs:
        lab = Lab.objects.create(name=spec.name, slug=spec.slug)
        members = []
        for person in spec.people:
            user = User.objects.create_user(
                person.username,
                f"{person.username}@sandbox.invalid",
                "x",
                first_name=person.name,
            )
            Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
            DiscordIdentity.objects.create(
                user=user,
                discord_user_id=person.snowflake,
                link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
                state=DiscordIdentity.State.ACTIVE,
            )
            if person.opted_in:
                ListeningConsent.objects.create(
                    user=user, platform=Platform.DISCORD, enabled=True
                )
            areas = list(person.declared)
            clusters = [
                {"id": f"c{i}", "label": area.title(), "areas": [area]}
                for i, area in enumerate(areas)
            ]
            if person.full_clusters:
                extra = [f"sandbox theme {i}" for i in range(6 - len(areas))]
                areas += extra
                clusters += [
                    {"id": f"x{i}", "label": f"Theme {i}", "areas": [a]}
                    for i, a in enumerate(extra)
                ]
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.interests = {"version": 2, "areas": areas, "clusters": clusters}
            profile.save()
            project_declared(user)
            members.append(user)
            counts["people"] += 1
        for name in spec.projects:
            project = Project.objects.create(name=name, scope_lab=lab)
            for user in members:
                ProjectMember.objects.create(project=project, user=user)
            counts["projects"] += 1
        service.set_guild_listening(spec.guild, on=True, lab=lab)
    return counts


def _when(day: int, hour: int, minute: int) -> datetime:
    base = timezone.localtime(timezone.now() - timedelta(days=day))
    return base.replace(
        hour=hour, minute=minute % 60, second=0, microsecond=0
    ) + timedelta(hours=minute // 60)


def ingest(world: World, written: list[dict]) -> dict:
    """Every generated message, through the gateway's own door."""
    from apps.ambient import service

    names = {(lab.slug, p.name): p for lab in world.labs for p in lab.people}
    guild = {lab.slug: lab.guild for lab in world.labs}
    counts = {"messages": 0, "stored": 0, "dropped": {}, "plant_messages": {}}
    hour_of: dict[tuple, int] = {}
    for conv in written:
        slot = (conv["lab"], conv["day"], conv["place"])
        hour = 9 + 2 * hour_of.get(slot, 0)
        hour_of[slot] = hour_of.get(slot, 0) + 1
        for index, message in enumerate(conv["messages"]):
            counts["messages"] += 1
            mid = f"{conv['id']}#{index}"
            sent = _when(conv["day"], hour, 2 * index)
            if message["speaker"] == "Mylo":
                owner = next(
                    p
                    for (lab, _n), p in names.items()
                    if lab == conv["lab"] and p.username == conv["dm_person"]
                )
                outcome = service.heard(
                    guild_id="",
                    message_id=mid,
                    text=message["text"],
                    sent_at=sent,
                    author_id=owner.snowflake,
                    is_dm=True,
                    is_bot=True,
                    from_mylo=True,
                )
            else:
                person = names.get((conv["lab"], message["speaker"]))
                if person is None:
                    continue
                if conv["place"] == "dm":
                    outcome = service.heard(
                        guild_id="",
                        message_id=mid,
                        text=message["text"],
                        sent_at=sent,
                        author_id=person.snowflake,
                        is_dm=True,
                        explicit=True,
                    )
                else:
                    outcome = service.heard(
                        guild_id=guild[conv["lab"]],
                        message_id=mid,
                        text=message["text"],
                        sent_at=sent,
                        author_id=person.snowflake,
                        place_id=f"{conv['lab']}-{conv['place']}",
                        place_label=conv["place"],
                    )
            if outcome.stored:
                counts["stored"] += 1
            else:
                counts["dropped"][outcome.reason] = (
                    counts["dropped"].get(outcome.reason, 0) + 1
                )
            if message.get("plant"):
                counts["plant_messages"][message["plant"]] = {
                    "mid": mid,
                    "stored": bool(outcome.stored),
                    "reason": outcome.reason,
                }
    return counts


def pipeline() -> dict:
    """The hourly read (as many passes as it takes), then the nightly decide."""
    from apps.ambient import deliberate, explain, reading

    timings = {}
    started = time.monotonic()
    reads = []
    for _ in range(5):
        run = reading.read_ready()
        reads.append(run.as_dict())
        if not run.ready or (run.read == 0 and run.unavailable == 0):
            break
        if run.unavailable == 0:
            continue
    timings["read_s"] = round(time.monotonic() - started, 1)
    started = time.monotonic()
    decided = deliberate.deliberate().as_dict()
    timings["deliberate_s"] = round(time.monotonic() - started, 1)
    started = time.monotonic()
    explained = explain.explain_pending().as_dict()
    timings["explain_s"] = round(time.monotonic() - started, 1)
    return {
        "reads": reads,
        "deliberate": decided,
        "explain": explained,
        "timings": timings,
    }
