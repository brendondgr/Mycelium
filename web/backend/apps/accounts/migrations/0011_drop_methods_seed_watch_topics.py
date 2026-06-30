"""Retire ``methods`` and seed watch topics for the watch-driven search.

Two data fixes for the pipeline overhaul:

1. ``methods`` was removed from the interests contract. Strip the stale key from
   every stored ``interests`` JSON (Profile, LabProfile, DeptProfile) so a later
   re-save does not trip the contract validator (which now rejects unknown keys).

2. Literature search is now driven *solely* by each user's
   :class:`WatchPreference` topics. Existing users onboarded before this change
   have interests but no watch topics, so they would silently get no searches.
   Seed each user's watch topics from their interests (areas + keywords) — but
   only when they have not already curated their own topics, so we never clobber
   a deliberate choice.
"""

from __future__ import annotations

from django.db import migrations

_TOPIC_CAP = 12


def _strip_methods(interests):
    data = dict(interests or {})
    if "methods" in data:
        data.pop("methods", None)
        return data, True
    return data, False


def _seed_topics(interests) -> list[str]:
    """Deduped areas + keywords, order-preserving, capped — the search seed."""
    topics: list[str] = []
    seen: set[str] = set()
    for key in ("areas", "keywords"):
        for value in (interests or {}).get(key) or []:
            text = " ".join(str(value).split())
            fold = text.casefold()
            if text and fold not in seen:
                seen.add(fold)
                topics.append(text)
    return topics[:_TOPIC_CAP]


def forward(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    WatchPreference = apps.get_model("accounts", "WatchPreference")

    # 1 + 2: strip methods from profiles and seed each user's watch topics.
    for profile in Profile.objects.all().iterator():
        cleaned, changed = _strip_methods(profile.interests)
        if changed:
            profile.interests = cleaned
            profile.save(update_fields=["interests"])

        watch, created = WatchPreference.objects.get_or_create(user_id=profile.user_id)
        if created or not watch.topics:
            seeded = _seed_topics(cleaned)
            if seeded:
                watch.topics = seeded
                watch.save(update_fields=["topics"])

    # 1 (cont.): strip methods from lab/dept interest surfaces too.
    for model_name in ("LabProfile", "DeptProfile"):
        Model = apps.get_model("accounts", model_name)
        for row in Model.objects.all().iterator():
            cleaned, changed = _strip_methods(row.interests)
            if changed:
                row.interests = cleaned
                row.save(update_fields=["interests"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_watchpreference"),
    ]

    operations = [
        # Irreversible by design: methods cannot be reconstructed, and seeded
        # topics are indistinguishable from user-set ones on the way back.
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
