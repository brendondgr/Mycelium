import uuid

from django.conf import settings
from django.contrib.postgres.search import SearchVectorField
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
    # Weighted full-text index for query-first search (apps.content.search),
    # kept in sync from ``metadata`` by a Postgres trigger (title/name = A,
    # abstract/summary = B, authors/venue/keywords = C). A real nullable column
    # so ORM inserts still work everywhere; the trigger + GIN index are
    # Postgres-only (see migration 0004), so it simply stays NULL on SQLite —
    # search is Postgres-only. ``editable=False`` keeps it out of forms/admin;
    # the trigger overrides whatever the ORM writes.
    search_vector = SearchVectorField(null=True, editable=False)
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


# --------------------------------------------------------------------------- #
# Project collaboration (briefing Features A / B / D — the Projects page)
# --------------------------------------------------------------------------- #


class ProjectShare(models.Model):
    """A content item a member shared into a project's collaboration feed (A).

    The feed unit. Multiple members may re-share the same paper — there is
    deliberately **no** unique constraint on ``(project, content)``; the feed
    collapses duplicates by content and credits every co-sharer. Display-dedup and
    the "already seen by your team" badge come from :class:`ProjectItemSeen`, not
    from a constraint here.
    """

    class Source(models.TextChoices):
        DIGEST = "digest", "Digest"
        EXTERNAL_LINK = "external_link", "External link"
        COLLECTION = "collection", "Collection"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="shares",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="project_shares",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_shares",
    )
    note = models.TextField(
        blank=True, default="", help_text="The sharer's one-line why."
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.DIGEST
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "created_at"])]

    def __str__(self) -> str:
        return f"{self.shared_by} shared {self.content} → project {self.project_id}"


class ProjectItemSeen(models.Model):
    """The dedup ledger: has this item surfaced in this project, and to whom (B).

    One row per ``(project, content)`` — written the first time an item enters the
    project by any path (digest match, share, external link). ``first_seen_via``
    records that first path and never changes; ``seen_by`` grows as members actually
    view the item in-app. Powers the "already seen by your team" badge and the
    pre-share dedup check.
    """

    class Via(models.TextChoices):
        DIGEST = "digest", "Digest"
        SHARE = "share", "Share"
        EXTERNAL_LINK = "external_link", "External link"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="seen_items",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="project_seen",
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    first_seen_via = models.CharField(max_length=20, choices=Via.choices)
    seen_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="project_items_seen",
        help_text="Members who have actually viewed the item in-app.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "content"],
                name="content_project_item_seen_unique",
            ),
        ]
        indexes = [models.Index(fields=["project", "content"])]

    def __str__(self) -> str:
        return f"seen[{self.first_seen_via}] {self.content} @ project {self.project_id}"


class RelevanceEvent(models.Model):
    """An append-only engagement event — a weak relevance label (Feature D).

    Every view / save / share / thumb / dismiss is logged with a config-driven
    weight (``settings.RELEVANCE_EVENT_WEIGHTS``). This is the ground-truth stream a
    future team-relevance recompute (and the evaluation harness) will read; it never
    mutates any individual profile. ``project`` is nullable so the same log can carry
    non-project engagement later.
    """

    class Action(models.TextChoices):
        VIEW = "view", "View"
        SAVE = "save", "Save"
        SHARE = "share", "Share"
        THUMBS_UP = "thumbs_up", "Thumbs up"
        THUMBS_DOWN = "thumbs_down", "Thumbs down"
        DISMISS = "dismiss", "Dismiss"
        OPEN_EXTERNAL = "open_external", "Open external"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="relevance_events",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_events",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="relevance_events",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    weight = models.FloatField(
        help_text="Per-action weight at capture time (config-driven)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["user", "content"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.action} {self.content} ({self.weight:+.2f})"


class Collection(models.Model):
    """A shared reading list within a project (briefing Feature C).

    A named, ordered-ish bucket of content items a project curates together —
    "papers for the Aim 2 review", "methods to try". Archiving hides it from the
    default list but keeps its items for audit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="collections",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_collections",
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "is_archived"])]

    def __str__(self) -> str:
        return f"{self.name} (project {self.project_id})"


class CollectionItem(models.Model):
    """One content item in a shared collection (briefing Feature C).

    ``unique_together (collection, content)`` keeps a paper from being added twice —
    a duplicate add is a no-op, not an error.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        related_name="items",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="collection_items",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="added_collection_items",
    )
    note = models.TextField(blank=True, default="")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-added_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "content"],
                name="content_collection_item_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.content} in {self.collection_id}"


class ProjectProfile(models.Model):
    """A project's recomputed team-relevance signal (briefing Feature D).

    Separate from any individual :class:`~apps.accounts.models.Profile` — the team
    signal updates the *project*, never the member (project principle). The derived
    vector itself is written to ``research.Project.embedding`` (previously unused) so
    the recommendation pipeline can read it as the project's query vector; this row
    carries the aggregated interest terms and the recompute bookkeeping.
    """

    class Reason(models.TextChoices):
        MEMBERSHIP_CHANGE = "membership_change", "Membership change"
        ENGAGEMENT = "engagement", "Engagement"
        MANUAL = "manual", "Manual"

    project = models.OneToOneField(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="team_profile",
    )
    interests = models.JSONField(
        default=dict,
        blank=True,
        help_text="Aggregated / deduped interest terms from members + engagement.",
    )
    last_recomputed = models.DateTimeField(null=True, blank=True)
    recompute_reason = models.CharField(
        max_length=20, choices=Reason.choices, blank=True, default=""
    )

    def __str__(self) -> str:
        return f"team profile for project {self.project_id}"


class MemberSuggestion(models.Model):
    """A shared item scored against one member's profile (briefing Feature F).

    Written by the cross-member fan-out when a paper enters a project: for each
    other member, the item is scored (normalized cosine, never an RRF rank) against
    their individual profile. ``suggested=True`` rows are delivered in-app; below-floor
    rows are still persisted (``suggested=False``) as audited abstentions. One row per
    ``(user, content)`` — a member is never notified twice for the same paper.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_suggestions",
    )
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="member_suggestions",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="member_suggestions",
    )
    origin_share = models.ForeignKey(
        ProjectShare,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suggestions",
    )
    score = models.FloatField(help_text="Normalized cosine, member profile vs item.")
    suggested = models.BooleanField(
        help_text=(
            "True = delivered; False = below-floor abstention, persisted for audit."
        )
    )
    floor_used = models.FloatField(
        help_text="The cosine floor applied at decision time."
    )
    delivered_via = models.CharField(max_length=20, blank=True, default="")
    dismissed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content"],
                name="content_member_suggestion_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "suggested", "dismissed"]),
        ]

    def __str__(self) -> str:
        verb = "suggest" if self.suggested else "abstain"
        return f"{verb} {self.content} → {self.user} ({self.score:.3f})"
