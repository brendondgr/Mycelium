import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField

from apps.core.db import exactly_one, validate_exactly_one

TARGET_FIELDS = ("target_user", "target_project", "target_lab", "target_department")


class ContentItem(models.Model):
    """Global, deduplicated content from external sources (briefing §3).

    Single table with a ``type`` discriminator (paper / grant / fellowship /
    conference) rather than sibling tables — see briefing open question on
    content table shape. The embedding is scored against profile / project /
    lab / dept targets.
    """

    class Type(models.TextChoices):
        PAPER = "paper", "Paper"
        GRANT = "grant", "Grant"
        FELLOWSHIP = "fellowship", "Fellowship"
        CONFERENCE = "conference", "Conference"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=Type.choices)
    source = models.CharField(
        max_length=120,
        help_text="OpenAlex, arXiv, NIH Reporter, grants.gov, etc.",
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "The source's own stable identifier — arXiv id, DOI, NIH project "
            "number, grants.gov opportunity id. Together with ``source`` this "
            "is the dedup key: re-scraping the same item updates it in place "
            "instead of inserting a duplicate."
        ),
    )
    source_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Canonical URL for the item at its source.",
    )
    embedding = VectorField(null=True, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Authors, venue, deadline, agency, etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["type", "source"]),
            models.Index(fields=["source", "external_id"]),
        ]
        constraints = [
            # Partial unique key: one row per (source, external_id) whenever the
            # source gave us an id. Rows without an external_id are exempt so
            # manually-entered items aren't blocked, but scrapers should always
            # set it so re-runs upsert rather than duplicate.
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(external_id=""),
                name="content_item_unique_source_external_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} <{self.source}>"


class RelevanceScore(models.Model):
    """The match between a content item and a scoring target (briefing §3, §6).

    The target is polymorphic — a user's interest profile, a project, a lab, or
    a department — guarded so exactly one target is set. ``signals`` carries the
    per-signal breakdown (including the project-vs-interest weighting) so digests
    can explain why an item surfaced; the weighting lives in the engine, not the
    schema.
    """

    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    target_project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    target_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    target_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    score = models.FloatField()
    signals = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-signal breakdown — the 'why this matters'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.CheckConstraint(
                name="content_relevance_one_target",
                condition=exactly_one(*TARGET_FIELDS),
            ),
            *[
                models.UniqueConstraint(
                    fields=["content", field],
                    name=f"content_relevance_unique_{field}",
                )
                for field in TARGET_FIELDS
            ],
        ]

    def clean(self) -> None:
        validate_exactly_one(self, *TARGET_FIELDS)

    @property
    def target_type(self) -> str:
        """Derived discriminator: ``user`` / ``project`` / ``lab`` / ``department``."""
        if self.target_user_id is not None:
            return "user"
        if self.target_project_id is not None:
            return "project"
        if self.target_lab_id is not None:
            return "lab"
        return "department"

    @property
    def target(self):
        return (
            self.target_user
            or self.target_project
            or self.target_lab
            or self.target_department
        )

    def __str__(self) -> str:
        return f"{self.content} → {self.target_type} ({self.score:.3f})"


class SavedOpportunity(models.Model):
    """A grant / conference / fellowship a user has saved to their deadlines.

    Backs the save system and the Deadlines page. The link to the global
    :class:`ContentItem` is ``SET_NULL`` and a display + deadline **snapshot** is
    stored at save time, so the daily prune of expired opportunities never
    destroys a user's saved deadline — the Deadlines view reads the snapshot even
    after the source item is gone. One save per ``(user, content)``.
    """

    class Area(models.TextChoices):
        GRANT = "grant", "Grant"
        CONFERENCE = "conference", "Conference"
        FELLOWSHIP = "fellowship", "Fellowship"

    class DeadlineKind(models.TextChoices):
        APPLICATION = "application", "Application"
        ABSTRACT = "abstract", "Abstract"
        MANUSCRIPT = "manuscript", "Manuscript"
        EVENT = "event", "Event"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_opportunities",
    )
    content = models.ForeignKey(
        ContentItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="saves",
        help_text="Global source item; nulled if the item is later pruned.",
    )
    area = models.CharField(max_length=20, choices=Area.choices)
    title = models.CharField(max_length=500, help_text="Snapshot at save time.")
    url = models.URLField(max_length=500, blank=True, default="")
    subtitle = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Snapshot of sponsor (grant) or location (conference).",
    )
    deadline_date = models.DateField(
        null=True,
        blank=True,
        help_text="The actionable date this save is tracking (snapshot).",
    )
    deadline_kind = models.CharField(
        max_length=20,
        choices=DeadlineKind.choices,
        default=DeadlineKind.OTHER,
    )
    snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full display fields captured at save time (survives prune).",
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["deadline_date", "created_at"]
        indexes = [
            models.Index(fields=["user", "deadline_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content"],
                condition=Q(content__isnull=False),
                name="content_saved_opportunity_unique_user_content",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} saved {self.area}: {self.title[:40]}"
