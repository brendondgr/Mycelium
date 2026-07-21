"""Grandfather existing department-attached labs into the plan.

Before per-lab inclusion, every lab under a department was automatically covered by
the department plan. Inclusion now defaults to opt-in (False), so without this
backfill every currently-attached lab's members would silently drop off the plan on
deploy. Set ``department_plan_included=True`` for every lab that already belongs to
a department, preserving current entitlements; new attachments start opt-out.
"""

from django.db import migrations


def grandfather(apps, schema_editor):
    Lab = apps.get_model("accounts", "Lab")
    Lab.objects.filter(department__isnull=False).update(department_plan_included=True)


def unset(apps, schema_editor):
    Lab = apps.get_model("accounts", "Lab")
    Lab.objects.update(department_plan_included=False)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0019_lab_department_plan_included"),
    ]

    operations = [
        migrations.RunPython(grandfather, unset),
    ]
