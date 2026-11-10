"""The public demo's two records: which world it shows, and who has asked Mylo.

The world itself — the department, lab, people and projects — is ordinary
``apps.accounts`` / ``apps.research`` rows, built by ``manage.py demo build``
from ``world.yaml``. That is the point: the nightly run ranks them, and the app
shows them, exactly as it would anyone's. :class:`DemoWorld` only records which
rows they are, so the middleware knows whom a visitor looks around as and the
teardown knows what to remove.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class DemoWorld(models.Model):
    """The one demo world (``key="default"``)."""

    key = models.CharField(max_length=32, unique=True, default="default")
    #: The person a visitor looks around as: the lab's PI, also in the department.
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    lab = models.ForeignKey("accounts.Lab", on_delete=models.CASCADE, related_name="+")
    department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    #: ``version`` from ``world.yaml`` when it was built.
    fixture_version = models.PositiveIntegerField(default=1)
    built_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"demo world {self.key} ({self.lab_id})"


class DemoQuestion(models.Model):
    """One question a demo visitor asked Mylo: the budget is counted from these.

    ``visitor`` is the random id in the visitor's signed cookie; ``ip_hash`` is
    a keyed hash of their network address (never the address itself). Rows
    older than the visitor window are purged as new ones are taken.
    """

    visitor = models.CharField(max_length=64, db_index=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    thread_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
