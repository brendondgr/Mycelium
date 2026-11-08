"""Per-round deadlines: ``ContentDeadline`` keyed on (content, kind, round_key).

The schema half is generated; :func:`rekey_conference_rounds` is the hand-written
half and the only part with a judgement in it. Every existing row lands on
``round_key = ""`` from the field default, but the new derivation gives a
conference round the collector's own identity (``"submission:"``,
``"abstract:round 2"``, …). Left alone, the next projection rebuild would see no
row matching those keys, delete every ``""``-keyed conference row, and create
fresh ones — orphaning any reminder pointing at the old row.

So this re-keys them in place, matching each existing row to the collector
deadline entry that produced it on ``(mapped kind, date)``, and moves any
subscription on that row with it. Grants, fellowships, and a conference's event
row are single-round and correctly keep ``""``.

A row whose source entry can no longer be found (metadata rewritten since, or a
date that has passed) is left on ``""``; the rebuild then removes it, which is
the same outcome it would have had anyway.
"""

from django.conf import settings
from django.db import migrations, models

#: Mirrors ``deadlines_projection._STRUCTURED_KIND_MAP``, copied rather than
#: imported: a migration must keep describing what the schema looked like at
#: this point in history even after that module moves on.
_KIND_MAP = {"abstract": "abstract", "submission": "manuscript"}


def _round_key(collector_kind, round_label):
    return f"{collector_kind}:{(round_label or '').strip().lower()}"


def rekey_conference_rounds(apps, schema_editor):
    ContentDeadline = apps.get_model("content", "ContentDeadline")
    ReminderSubscription = apps.get_model("content", "ReminderSubscription")

    rows = ContentDeadline.objects.filter(content__type="conference").select_related(
        "content"
    )
    for row in rows:
        entries = (row.content.metadata or {}).get("deadlines_structured") or []
        for entry in entries:
            instant = entry.get("instant") or ""
            if instant[:10] != (row.due_date.isoformat() if row.due_date else ""):
                continue
            collector_kind = entry.get("kind") or "unknown"
            if _KIND_MAP.get(collector_kind, "other") != row.kind:
                continue
            label = (entry.get("round_label") or "").strip()
            row.round_key = _round_key(collector_kind, label)
            row.round_label = label
            row.save(update_fields=["round_key", "round_label"])
            ReminderSubscription.objects.filter(
                content_id=row.content_id, deadline_kind=row.kind, deadline_round_key=""
            ).update(deadline_round_key=row.round_key, round_label=label)
            break


def unkey(apps, schema_editor):
    """Reverse: collapse every round back onto the single per-kind row.

    Lossy by nature — several rounds share one key again — but the constraint
    being restored is the narrower one, so anything it would now reject was
    created after this migration ran and could not have existed before it.
    """
    apps.get_model("content", "ContentDeadline").objects.update(
        round_key="", round_label=""
    )
    apps.get_model("content", "ReminderSubscription").objects.update(
        deadline_round_key="", round_label=""
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0020_grandfather_dept_lab_inclusion'),
        ('content', '0021_search_vector_opportunity_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='contentdeadline',
            options={'ordering': ['due_date', 'kind', 'round_key']},
        ),
        migrations.RemoveConstraint(
            model_name='contentdeadline',
            name='content_deadline_unique_content_kind',
        ),
        migrations.RemoveConstraint(
            model_name='remindersubscription',
            name='content_reminder_unique_user_content_kind',
        ),
        migrations.RemoveConstraint(
            model_name='remindersubscription',
            name='content_reminder_unique_lab_content_kind',
        ),
        migrations.AddField(
            model_name='contentdeadline',
            name='is_next',
            field=models.BooleanField(default=True, help_text='This is the earliest future row of its kind (the headline one).'),
        ),
        migrations.AddField(
            model_name='contentdeadline',
            name='round_key',
            field=models.CharField(blank=True, default='', help_text="Stable identity of this round within its item — the collector's '<kind>:<normalized label>'. Empty for a single-round deadline.", max_length=160),
        ),
        migrations.AddField(
            model_name='contentdeadline',
            name='round_label',
            field=models.CharField(blank=True, default='', help_text="The source's own round wording ('round 2'), verbatim.", max_length=200),
        ),
        migrations.AddField(
            model_name='remindersubscription',
            name='deadline_round_key',
            field=models.CharField(blank=True, default='', help_text='Which round of that kind this reminder is for — the matching ContentDeadline.round_key. Empty for a single-round deadline.', max_length=160),
        ),
        migrations.AddField(
            model_name='remindersubscription',
            name='round_label',
            field=models.CharField(blank=True, default='', help_text="Snapshot of the round's wording, so a fired message can name it.", max_length=200),
        ),
        # Between the columns landing and the new key being enforced: the rows
        # must already hold their real round keys before uniqueness is checked
        # against them.
        migrations.RunPython(rekey_conference_rounds, unkey),
        migrations.AddConstraint(
            model_name='contentdeadline',
            constraint=models.UniqueConstraint(fields=('content', 'kind', 'round_key'), name='content_deadline_unique_content_kind_round'),
        ),
        migrations.AddConstraint(
            model_name='remindersubscription',
            constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_user__isnull', False)), fields=('target_user', 'content', 'deadline_kind', 'deadline_round_key'), name='content_reminder_unique_user_content_round'),
        ),
        migrations.AddConstraint(
            model_name='remindersubscription',
            constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_lab__isnull', False)), fields=('target_lab', 'content', 'deadline_kind', 'deadline_round_key'), name='content_reminder_unique_lab_content_round'),
        ),
    ]
