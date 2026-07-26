import uuid

from django.conf import settings
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField

from apps.core.db import exactly_one, validate_exactly_one

TARGET_FIELDS = ("target_user", "target_project", "target_lab", "target_department")

#: Reminder subscriptions carry a personal OR lab target (extends to project later).
REMINDER_TARGET_FIELDS = ("target_user", "target_lab")


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
    """An item bookmarked to a personal workspace **or** to a lab.

    Backs the save system and the Saves (bookmarks) page. The link to the global
    :class:`ContentItem` is ``SET_NULL`` and a display + deadline **snapshot** is
    stored at save time, so the daily prune of expired opportunities never
    destroys a save — the Saves view falls back to the snapshot even after the
    source item is gone. Papers carry no deadline; the deadline fields stay null.

    ``user`` is always the **actor** who saved the item. A **personal** save has
    ``target_lab`` null and belongs to that user (unique ``(user, content)``). A
    **lab** save has ``target_lab`` set and belongs to the lab (unique
    ``(target_lab, content)`` — one per lab regardless of which manager added it);
    ``user`` then records who added it. Only a lab manager may create or remove a
    lab save (enforced in the view).
    """

    class Area(models.TextChoices):
        GRANT = "grant", "Grant"
        CONFERENCE = "conference", "Conference"
        FELLOWSHIP = "fellowship", "Fellowship"
        PAPER = "paper", "Paper"

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
    target_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="saved_opportunities",
        help_text="Set for a lab save; null for a personal save.",
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
            models.Index(fields=["target_lab", "deadline_date"]),
        ]
        constraints = [
            # One personal save per (user, content) — personal saves only.
            models.UniqueConstraint(
                fields=["user", "content"],
                condition=Q(content__isnull=False, target_lab__isnull=True),
                name="content_saved_opportunity_unique_user_content",
            ),
            # One lab save per (lab, content), regardless of which manager added it.
            models.UniqueConstraint(
                fields=["target_lab", "content"],
                condition=Q(content__isnull=False, target_lab__isnull=False),
                name="content_saved_opportunity_unique_lab_content",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} saved {self.area}: {self.title[:40]}"


class ContentDeadline(models.Model):
    """One addressable deadline on a :class:`ContentItem` (Discord reminders R0).

    A **projection**, not a new source of truth: rebuilt on every opportunity
    upsert from the same status functions the feed already uses
    (:mod:`apps.content.deadlines_projection`). A conference yields up to three
    rows (abstract / manuscript / event); a grant or fellowship yields one
    APPLICATION row. Rolling / continuous fellowships get a row with a null
    ``due_date`` so the UI can explain "no date — can't remind" instead of
    silently omitting them.

    The row is updated **in place** when a date moves — hence the unique key is
    ``(content, kind)``, not ``(content, kind, due_date)`` — so ``changed_at`` is
    meaningful and a reminder keeps pointing at a stable row. ``previous_due_date``
    + ``changed_at`` are the signal the DEADLINE_MOVED announcement (R6) reads;
    nothing here re-fires reminders, which compute their own dates on read.
    """

    class Confidence(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"  # conference date / fellowship "true"
        ANTICIPATED = "anticipated", "Anticipated"  # fellowship "anticipated" — moves
        ROLLING = "rolling", "Rolling"  # continuous / rolling — no date, unremindable
        UNKNOWN = "unknown", "Unknown"  # varies / suspended / unparseable

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="deadline_rows",
    )
    kind = models.CharField(
        max_length=20,
        choices=SavedOpportunity.DeadlineKind.choices,
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Null iff confidence is rolling or unknown (no remindable date).",
    )
    label = models.CharField(max_length=200, blank=True, default="")
    confidence = models.CharField(max_length=20, choices=Confidence.choices)
    previous_due_date = models.DateField(
        null=True,
        blank=True,
        help_text="The prior date, set when due_date last moved (corroboration).",
    )
    previous_confidence = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="The prior confidence, set on a change — e.g. anticipated→confirmed.",
    )
    changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time due_date actually moved — drives DEADLINE_MOVED (R6).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["content", "kind"],
                name="content_deadline_unique_content_kind",
            ),
        ]
        indexes = [models.Index(fields=["due_date", "kind"])]

    def __str__(self) -> str:
        return (
            f"{self.get_kind_display()} deadline "
            f"{self.due_date or '—'} ({self.confidence})"
        )


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


class DailyBriefing(models.Model):
    """One user's current cross-category "Mylo Report".

    A written 2–3 paragraph synthesis over the day's top papers, grants,
    conferences, and fellowships — gated to the categories the user watches
    (``accounts.WatchPreference.categories``) — alongside the numeric counts and
    the top showcase items the prose is grounded in. This is the durable record
    behind ``GET /api/daily-briefing/`` and the Daily page's three-zone layout.

    One row per user (a OneToOne), replaced in place by each daily run's
    ``generate_daily_briefing`` stage: the app always serves the newest briefing
    and the table cannot grow unbounded. ``origin`` records whether the language
    model wrote the body or the deterministic fallback did, mirroring the paper
    and opportunity pipelines so the surface is honest when the LLM is down.
    """

    class Origin(models.TextChoices):
        LLM = "llm", "LLM"
        FALLBACK = "fallback", "Fallback"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # A briefing belongs to exactly one target: a person or a lab (the exactly_one
    # constraint below). A lab briefing synthesizes the lab's aggregate matches.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="daily_briefing",
    )
    lab = models.OneToOneField(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="daily_briefing",
    )
    body = models.TextField(
        blank=True,
        default="",
        help_text="The 2–3 paragraph briefing prose (Mylo's voice).",
    )
    origin = models.CharField(
        max_length=20,
        choices=Origin.choices,
        default=Origin.FALLBACK,
        help_text="Whether the LLM or the deterministic fallback wrote the body.",
    )
    categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Snapshot of the watched categories this briefing covered.",
    )
    counts = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-category item counts, e.g. {'papers': 12, 'grants': 3}.",
    )
    new_counts = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-category counts of items first seen this week (signals.is_new) — "
            "what the briefing leads with; counts keeps the total matched."
        ),
    )
    showcase = models.JSONField(
        default=dict,
        blank=True,
        help_text="Top items per category the briefing references (grounding).",
    )
    generated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this briefing was last (re)generated.",
    )

    class Meta:
        ordering = ["-generated_at"]
        constraints = [
            models.CheckConstraint(
                name="content_dailybriefing_exactly_one_target",
                condition=exactly_one("user", "lab"),
            ),
        ]

    def clean(self) -> None:
        validate_exactly_one(self, "user", "lab")

    def __str__(self) -> str:
        return f"DailyBriefing<{self.user or self.lab}> ({self.origin})"


# --------------------------------------------------------------------------- #
# Deadline reminders & notifications (Discord reminders R1)
# --------------------------------------------------------------------------- #


def default_reminder_offsets() -> list[dict]:
    """The lab default offsets: one month, one week, and one day before."""
    return [
        {"amount": 1, "unit": "month"},
        {"amount": 1, "unit": "week"},
        {"amount": 1, "unit": "day"},
    ]


class ReminderSubscription(models.Model):
    """A standing reminder for one deadline on one target (personal or lab).

    Mirrors :class:`RelevanceScore`'s polymorphic target: exactly one of
    ``target_user`` / ``target_lab`` is set (the ``exactly_one`` helper, same as
    ``RelevanceScore``). The link to the live item is ``SET_NULL`` and a
    **snapshot** (title / url / due_date / confidence) is kept, so the reminder
    survives the daily prune exactly as :class:`SavedOpportunity` does; while the
    item is alive the snapshot's ``due_date`` is resynced from the
    :class:`ContentDeadline` projection on every tick. Nothing here stores a fire
    schedule — the tick computes fire dates on read from whatever ``due_date`` the
    row currently holds (see :mod:`apps.content.reminders_tick`).
    """

    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        FIRED_OUT = "fired_out", "Fired out"
        CANCELLED = "cancelled", "Cancelled"
        STALE = "stale", "Stale"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    target_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    content = models.ForeignKey(
        ContentItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reminders",
        help_text="Live item; nulled when pruned — the snapshot then drives the tick.",
    )
    deadline_kind = models.CharField(
        max_length=20,
        choices=SavedOpportunity.DeadlineKind.choices,
    )
    # --- Snapshot: survives prune; due_date/confidence resynced each tick. ---
    area = models.CharField(max_length=20, choices=SavedOpportunity.Area.choices)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=500, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    confidence = models.CharField(
        max_length=20,
        choices=ContentDeadline.Confidence.choices,
        default=ContentDeadline.Confidence.CONFIRMED,
    )
    channel_id_override = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Lab only: a specific channel instead of the lab default.",
    )
    # Suppress firing until this date (exclusive). Deliberately *not* a seal: the
    # offsets stay unsealed while snoozed, so when the date passes the still-pending
    # ones trigger and the one-message-per-day collapse sends a single reminder with
    # the true days remaining. Sealing instead would swallow the reminder rather than
    # defer it — the difference between "later" and "never".
    snoozed_until = models.DateField(null=True, blank=True)
    has_unlinked_targets = models.BooleanField(
        default=False,
        help_text="A mention target has no active Discord identity (portal prompts).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_reminders",
    )
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "created_at"]
        constraints = [
            models.CheckConstraint(
                name="content_reminder_one_target",
                condition=exactly_one(*REMINDER_TARGET_FIELDS),
            ),
            models.UniqueConstraint(
                fields=["target_user", "content", "deadline_kind"],
                condition=Q(content__isnull=False, target_user__isnull=False),
                name="content_reminder_unique_user_content_kind",
            ),
            models.UniqueConstraint(
                fields=["target_lab", "content", "deadline_kind"],
                condition=Q(content__isnull=False, target_lab__isnull=False),
                name="content_reminder_unique_lab_content_kind",
            ),
        ]
        indexes = [models.Index(fields=["state", "due_date"])]

    def clean(self) -> None:
        validate_exactly_one(self, *REMINDER_TARGET_FIELDS)

    @property
    def target_type(self) -> str:
        return "user" if self.target_user_id is not None else "lab"

    @property
    def is_lab(self) -> bool:
        return self.target_lab_id is not None

    def __str__(self) -> str:
        return f"reminder<{self.target_type}> {self.title[:40]} ({self.deadline_kind})"


class ReminderOffset(models.Model):
    """One "N units before the deadline" trigger on a subscription.

    Free-form: any positive amount + any unit. Stored, never pre-materialized into a
    schedule — the tick subtracts it from the live ``due_date`` with calendar math
    (:func:`dateutil.relativedelta.relativedelta`). ``(1, week)`` and ``(7, day)`` are
    distinct rows that may resolve to the same fire date; the tick dedupes by the
    computed date and fires once.
    """

    class Unit(models.TextChoices):
        DAY = "day", "Day"
        WEEK = "week", "Week"
        MONTH = "month", "Month"
        YEAR = "year", "Year"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        ReminderSubscription,
        on_delete=models.CASCADE,
        related_name="offsets",
    )
    amount = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    unit = models.CharField(max_length=10, choices=Unit.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "amount", "unit"],
                name="content_reminder_offset_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.unit}(s) before"


class ReminderMention(models.Model):
    """A lab member to @-mention when a lab reminder fires (user mentions only)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        ReminderSubscription,
        on_delete=models.CASCADE,
        related_name="mentions",
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reminder_mentions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "member"],
                name="content_reminder_mention_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"mention {self.member} on {self.subscription_id}"


class ReminderFire(models.Model):
    """The fired-ledger: one row per offset sealed by a fire or a skip.

    NOT a pre-materialized schedule — written only when the tick fires or seals an
    offset. ``idempotency_key`` embeds the ``due_date`` it was computed against, so a
    moved deadline changes the key and re-opens the offset; a stable deadline keeps
    the seal and prevents a re-fire. One fire per subscription per day, regardless of
    how many offsets triggered — all triggering offsets are sealed by that one fire.
    """

    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        DISCORD_DM = "discord_dm", "Discord DM"
        DISCORD_CHANNEL = "discord_channel", "Discord channel"

    class Result(models.TextChoices):
        SENT = "sent", "Sent"
        QUEUED = "queued", "Queued"  # handed to the outbox; delivery is its record
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        ReminderSubscription,
        on_delete=models.CASCADE,
        related_name="fires",
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    fired_on = models.DateField(db_index=True)
    days_remaining = models.IntegerField(null=True, blank=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    state = models.CharField(max_length=20, choices=Result.choices)
    skip_reason = models.CharField(max_length=40, blank=True, default="")
    # The outbox row this fire handed its Discord message to, by dedupe key rather
    # than a foreign key: the seal belongs to `content`, the delivery record belongs
    # to `integrations`, and neither app needs to know the other's schema to join
    # them. Blank when the fire had nothing to send to Discord.
    outbox_key = models.CharField(max_length=200, blank=True, default="")
    discord_message_id = models.CharField(max_length=32, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.IntegerField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["subscription", "fired_on"])]

    def __str__(self) -> str:
        return f"fire[{self.state}] {self.idempotency_key}"


class LabReminderPolicy(models.Model):
    """A lab's default offsets + default mention targets for new lab reminders.

    Without defaults, "set a lab reminder" is a six-field form nobody uses.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab = models.OneToOneField(
        "accounts.Lab",
        on_delete=models.CASCADE,
        related_name="reminder_policy",
    )
    default_offsets = models.JSONField(default=default_reminder_offsets, blank=True)
    default_mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="reminder_policy_defaults",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"reminder policy for lab {self.lab_id}"


class Notification(models.Model):
    """One in-app notification for the header bell (reminders rework, D-2 / D-3).

    Replaces the old compute-on-the-fly deadline scan. Three sources, one bell: a
    fired reminder, a moved deadline, and a high-signal recommendation. A snapshot
    (title / body / url) is stored so it survives the source item's prune;
    ``dedupe_key`` makes delivery idempotent.
    """

    class Kind(models.TextChoices):
        REMINDER = "reminder", "Reminder"
        DEADLINE_MOVED = "deadline_moved", "Deadline moved"
        HIGH_SIGNAL = "high_signal", "High signal"
        # Mylo gave up delivering something to Discord. In-app is the only channel
        # that can carry this: if Discord is the broken thing, a Discord message
        # would fail for the same reason the original one did.
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    content = models.ForeignKey(
        ContentItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    title = models.CharField(max_length=500)
    body = models.TextField(blank=True, default="")
    url = models.URLField(max_length=500, blank=True, default="")
    dedupe_key = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "dismissed_at", "created_at"])]

    def __str__(self) -> str:
        return f"notif[{self.kind}] {self.user} {self.title[:30]}"
