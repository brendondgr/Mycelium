"""Drop the boolean ``visibility`` replaced (backfilled in 0007).

A migration of its own so the data step and the ALTER never share a
transaction.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("research", "0007_project_visibility_member_role"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="project",
            name="share_in_lab_reports",
        ),
    ]
