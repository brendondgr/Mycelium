"""Keep each department head's membership row in step with ``Department.owner``.

The head is the ``owner`` foreign key; new departments also get an OWNER
``DeptMembership`` row (``create_department_workspace``), but older ones may not,
and before department roles had a rank a manager could create further OWNER
rows. After this every head has exactly the OWNER row, and any other OWNER row
is an admin — which is what it could already do, minus the claim to the head.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    DeptMembership = apps.get_model("accounts", "DeptMembership")
    for department in Department.objects.all().iterator():
        row, created = DeptMembership.objects.get_or_create(
            department_id=department.pk,
            user_id=department.owner_id,
            defaults={"role": "owner"},
        )
        if not created and row.role != "owner":
            row.role = "owner"
            row.save(update_fields=["role"])
        DeptMembership.objects.filter(
            department_id=department.pk, role="owner"
        ).exclude(pk=row.pk).update(role="admin")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0033_security_hardening"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
