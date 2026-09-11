"""Backfill every existing watch row to ``daily`` (plan M3, open decision OD1).

The stored default was ``weekly``, but no send path ever read ``cadence``:
``select_users``, ``eligible_recipients`` and ``eligible_labs`` all ignored it, so
every linked user and lab has been receiving a Discord post **every day** whatever
their row says. Phase 0.4 makes the field real.

Honouring the stored value at that moment would silently move most of the product's
existing readers from daily posts to one post a week — a change nobody asked for,
delivered as a disappearance. So every existing row is set to the cadence it has
actually been getting, and the choice is offered forward rather than applied
retroactively. Nobody's experience changes on the day this ships.

Deliberately not reversible in the data sense: there is no record of which rows
were flipped, and re-setting them all to ``weekly`` on a rollback would do the exact
harm this migration exists to avoid. The reverse is a no-op, which leaves the
column populated and harmless.
"""

from django.db import migrations


def backfill_daily(apps, schema_editor):
    for model_name in ("WatchPreference", "LabWatchPreference"):
        model = apps.get_model("accounts", model_name)
        model.objects.exclude(cadence="daily").update(cadence="daily")


def noop(apps, schema_editor):
    """Leave the column as it is — see the module docstring."""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_watch_delivery_and_timeline"),
    ]

    operations = [
        migrations.RunPython(backfill_daily, noop),
    ]
