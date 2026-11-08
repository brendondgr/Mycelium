"""The recommendation tool's models, taken over from the content app.

State only: the tables already exist (created by the content migrations,
kept under their names by each model's Meta.db_table); this migration only
tells Django the models now belong here. The content types are re-homed so
existing permissions follow the models.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MOVED = ("projectprofile", "itemcomprehension", "relevanceevent", "relevancescore")


def move_content_types(apps, schema_editor):
    """Re-home the moved models' content types (and so their permissions)."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model in MOVED:
        if not ContentType.objects.filter(app_label='recommendation', model=model).exists():
            ContentType.objects.filter(app_label='content', model=model).update(
                app_label='recommendation'
            )


def restore_content_types(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model in MOVED:
        if not ContentType.objects.filter(app_label='content', model=model).exists():
            ContentType.objects.filter(app_label='recommendation', model=model).update(
                app_label='content'
            )


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('accounts', '0032_org_limit_overrides'),
        ('content', '0038_hand_off_recommendation_models'),
        ('research', '0006_project_aliases'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # State only: the tables keep their names and their rows (each moved
        # model pins Meta.db_table), so the database is not touched.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='ProjectProfile',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('interests', models.JSONField(blank=True, default=dict, help_text='Aggregated / deduped interest terms from members + engagement.')),
                        ('last_recomputed', models.DateTimeField(blank=True, null=True)),
                        ('recompute_reason', models.CharField(blank=True, choices=[('membership_change', 'Membership change'), ('engagement', 'Engagement'), ('manual', 'Manual')], default='', max_length=20)),
                        ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='team_profile', to='research.project')),
                    ],
                    options={
                        'db_table': 'content_projectprofile',
                    },
                ),
                migrations.CreateModel(
                    name='ItemComprehension',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('problem', models.TextField(blank=True, default='')),
                        ('method', models.TextField(blank=True, default='')),
                        ('setting', models.TextField(blank=True, default='', help_text='The data, cohort, or setting the work was carried out in.')),
                        ('claim', models.TextField(blank=True, default='')),
                        ('limitations', models.TextField(blank=True, default='', help_text='Limitations the authors themselves state — never inferred.')),
                        ('reusable', models.TextField(blank=True, default='', help_text='What an outside researcher could concretely take: a method, a dataset, a baseline, a negative result, an evaluation protocol.')),
                        ('thin', models.BooleanField(default=False, help_text='The source text was too sparse to support a précis.')),
                        ('prompt_version', models.CharField(blank=True, default='', max_length=32)),
                        ('source_fingerprint', models.CharField(blank=True, default='', max_length=64)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('content', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='comprehension', to='content.contentitem')),
                    ],
                    options={
                        'db_table': 'content_itemcomprehension',
                        'indexes': [models.Index(fields=['prompt_version'], name='content_ite_prompt__40fec5_idx')],
                    },
                ),
                migrations.CreateModel(
                    name='RelevanceEvent',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('action', models.CharField(choices=[('view', 'View'), ('save', 'Save'), ('share', 'Share'), ('thumbs_up', 'Thumbs up'), ('thumbs_down', 'Thumbs down'), ('dismiss', 'Dismiss'), ('open_external', 'Open external')], max_length=20)),
                        ('weight', models.FloatField(help_text='Per-action weight at capture time (config-driven).')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relevance_events', to='content.contentitem')),
                        ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='relevance_events', to='research.project')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relevance_events', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_relevanceevent',
                        'ordering': ['-created_at'],
                        'indexes': [models.Index(fields=['project', 'created_at'], name='content_rel_project_d5703e_idx'), models.Index(fields=['user', 'content'], name='content_rel_user_id_0a9086_idx')],
                    },
                ),
                migrations.CreateModel(
                    name='RelevanceScore',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('score', models.FloatField()),
                        ('signals', models.JSONField(blank=True, default=dict, help_text="Per-signal breakdown — the 'why this matters'.")),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scores', to='content.contentitem')),
                        ('target_department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='relevance_scores', to='accounts.department')),
                        ('target_lab', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='relevance_scores', to='accounts.lab')),
                        ('target_project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='relevance_scores', to='research.project')),
                        ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='relevance_scores', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_relevancescore',
                        'ordering': ['-score'],
                        'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('target_user__isnull', False), ('target_project__isnull', True), ('target_lab__isnull', True), ('target_department__isnull', True)), models.Q(('target_project__isnull', False), ('target_user__isnull', True), ('target_lab__isnull', True), ('target_department__isnull', True)), models.Q(('target_lab__isnull', False), ('target_user__isnull', True), ('target_project__isnull', True), ('target_department__isnull', True)), models.Q(('target_department__isnull', False), ('target_user__isnull', True), ('target_project__isnull', True), ('target_lab__isnull', True)), _connector='OR'), name='content_relevance_one_target'), models.UniqueConstraint(fields=('content', 'target_user'), name='content_relevance_unique_target_user'), models.UniqueConstraint(fields=('content', 'target_project'), name='content_relevance_unique_target_project'), models.UniqueConstraint(fields=('content', 'target_lab'), name='content_relevance_unique_target_lab'), models.UniqueConstraint(fields=('content', 'target_department'), name='content_relevance_unique_target_department')],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(move_content_types, restore_content_types),
    ]
