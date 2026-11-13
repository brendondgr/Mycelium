"""Go-public hardening (plan 20261112-go-public-readiness, Phases 1–2).

* ``OrgInvite.token`` becomes ``token_hash``: every existing token is replaced
  by its SHA-256 digest in place, so live links keep working (they are looked
  up by the digest of what the visitor presents) while the table stops holding
  anything spendable.
* ``LabAttachRequest``: a department asks, the lab's owner decides.
* ``AuthorWork.verified``: new self-service imports are claims. Works stored
  before this migration are grandfathered as verified — there is no record of
  how each was imported, and un-verifying them all would silently empty every
  existing co-authorship and "demonstrated" edge.
* ``EmailVerification.Purpose`` gains ``delete`` for account deletion codes.
"""

import hashlib
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def hash_tokens(apps, schema_editor):
    OrgInvite = apps.get_model("accounts", "OrgInvite")
    for invite in OrgInvite.objects.all().only("pk", "token_hash"):
        raw = invite.token_hash or ""
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        OrgInvite.objects.filter(pk=invite.pk).update(token_hash=digest)


def grandfather_works(apps, schema_editor):
    AuthorWork = apps.get_model("accounts", "AuthorWork")
    AuthorWork.objects.all().update(verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0032_org_limit_overrides"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # -- OrgInvite: keep the column, store the digest ------------------------
        migrations.RemoveIndex(
            model_name="orginvite",
            name="accounts_orginvite_token",
        ),
        migrations.RenameField(
            model_name="orginvite",
            old_name="token",
            new_name="token_hash",
        ),
        migrations.RunPython(hash_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="orginvite",
            name="token_hash",
            field=models.CharField(
                help_text=(
                    "SHA-256 hex digest of the token; the token itself is not kept."
                ),
                max_length=64,
                unique=True,
            ),
        ),
        # -- AuthorWork.verified -------------------------------------------------
        migrations.AddField(
            model_name="authorwork",
            name="verified",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(grandfather_works, migrations.RunPython.noop),
        # -- EmailVerification purpose ------------------------------------------
        migrations.AlterField(
            model_name="emailverification",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("signup", "Sign-up confirmation"),
                    ("change", "Email change"),
                    ("password", "Password change"),
                    ("delete", "Account deletion"),
                ],
                default="signup",
                max_length=20,
            ),
        ),
        # -- LabAttachRequest ----------------------------------------------------
        migrations.CreateModel(
            name="LabAttachRequest",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("declined", "Declined"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lab_attach_requests",
                        to="accounts.department",
                    ),
                ),
                (
                    "lab",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attach_requests",
                        to="accounts.lab",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lab_attach_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "responded_by",
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
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "pending")),
                        fields=("department", "lab"),
                        name="accounts_unique_pending_lab_attach",
                    )
                ],
            },
        ),
    ]
