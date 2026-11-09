import uuid

import django.db.models.deletion
import pgvector.django.vector
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0032_org_limit_overrides"),
        ("core", "0001_enable_pgvector"),
        ("research", "0006_project_aliases"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentPreference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("chat_enabled", models.BooleanField(default=True)),
                ("discord_allowed", models.BooleanField(default=True)),
                ("groups_off", models.JSONField(blank=True, default=list)),
                ("learning_notice_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_preference",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AgentThread",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "scope_kind",
                    models.CharField(
                        choices=[
                            ("personal", "personal"),
                            ("lab", "lab"),
                            ("department", "department"),
                            ("project", "project"),
                        ],
                        default="personal",
                        max_length=12,
                    ),
                ),
                ("surface", models.CharField(default="web", max_length=12)),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("purpose", models.CharField(blank=True, default="", max_length=300)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("idle", "Idle"),
                            ("running", "Running"),
                            ("waiting", "Waiting"),
                            ("error", "Error"),
                        ],
                        default="idle",
                        max_length=10,
                    ),
                ),
                ("mode", models.CharField(default="read", max_length=10)),
                ("settings", models.JSONField(blank=True, default=dict)),
                ("archived", models.BooleanField(default=False)),
                ("fork_seq", models.PositiveIntegerField(blank=True, null=True)),
                ("learned_seq", models.PositiveIntegerField(default=0)),
                ("learn_after", models.DateTimeField(blank=True, null=True)),
                ("learn_failures", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "last_activity_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="forks",
                        to="agent.agentthread",
                    ),
                ),
                (
                    "scope_department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.department",
                    ),
                ),
                (
                    "scope_lab",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.lab",
                    ),
                ),
                (
                    "scope_project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="research.project",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_threads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-last_activity_at"],
            },
        ),
        migrations.CreateModel(
            name="AgentQueuedMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text", models.TextField()),
                ("mentions", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="queued",
                        to="agent.agentthread",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="AgentEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("seq", models.PositiveIntegerField()),
                ("ts", models.DateTimeField(auto_now_add=True)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("user", "user"),
                            ("recall", "recall"),
                            ("thinking", "thinking"),
                            ("assistant", "assistant"),
                            ("tool_call", "tool_call"),
                            ("tool_result", "tool_result"),
                            ("question", "question"),
                            ("answer", "answer"),
                            ("todos", "todos"),
                            ("usage", "usage"),
                            ("compact", "compact"),
                            ("note", "note"),
                            ("error", "error"),
                            ("state", "state"),
                            ("verdict", "verdict"),
                        ],
                        max_length=16,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("tokens", models.PositiveIntegerField(default=0)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="agent.agentthread",
                    ),
                ),
            ],
            options={
                "ordering": ["thread", "seq"],
            },
        ),
        migrations.CreateModel(
            name="AgentThreadDigest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text", models.TextField(blank=True, default="")),
                (
                    "embedding",
                    pgvector.django.vector.VectorField(blank=True, null=True),
                ),
                ("upto_seq", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "thread",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="digest",
                        to="agent.agentthread",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AgentOrgPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("groups_off", models.JSONField(blank=True, default=list)),
                ("discord_channels_off", models.JSONField(blank=True, default=list)),
                ("max_risk", models.CharField(default="read", max_length=12)),
                ("members_inform_org", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "department",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.department",
                    ),
                ),
                (
                    "lab",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.lab",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("lab__isnull", False), ("department__isnull", True)
                            ),
                            models.Q(
                                ("department__isnull", False), ("lab__isnull", True)
                            ),
                            _connector="OR",
                        ),
                        name="agent_org_policy_one_org",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="agentthread",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("scope_department__isnull", True),
                        ("scope_kind", "personal"),
                        ("scope_lab__isnull", True),
                        ("scope_project__isnull", True),
                    ),
                    models.Q(
                        ("scope_kind", "lab"),
                        models.Q(
                            models.Q(
                                ("scope_lab__isnull", False),
                                ("scope_department__isnull", True),
                                ("scope_project__isnull", True),
                            ),
                            models.Q(
                                ("scope_department__isnull", False),
                                ("scope_lab__isnull", True),
                                ("scope_project__isnull", True),
                            ),
                            models.Q(
                                ("scope_project__isnull", False),
                                ("scope_lab__isnull", True),
                                ("scope_department__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        ("scope_lab__isnull", False),
                    ),
                    models.Q(
                        ("scope_kind", "department"),
                        models.Q(
                            models.Q(
                                ("scope_lab__isnull", False),
                                ("scope_department__isnull", True),
                                ("scope_project__isnull", True),
                            ),
                            models.Q(
                                ("scope_department__isnull", False),
                                ("scope_lab__isnull", True),
                                ("scope_project__isnull", True),
                            ),
                            models.Q(
                                ("scope_project__isnull", False),
                                ("scope_lab__isnull", True),
                                ("scope_department__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        ("scope_department__isnull", False),
                    ),
                    models.Q(
                        ("scope_kind", "project"),
                        models.Q(
                            models.Q(
                                ("scope_lab__isnull", False),
                                ("scope_department__isnull", True),
                                ("scope_project__isnull", True),
                            ),
                            models.Q(
                                ("scope_department__isnull", False),
                                ("scope_lab__isnull", True),
                                ("scope_project__isnull", True),
                            ),
                            models.Q(
                                ("scope_project__isnull", False),
                                ("scope_lab__isnull", True),
                                ("scope_department__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        ("scope_project__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="agent_thread_scope_matches_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentevent",
            constraint=models.UniqueConstraint(
                fields=("thread", "seq"), name="agent_event_unique_seq"
            ),
        ),
    ]
