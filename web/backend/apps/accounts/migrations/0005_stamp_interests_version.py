"""Stamp existing ``Profile.interests`` rows to the v1 contract.

A version-stamp, not a reshape: rows already carry contract-valid keys (the
seeder writes ``areas``/``skills``/``funding_needs``/``seeking``). The migration
adds ``version: 1`` and coerces the seeder's legacy string ``seeking`` into a
list, so every stored row matches ``apps.accounts.interests``.
"""

from django.db import migrations

CURRENT_VERSION = 1


def _stamp(interests):
    data = dict(interests or {})
    data.setdefault("version", CURRENT_VERSION)
    seeking = data.get("seeking")
    if isinstance(seeking, str):
        data["seeking"] = [seeking] if seeking else []
    return data


def stamp_forward(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    for profile in Profile.objects.all().iterator():
        stamped = _stamp(profile.interests)
        if stamped != profile.interests:
            profile.interests = stamped
            profile.save(update_fields=["interests"])


def stamp_backward(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    for profile in Profile.objects.all().iterator():
        data = dict(profile.interests or {})
        if "version" in data:
            data.pop("version", None)
            profile.interests = data
            profile.save(update_fields=["interests"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_backfill_profiles"),
    ]

    operations = [
        migrations.RunPython(stamp_forward, stamp_backward),
    ]
