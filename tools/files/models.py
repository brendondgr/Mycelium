"""A stored file. The database row is the source of truth; the bytes live
under ``data/files/<owner kind>/<owner id>/<file id>/``."""

from __future__ import annotations

import uuid

from apps.core.db import exactly_one
from django.conf import settings
from django.db import models
from django.db.models import Q

OWNER_FIELDS = ("owner_user", "owner_lab", "owner_department", "owner_project")
OWNER_KINDS = {
    "user": "owner_user",
    "lab": "owner_lab",
    "department": "owner_department",
    "project": "owner_project",
}


class StoredFile(models.Model):
    class Status(models.TextChoices):
        STORED = "stored"
        EXTRACTING = "extracting"
        READY = "ready"
        NO_TEXT = "no_text"
        FAILED = "failed"

    class Origin(models.TextChoices):
        UPLOAD = "upload"
        CHAT = "chat"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    owner_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    owner_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    owner_project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Cleaned, for display only. Never part of a path.
    filename = models.CharField(max_length=255)
    #: Sniffed from the bytes: pdf | txt | md | csv | docx.
    kind = models.CharField(max_length=8)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    pages = models.PositiveIntegerField(default=0)
    chars = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.STORED
    )
    extract_error = models.CharField(max_length=300, blank=True, default="")
    origin = models.CharField(
        max_length=8, choices=Origin.choices, default=Origin.UPLOAD
    )
    #: The agent thread it was attached in (no key: files does not depend on
    #: the agent).
    thread_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="files_stored_one_owner", condition=exactly_one(*OWNER_FIELDS)
            ),
        ]
        indexes = [
            models.Index(
                fields=["sha256"],
                name="files_sha_idx",
                condition=Q(deleted_at__isnull=True),
            )
        ]

    @property
    def owner_kind(self) -> str:
        for kind, field in OWNER_KINDS.items():
            if getattr(self, f"{field}_id") is not None:
                return kind
        return ""

    @property
    def owner_id(self) -> str:
        return str(getattr(self, f"{OWNER_KINDS[self.owner_kind]}_id"))

    @property
    def owner(self):
        return getattr(self, OWNER_KINDS[self.owner_kind])

    def __str__(self) -> str:
        return f"{self.filename} ({self.owner_kind}:{self.owner_id})"
