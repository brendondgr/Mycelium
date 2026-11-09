import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0032_org_limit_overrides"),
        ("research", "0006_project_aliases"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StoredFile",
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
                ("filename", models.CharField(max_length=255)),
                ("kind", models.CharField(max_length=8)),
                ("content_type", models.CharField(max_length=100)),
                ("size", models.PositiveBigIntegerField()),
                ("sha256", models.CharField(db_index=True, max_length=64)),
                ("pages", models.PositiveIntegerField(default=0)),
                ("chars", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("stored", "Stored"),
                            ("extracting", "Extracting"),
                            ("ready", "Ready"),
                            ("no_text", "No Text"),
                            ("failed", "Failed"),
                        ],
                        default="stored",
                        max_length=12,
                    ),
                ),
                (
                    "extract_error",
                    models.CharField(blank=True, default="", max_length=300),
                ),
                (
                    "origin",
                    models.CharField(
                        choices=[("upload", "Upload"), ("chat", "Chat")],
                        default="upload",
                        max_length=8,
                    ),
                ),
                ("thread_id", models.UUIDField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("purged_at", models.DateTimeField(blank=True, null=True)),
                (
                    "owner_department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.department",
                    ),
                ),
                (
                    "owner_lab",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.lab",
                    ),
                ),
                (
                    "owner_project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="research.project",
                    ),
                ),
                (
                    "owner_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        condition=models.Q(("deleted_at__isnull", True)),
                        fields=["sha256"],
                        name="files_sha_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("owner_user__isnull", False),
                                ("owner_lab__isnull", True),
                                ("owner_department__isnull", True),
                                ("owner_project__isnull", True),
                            ),
                            models.Q(
                                ("owner_lab__isnull", False),
                                ("owner_user__isnull", True),
                                ("owner_department__isnull", True),
                                ("owner_project__isnull", True),
                            ),
                            models.Q(
                                ("owner_department__isnull", False),
                                ("owner_user__isnull", True),
                                ("owner_lab__isnull", True),
                                ("owner_project__isnull", True),
                            ),
                            models.Q(
                                ("owner_project__isnull", False),
                                ("owner_user__isnull", True),
                                ("owner_lab__isnull", True),
                                ("owner_department__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="files_stored_one_owner",
                    )
                ],
            },
        ),
    ]
