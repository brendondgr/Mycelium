"""Turn ``DailyBriefing`` from one overwritten row per target into dated history.

Adds ``generated_on`` (nullable first so existing rows can be backfilled from the
``generated_at`` timestamp), relaxes the OneToOne targets to ForeignKeys, then
locks in one row per target per day. There is at most one row per target before
this runs, so the backfill cannot collide.
"""

from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_generated_on(apps, schema_editor):
    """Stamp each existing briefing with the local date it was written."""
    DailyBriefing = apps.get_model("content", "DailyBriefing")
    for briefing in DailyBriefing.objects.all().iterator():
        briefing.generated_on = timezone.localtime(briefing.generated_at).date()
        briefing.save(update_fields=["generated_on"])


def unset_generated_on(apps, schema_editor):
    """Reverse: clear the column so the AddField can drop cleanly."""
    DailyBriefing = apps.get_model("content", "DailyBriefing")
    DailyBriefing.objects.update(generated_on=None)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
        ("content", "0017_remindersubscription_snoozed_until"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailybriefing",
            name="generated_on",
            field=models.DateField(
                null=True,
                db_index=True,
                help_text="The local date this briefing covers — the history key.",
            ),
        ),
        migrations.RunPython(backfill_generated_on, unset_generated_on),
        migrations.AlterField(
            model_name="dailybriefing",
            name="generated_on",
            field=models.DateField(
                db_index=True,
                default=django.utils.timezone.localdate,
                help_text="The local date this briefing covers — the history key.",
            ),
        ),
        migrations.AlterField(
            model_name="dailybriefing",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="daily_briefings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="dailybriefing",
            name="lab",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="daily_briefings",
                to="accounts.lab",
            ),
        ),
        migrations.AlterModelOptions(
            name="dailybriefing",
            options={"ordering": ["-generated_on", "-generated_at"]},
        ),
        migrations.AddConstraint(
            model_name="dailybriefing",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("user", "generated_on"),
                name="content_dailybriefing_user_day_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="dailybriefing",
            constraint=models.UniqueConstraint(
                condition=models.Q(("lab__isnull", False)),
                fields=("lab", "generated_on"),
                name="content_dailybriefing_lab_day_unique",
            ),
        ),
    ]
