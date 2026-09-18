"""Plan CN-04's sandbox validation: a consent matrix and a simulated search week.

Plants consent choices, personal addresses, unverified accounts, expired
settings and conversation-only topics on EXP-2026-09-005's world, then checks
every rule of being findable exhaustively against an independent reference
written from the plan — not from the code under test.
"""

from __future__ import annotations

import random
import time
from collections import Counter, defaultdict
from datetime import timedelta

#: What the directory says each sandbox domain is: (primary domain, country).
DIRECTORY_TRUTH = {
    "fsu.edu": ("fsu.edu", "US"),
    "ufl.edu": ("ufl.edu", "US"),
    "umich.edu": ("umich.edu", "US"),
    "ox.ac.uk": ("oxford.ac.uk", "GB"),
    "ed.ac.uk": ("ed.ac.uk", "GB"),
    "utoronto.ca": ("utoronto.ca", "CA"),
}
SCOPES = ("institution", "country", "anywhere")


def plan(world, seed: int) -> dict:
    rng = random.Random(seed * 11 + 5)
    people = [p.key for p in world.people]
    personal = set(rng.sample(people, k=len(people) // 10))
    rest = [p for p in people if p not in personal]
    unverified = set(rng.sample(rest, k=len(people) // 20))
    eligible = [p for p in people if p not in unverified]
    opened = set(rng.sample(eligible, k=int(len(eligible) * 0.4)))
    audiences = {}
    for key in opened:
        if key in personal:
            audiences[key] = "anywhere"
        else:
            audiences[key] = rng.choices(SCOPES, weights=(40, 30, 30))[0]
    expired = set(rng.sample(sorted(opened), k=max(1, len(opened) // 10)))
    talkers = set(rng.sample(people, k=int(len(people) * 0.3)))
    return {
        "personal": personal,
        "unverified": unverified,
        "opened": opened,
        "audiences": audiences,
        "expired": expired,
        "talkers": talkers,
    }


def apply(world, planned: dict) -> dict:
    """Write the plan into the sandbox through the real code paths."""
    from django.contrib.auth import get_user_model

    from apps.collab import consent
    from apps.collab.models import CollaborationSetting, OpenTo
    from apps.knowledge import service
    from apps.knowledge.models import Relation

    from .bootstrap import assert_sandboxed

    assert_sandboxed()
    User = get_user_model()
    CollaborationSetting.objects.all().delete()
    users = {
        u.username: u
        for u in User.objects.filter(username__in=[p.key for p in world.people])
    }
    rng = random.Random(7)
    refusals_tried = refusals_missed = 0
    for person in world.people:
        user = users[person.key]
        base = person.email.split("@")[0]
        user.email = (
            f"{base}@gmail.com" if person.key in planned["personal"] else person.email
        )
        user.save(update_fields=["email"])
        user.profile.is_verified = person.key not in planned["unverified"]
        user.profile.save(update_fields=["is_verified"])
    for key in sorted(planned["opened"]):
        user = users[key]
        consent.update(
            user,
            open=True,
            audience=planned["audiences"][key],
            open_to=rng.sample(OpenTo.values, k=rng.randint(0, 2)),
        )
        # Every narrower audience than the person's verified email supports
        # must be refused.
        if key in planned["personal"]:
            for scope in ("institution", "country"):
                refusals_tried += 1
                try:
                    consent.update(user, open=True, audience=scope)
                    refusals_missed += 1
                    consent.update(user, open=True, audience="anywhere")
                except consent.ConsentRefused:
                    pass
    for key in planned["unverified"]:
        refusals_tried += 1
        try:
            consent.update(users[key], open=True, audience="anywhere")
            refusals_missed += 1
        except consent.ConsentRefused:
            pass
    past = __import__("django.utils.timezone", fromlist=["now"]).now() - timedelta(
        days=1
    )
    CollaborationSetting.objects.filter(user__username__in=planned["expired"]).update(
        expires_at=past
    )
    talked = {}
    for key in sorted(planned["talkers"]):
        topic = f"sandbox private topic {key}"
        confirmed = service.record_conversational(
            users[key], surface=topic, relation=Relation.INTERESTED_IN
        )
        if confirmed is not None:
            service.confirm(users[key], confirmed.concept_id, Relation.INTERESTED_IN)
            talked[key] = topic
        service.record_conversational(
            users[key], surface=f"{topic} pending", relation=Relation.INTERESTED_IN
        )
    return {
        "users": users,
        "refusals_tried": refusals_tried,
        "refusals_missed": refusals_missed,
        "talked": talked,
    }


def _reference_place(person, planned):
    """Where the plan says a person is — written independently of the code."""
    if person.key in planned["unverified"]:
        return None
    if person.key in planned["personal"]:
        return ("", "")
    return DIRECTORY_TRUTH[person.institution]


def _reference_visible(candidate, cand_place, audience, seeker_place, scope) -> bool:
    if cand_place is None or seeker_place is None:
        return False

    def inside(a, b, how):
        if how == "anywhere":
            return True
        if how == "country":
            return bool(a[1]) and a[1] == b[1]
        return bool(a[0]) and a[0] == b[0]

    return inside(cand_place, seeker_place, audience) and inside(
        seeker_place, cand_place, scope
    )


def _gini(values) -> float:
    values = sorted(values)
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    cumulative = sum((i + 1) * v for i, v in enumerate(values))
    return round((2 * cumulative) / (n * sum(values)) - (n + 1) / n, 4)


def check(world, planned, applied, *, seed: int, searches: int = 2000) -> dict:
    from django.conf import settings
    from django.utils import timezone

    from apps.collab import consent
    from apps.collab.affiliation import refresh
    from apps.collab.models import Appearance, CollaborationSetting
    from apps.collab.preview import preview
    from apps.knowledge.models import Edge, Tier

    users = applied["users"]
    people = {p.key: p for p in world.people}
    out: dict = {}

    # H1 — verified scope, for everyone.
    scope_wrong = 0
    places = {}
    for key, person in people.items():
        row = refresh(users[key])
        got = None if row is None else (row.domain, row.country)
        expected = _reference_place(person, planned)
        scope_wrong += int(got != expected)
        places[key] = consent.place_of(users[key])
    out["scope_checked"] = len(people)
    out["violations_scope"] = scope_wrong

    # H3 — refusals and expiry.
    now = timezone.now()
    settings_by_user = {
        s.user.username: s for s in CollaborationSetting.objects.select_related("user")
    }
    open_now = {k for k, s in settings_by_user.items() if s.is_open(now)}
    out["violations_refusals"] = applied["refusals_missed"]
    out["refusals_tried"] = applied["refusals_tried"]
    out["violations_expiry"] = len(planned["expired"] & open_now)
    out["open_now"] = len(open_now)

    # H2 — every (seeker, candidate, scope) against the reference.
    started = time.monotonic()
    disagreements = triples = 0
    for seeker_key, seeker in people.items():
        seeker_ref = _reference_place(seeker, planned)
        for cand_key in open_now:
            if cand_key == seeker_key:
                continue
            audience = settings_by_user[cand_key].audience
            cand_ref = _reference_place(people[cand_key], planned)
            for scope in SCOPES:
                triples += 1
                expected = _reference_visible(
                    cand_key, cand_ref, audience, seeker_ref, scope
                )
                got = consent.mutually_visible(
                    places[cand_key], audience, places[seeker_key], scope
                )
                disagreements += int(expected != got)
    out["visibility_triples"] = triples
    out["violations_visibility"] = disagreements
    out["visibility_seconds"] = round(time.monotonic() - started, 1)

    # H4 — the preview of every open person.
    preview_bad = 0
    for key in sorted(open_now):
        user = users[key]
        allowed = {
            (e.surface or "").casefold()
            for e in Edge.objects.filter(
                user=user, tier__in=[Tier.DECLARED, Tier.DEMONSTRATED], status="active"
            )
        } | {
            e.concept.label.casefold()
            for e in Edge.objects.filter(
                user=user, tier__in=[Tier.DECLARED, Tier.DEMONSTRATED], status="active"
            ).select_related("concept")
        }
        shown = preview(user)
        for items in shown["facets"].values():
            for item in items:
                label = item["label"].casefold()
                if label not in allowed or "sandbox private topic" in label:
                    preview_bad += 1
    out["previews_checked"] = len(open_now)
    out["violations_preview"] = preview_bad

    # H5 — a simulated week of searches, with and without the cap.
    Appearance.objects.all().delete()
    rng = random.Random(seed * 13 + 1)
    open_list = sorted(open_now)
    popularity = {
        key: 1 / ((rank + 1) ** 1.2)
        for rank, key in enumerate(rng.sample(open_list, len(open_list)))
    }
    seekers = [k for k in people if places[k] is not None]
    uncapped: dict[str, set] = defaultdict(set)
    withheld = returned = 0
    week_start = now
    for _ in range(searches):
        seeker_key = rng.choice(seekers)
        scope = rng.choice(SCOPES)
        visible = [
            k
            for k in open_list
            if k != seeker_key
            and consent.mutually_visible(
                places[k], settings_by_user[k].audience, places[seeker_key], scope
            )
        ]
        if not visible:
            continue
        # A search returns a handful of people, drawn toward the popular.
        picks = set(
            rng.choices(
                visible,
                weights=[popularity[k] for k in visible],
                k=min(5, len(visible)),
            )
        )
        for cand_key in picks:
            uncapped[cand_key].add(seeker_key)
            if consent.may_appear(users[cand_key], users[seeker_key], now=week_start):
                consent.record_appearance(
                    users[cand_key], users[seeker_key], now=week_start
                )
                returned += 1
            else:
                withheld += 1
    capped = Counter(Appearance.objects.values_list("candidate__username", flat=True))
    cap = settings.COLLAB_APPEARANCE_CAP
    out["searches"] = searches
    out["results_returned"] = returned
    out["results_withheld_by_cap"] = withheld
    out["violations_cap"] = sum(1 for n in capped.values() if n > cap)
    out["max_distinct_seekers_capped"] = max(capped.values(), default=0)
    out["max_distinct_seekers_uncapped"] = max(
        (len(v) for v in uncapped.values()), default=0
    )
    out["gini_capped"] = _gini([capped.get(k, 0) for k in open_list])
    out["gini_uncapped"] = _gini([len(uncapped.get(k, set())) for k in open_list])
    out["violations_total"] = sum(
        v for k, v in out.items() if k.startswith("violations_")
    )
    return out
