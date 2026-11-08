"""Hand RelevanceScore, ItemComprehension, ProjectProfile and RelevanceEvent to the
recommendation tool.

State only: the models now live in tools/recommendation/models.py under the
recommendation app label, with their tables (content_relevancescore …)
unchanged. See recommendation.0001_initial for the other half.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0037_guest_reminders'),
    ]

    operations = [
        # State only: the tables keep their names and their rows (each moved
        # model pins Meta.db_table), so the database is not touched.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='projectprofile',
                    name='project',
                ),
                migrations.RemoveField(
                    model_name='relevanceevent',
                    name='content',
                ),
                migrations.RemoveField(
                    model_name='relevanceevent',
                    name='project',
                ),
                migrations.RemoveField(
                    model_name='relevanceevent',
                    name='user',
                ),
                migrations.RemoveField(
                    model_name='relevancescore',
                    name='content',
                ),
                migrations.RemoveField(
                    model_name='relevancescore',
                    name='target_department',
                ),
                migrations.RemoveField(
                    model_name='relevancescore',
                    name='target_lab',
                ),
                migrations.RemoveField(
                    model_name='relevancescore',
                    name='target_project',
                ),
                migrations.RemoveField(
                    model_name='relevancescore',
                    name='target_user',
                ),
                migrations.DeleteModel(
                    name='ItemComprehension',
                ),
                migrations.DeleteModel(
                    name='ProjectProfile',
                ),
                migrations.DeleteModel(
                    name='RelevanceEvent',
                ),
                migrations.DeleteModel(
                    name='RelevanceScore',
                ),
            ],
            database_operations=[],
        ),
    ]
