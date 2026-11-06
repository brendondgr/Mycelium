import uuid

from django.conf import settings
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
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


class IgnoredItem(models.Model):
    """One item a reader has chosen not to be shown again (manual ignore).

    The mirror image of :class:`SavedOpportunity`: where a save says "keep this
    in front of me", an ignore says "stop surfacing this". It is a **per-reader
    display filter**, not a deletion and not a ranking signal — the
    :class:`ContentItem` and its :class:`RelevanceScore` rows are untouched, so
    the item stays in the corpus, stays rankable, and stays visible to everyone
    else. Nothing here feeds back into any profile; the engagement label lives
    in :class:`RelevanceEvent` (action ``dismiss``), which nothing reads yet.

    Deliberately **no snapshot**. A save must survive the nightly prune because
    the reader asked to keep it; an ignore is meaningless once the item is gone,
    so ``content`` cascades and the row disappears with it.

    An ignore and a *personal* save are mutually exclusive (enforced in the
    view): ignoring drops the personal save, saving clears the ignore, so the
    Saves page and the feeds can never disagree about one item. Lab saves belong
    to the lab, not to this reader, and are left alone.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ignored_items",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="ignores",
    )
    area = models.CharField(
        max_length=20,
        choices=SavedOpportunity.Area.choices,
        help_text="Which feed the item was ignored from (mirrors the save areas).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "content"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content"],
                name="content_ignored_item_unique_user_content",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} ignored {self.area}: {self.content_id}"


class ContentDeadline(models.Model):
    """One addressable deadline on a :class:`ContentItem` (Discord reminders R0).

    A **projection**, not a new source of truth: rebuilt on every opportunity
    upsert from the same status functions the feed already uses
    (:mod:`apps.content.deadlines_projection`). A conference yields **one row per
    dated round** plus an event row; a grant or fellowship yields one APPLICATION
    row. Rolling / continuous fellowships get a row with a null ``due_date`` so
    the UI can explain "no date — can't remind" instead of silently omitting
    them.

    Per-round, not per-kind
    ------------------------------------------------------------------------
    The original design keyed on ``(content, kind)`` and each row held only its
    kind's *next* future date, so a specific non-next round was never
    individually remindable. That is wrong for the thing conferences actually
    do: a venue routinely carries a workshop deadline, two full-paper rounds, a
    camera-ready and a notification, and "remind me about the second paper
    round" is the ordinary request. The key is therefore ``(content, kind,
    round_key)``.

    ``round_key`` is the collector's own deadline identity — ``"<collector
    kind>:<normalized round label>"`` — mirroring
    ``apps.scraper.collect.conferences.record.Deadline.identity``, which is
    deliberately *type plus label and never the date*, so an extension updates
    an entry in place rather than appending a duplicate. Borrowing it is what
    makes the key stable across re-scrapes: a moved deadline keeps its row, so
    ``changed_at`` stays meaningful and a reminder keeps pointing at the round
    the reader chose. Measured over the live corpus (2026-08-17): 1,120 dated
    entries across 912 conferences, **zero** ``(kind, label)`` collisions.
    ``""`` for the single-round cases (grant, fellowship, and a conference's
    event row).

    ``is_next`` marks the earliest future row of each kind — what a card's
    headline deadline reads, so the display never has to re-derive it.

    ``previous_due_date`` + ``changed_at`` are the signal the DEADLINE_MOVED
    announcement (R6) reads; nothing here re-fires reminders, which compute
    their own dates on read.
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
    round_key = models.CharField(
        max_length=160,
        blank=True,
        default="",
        help_text=(
            "Stable identity of this round within its item — the collector's "
            "'<kind>:<normalized label>'. Empty for a single-round deadline."
        ),
    )
    round_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="The source's own round wording ('round 2'), verbatim.",
    )
    is_next = models.BooleanField(
        default=True,
        help_text="This is the earliest future row of its kind (the headline one).",
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
        ordering = ["due_date", "kind", "round_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["content", "kind", "round_key"],
                name="content_deadline_unique_content_kind_round",
            ),
        ]
        indexes = [models.Index(fields=["due_date", "kind"])]

    def __str__(self) -> str:
        round_part = f" ({self.round_label})" if self.round_label else ""
        return (
            f"{self.get_kind_display()} deadline{round_part} "
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
    """One target's cross-category "Mylo Report" for one day.

    A written 2–3 paragraph synthesis over the day's top papers, grants,
    conferences, and fellowships — gated to the categories the user watches
    (``accounts.WatchPreference.categories``) — alongside the numeric counts and
    the top showcase items the prose is grounded in. This is the durable record
    behind ``GET /api/daily-briefing/`` and the Daily page's three-zone layout.

    One row per target **per day** (``generated_on``): the daily run's
    ``generate_daily_briefing`` stage upserts on that key, so a same-day rerun
    replaces the day in place while yesterday's report survives. The Reports page
    reads the history; ``prune_briefings`` keeps it to
    ``settings.BRIEFING_RETENTION_DAYS``. Every "current briefing" reader must
    order by ``-generated_on`` explicitly rather than lean on ``Meta.ordering``.
    ``origin`` records whether the language model wrote the body or the
    deterministic fallback did, mirroring the paper and opportunity pipelines so
    the surface is honest when the LLM is down.
    """

    class Origin(models.TextChoices):
        LLM = "llm", "LLM"
        FALLBACK = "fallback", "Fallback"
        #: Nothing entered the reader's Top-25, so yesterday's body was carried
        #: forward verbatim rather than re-worded to say the same thing.
        CARRIED = "carried", "Carried forward"

    class Kind(models.TextChoices):
        """Which report this row is.

        Two rows can exist for one target on one date: Monday carries both the
        daily (written for the web, as every day is) and the weekly. They are
        separate rows rather than one row with two bodies because they have
        different lifetimes on the Reports page and different readers — a reader
        catching up on Thursday wants Monday's daily, not its weekly.
        """

        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # A briefing belongs to exactly one target: a person or a lab (the exactly_one
    # constraint below). A lab briefing synthesizes the lab's aggregate matches.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="daily_briefings",
    )
    lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="daily_briefings",
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
        help_text=(
            "Whether the LLM wrote the body, the deterministic fallback did, or it "
            "was carried forward from the previous day (nothing new to say)."
        ),
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
            "Per-category counts of items that entered the target's Top-25 on this "
            "run — what the briefing leads with; counts keeps the total matched."
        ),
    )
    showcase = models.JSONField(
        default=dict,
        blank=True,
        help_text="Top items per category the briefing references (grounding).",
    )
    project_summary = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "The report's summary table: one row per part (Personal first, then "
            "each project), each carrying the count of items that entered that "
            "part's Top-25 per category. Empty on briefings written before the "
            "table existed."
        ),
    )
    narrative = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Mylo's prose as structure rather than markdown: "
            "{'lead', 'lead_origin', 'themes': [{'cluster_id', 'label', 'read', "
            "'origin'}]}. Stored once per run and read back by the PDF, the app, "
            "and the Discord message, so the three can never carry different "
            "wordings of the same day — and so a re-render never re-bills the "
            "model for prose that already exists."
        ),
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.DAILY,
        db_index=True,
        help_text="Daily or weekly. Every existing reader keeps reading dailies.",
    )
    stats = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "The run's statistics as structure — overnight volume, what matched, "
            "what entered, the per-category / per-project / per-theme splits, "
            "alerts and the deadline horizon. Stored so the web header and the "
            "Discord post show identical numbers rather than each deriving their "
            "own from the same rows at two different moments."
        ),
    )
    verification = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "The citation verifier's record for a weekly: claims checked, "
            "supported, removed, and the sentences it removed with the check "
            "that failed. Empty on a daily, which cites nothing the model wrote "
            "without a packet behind it."
        ),
    )
    context_version = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "A digest of what the report was written against: the declared "
            "profile, the understanding the person confirmed, and the project "
            "developments in effect (ambient Plan 05). Two reports with the same "
            "version were written against the same picture of the reader; an "
            "old report stays interpretable because its version is known."
        ),
    )
    generated_on = models.DateField(
        db_index=True,
        default=timezone.localdate,
        help_text="The local date this briefing covers — the history key.",
    )
    generated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this briefing was last (re)generated.",
    )

    class Meta:
        ordering = ["-generated_on", "-generated_at"]
        constraints = [
            models.CheckConstraint(
                name="content_dailybriefing_exactly_one_target",
                condition=exactly_one("user", "lab"),
            ),
            # One briefing per target per day. Split in two and conditioned on the
            # populated side: a plain unique_together over a nullable column lets
            # Postgres treat every NULL as distinct, which would not constrain the
            # lab rows at all (and vice versa).
            models.UniqueConstraint(
                fields=["user", "generated_on", "kind"],
                condition=Q(user__isnull=False),
                name="content_dailybriefing_user_day_kind_unique",
            ),
            models.UniqueConstraint(
                fields=["lab", "generated_on", "kind"],
                condition=Q(lab__isnull=False),
                name="content_dailybriefing_lab_day_kind_unique",
            ),
        ]

    @classmethod
    def latest_for(cls, kind: str = Kind.DAILY, **target) -> "DailyBriefing | None":
        """The newest briefing of one kind for one target (``user=``/``lab=``).

        Every "current briefing" surface goes through here. Ordering is stated
        rather than inherited from ``Meta``: now that the table keeps history, a
        bare ``.filter(user=…).first()`` would return an arbitrary day.

        ``kind`` defaults to ``daily`` so every existing reader — the app, the PDF,
        the Discord message, the resend command — keeps reading exactly what it was
        reading before the weekly existed. A caller that wants the weekly has to
        ask for it, which is the right direction for a default to fail in: a daily
        surface accidentally rendering last Monday's weekly would be a much louder
        wrong answer than the reverse.
        """
        return (
            cls.objects.filter(kind=kind, **target)
            .order_by("-generated_on")
            .first()
        )

    def clean(self) -> None:
        validate_exactly_one(self, "user", "lab")

    def __str__(self) -> str:
        owner = self.user or self.lab
        return f"DailyBriefing<{owner}> {self.generated_on} {self.kind} ({self.origin})"


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
    deadline_round_key = models.CharField(
        max_length=160,
        blank=True,
        default="",
        help_text=(
            "Which round of that kind this reminder is for — the matching "
            "ContentDeadline.round_key. Empty for a single-round deadline."
        ),
    )
    # --- Snapshot: survives prune; due_date/confidence resynced each tick. ---
    area = models.CharField(max_length=20, choices=SavedOpportunity.Area.choices)
    title = models.CharField(max_length=500)
    round_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Snapshot of the round's wording, so a fired message can name it.",
    )
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
            # Widened by the round: two reminders on the *same* conference and
            # the *same* kind are legitimate when they point at different
            # rounds ("warn me about both paper deadlines"), which is the whole
            # point of the per-round projection.
            models.UniqueConstraint(
                fields=[
                    "target_user",
                    "content",
                    "deadline_kind",
                    "deadline_round_key",
                ],
                condition=Q(content__isnull=False, target_user__isnull=False),
                name="content_reminder_unique_user_content_round",
            ),
            models.UniqueConstraint(
                fields=[
                    "target_lab",
                    "content",
                    "deadline_kind",
                    "deadline_round_key",
                ],
                condition=Q(content__isnull=False, target_lab__isnull=False),
                name="content_reminder_unique_lab_content_round",
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
    """Someone (or everyone) to @-mention when a lab reminder fires.

    Originally this was strictly "a Mycelium user who is a member of this lab",
    which is the right guard against Mylo being used to ping arbitrary people —
    but too narrow for the actual job. A lab's Discord contains collaborators,
    students and staff who have no Mycelium account, and the deadline that
    matters to them is the one the alert is about.

    So a mention is now one of three kinds, and the guard moves rather than
    disappearing: a ``USER`` or ``ROLE`` mention carries a raw ``discord_id``
    which must belong to **that lab's own guild**, checked before it is stored
    (:mod:`apps.content.reminders_views`), so the blast radius is still the one
    server the alert already posts to. ``EVERYONE`` carries no id at all.

    ``member`` stays, nullable, for a target that *is* a linked Mycelium user:
    that is the only case where the display name can be resolved from Mycelium
    itself and where "this person hasn't linked Discord yet" is answerable, which
    is what ``has_unlinked_targets`` reports.
    """

    class Kind(models.TextChoices):
        USER = "user", "User"
        ROLE = "role", "Role"
        EVERYONE = "everyone", "Everyone"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        ReminderSubscription,
        on_delete=models.CASCADE,
        related_name="mentions",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.USER)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reminder_mentions",
        help_text="Set only when the target is a linked Mycelium user.",
    )
    discord_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Guild member or role snowflake; empty for an @everyone mention.",
    )
    display_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="What to show in the portal for a target with no Mycelium user.",
    )

    class Meta:
        constraints = [
            # Unchanged for the Mycelium-user case, and still partial so the two
            # id-less EVERYONE rows a subscription could otherwise collect are
            # not what this key is about.
            models.UniqueConstraint(
                fields=["subscription", "member"],
                condition=Q(member__isnull=False),
                name="content_reminder_mention_unique",
            ),
            models.UniqueConstraint(
                fields=["subscription", "kind", "discord_id"],
                condition=~Q(discord_id=""),
                name="content_reminder_mention_unique_discord",
            ),
            # At most one @everyone per subscription — a second would simply
            # double the ping.
            models.UniqueConstraint(
                fields=["subscription"],
                condition=Q(kind="everyone"),
                name="content_reminder_mention_single_everyone",
            ),
        ]

    @property
    def label(self) -> str:
        """What a human calls this target, whichever kind it is."""
        if self.kind == self.Kind.EVERYONE:
            return "@everyone"
        if self.member_id is not None:
            return self.member.get_full_name() or self.member.get_username()
        return self.display_name or self.discord_id

    def __str__(self) -> str:
        return f"mention {self.label} on {self.subscription_id}"


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
        #: Something found today changes what a project should do — an overlap
        #: with its claim, an unblocked blocker, a venue that just became
        #: reachable, a deadline that moved. Unlike the three above, it is about
        #: a *project*, so the bell links into the project rather than the item.
        PROJECT_ALERT = "project_alert", "Project alert"
        # Mylo gave up delivering something to Discord. In-app is the only channel
        # that can carry this: if Discord is the broken thing, a Discord message
        # would fail for the same reason the original one did.
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"
        # Collaboration-network plan CN-04: "your open-to-collaboration setting
        # ends soon". Never anything about who searched.
        COLLAB_RENEWAL = "collab_renewal", "Collaboration setting ending"
        # Ambient profile (Plans 06-07): Mylo has a question; something the
        # person confirmed has taken effect; something was undone.
        SUGGESTION_PENDING = "suggestion_pending", "Mylo has a question"
        CHANGE_APPLIED = "change_applied", "A change you confirmed took effect"
        CHANGE_UNDONE = "change_undone", "A change was undone"

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


class ItemComprehension(models.Model):
    """A structured précis of one content item, written once and reused forever.

    Stage one of the two-stage model pipeline. It is deliberately **profile-blind**
    — no reader, no interests, no relevance judgement in the input — which is what
    makes one extraction serve every user and every theme indefinitely. That is
    both where the depth in the final write-ups comes from and where the cost
    saving lives: the fit stage that follows reads this instead of six hundred
    truncated characters of abstract, and never pays to re-read the paper.

    Every field is grounded in the source text. An absent field is left empty
    rather than inferred, and ``thin`` marks a source too sparse to support a
    précis at all — a valid outcome that downstream stages degrade on rather than
    receiving a fabrication.

    Two things invalidate a stored précis and nothing else does (plan §19):
    ``prompt_version`` changing, and ``source_fingerprint`` changing because the
    item's own text changed — most often an abstract backfilled after an empty
    first pass. Time alone never invalidates: a précis from three months ago is
    still a correct reading of the same paper.
    """

    content = models.OneToOneField(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="comprehension",
    )
    problem = models.TextField(blank=True, default="")
    method = models.TextField(blank=True, default="")
    setting = models.TextField(
        blank=True,
        default="",
        help_text="The data, cohort, or setting the work was carried out in.",
    )
    claim = models.TextField(blank=True, default="")
    limitations = models.TextField(
        blank=True,
        default="",
        help_text="Limitations the authors themselves state — never inferred.",
    )
    reusable = models.TextField(
        blank=True,
        default="",
        help_text=(
            "What an outside researcher could concretely take: a method, a "
            "dataset, a baseline, a negative result, an evaluation protocol."
        ),
    )
    thin = models.BooleanField(
        default=False,
        help_text="The source text was too sparse to support a précis.",
    )
    prompt_version = models.CharField(max_length=32, default="", blank=True)
    source_fingerprint = models.CharField(max_length=64, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["prompt_version"])]

    def __str__(self) -> str:
        return f"comprehension<{self.content_id}>"

    @property
    def is_empty(self) -> bool:
        """True when nothing usable was extracted (a thin or failed pass)."""
        return self.thin or not any(
            (self.problem, self.method, self.claim, self.reusable)
        )

    def as_prompt_block(self) -> str:
        """The précis as the fit prompt reads it — labelled lines, empties dropped."""
        rows = (
            ("Problem", self.problem),
            ("Method", self.method),
            ("Data / setting", self.setting),
            ("Headline claim", self.claim),
            ("Stated limitations", self.limitations),
            ("Reusable", self.reusable),
        )
        return "\n".join(f"    {label}: {value}" for label, value in rows if value)


# --------------------------------------------------------------------------- #
# Project alerts and reflection proposals (plan M7 / M8)
# --------------------------------------------------------------------------- #
class ProjectAlert(models.Model):
    """One thing found today that changes what a project should do.

    The distinction this table exists to hold is between *relevant* and
    *actionable*. A feed is full of relevant papers; an alert says a specific
    thing happened to a specific project and names what to do about it. That is a
    far stronger claim, so it fires far more rarely and is held to a far stricter
    rule: **once per (target, project, item, trigger)**, forever, enforced as a
    database constraint rather than a query.

    Once, not once a day. A paper that overlaps a project's contribution is news
    the morning it is found and noise every morning after; the weekly reports what
    *happened* to an already-alerted item (saved, opened, revised) instead of
    raising it again (plan 6.6).

    The target is a person or a lab, never both — the same exactly-one shape every
    other targeted row in this module uses.
    """

    class Trigger(models.TextChoices):
        #: Someone published something close to what this project claims is new.
        OVERLAP_RISK = "overlap_risk", "Overlap risk"
        #: Something on offer closes a blocker the project stated.
        UNBLOCKS = "unblocks", "Unblocks"
        #: A venue just became reachable from the project's next milestone.
        TIMELINE = "timeline", "Fits your timeline"
        #: A deadline moved on something the reader saved. The only trigger that
        #: can reach a weekly-cadence reader between Mondays (open decision OD2).
        DEADLINE_MOVED = "deadline_moved", "Deadline moved"
        #: A call requires expertise nobody on the team states.
        TEAM_GAP = "team_gap", "Team gap"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        #: Held back by the daily cap; carried into the Monday weekly.
        HELD = "held", "Held for the weekly"
        ACTED = "acted", "Acted on"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="project_alerts",
    )
    target_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="project_alerts",
    )
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="project_alerts",
    )
    trigger = models.CharField(max_length=20, choices=Trigger.choices, db_index=True)
    fired_on = models.DateField(default=timezone.localdate, db_index=True)
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "What the matcher computed — similarities, the blocker it matched, "
            "the timeline row, the requirement nobody covers. The model writes "
            "prose *from* this and may not add a number to it."
        ),
    )
    delivered_in = models.JSONField(
        default=list,
        blank=True,
        help_text="Surfaces this alert has already reached, e.g. ['web:2026-09-16'].",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fired_on", "-created_at"]
        constraints = [
            models.CheckConstraint(
                name="content_projectalert_exactly_one_target",
                condition=exactly_one("target_user", "target_lab"),
            ),
            # The whole idempotency guarantee, as a constraint rather than a
            # query: two split on the populated side, because Postgres treats
            # every NULL as distinct and a plain unique_together over a nullable
            # column would constrain neither half.
            models.UniqueConstraint(
                fields=["target_user", "project", "content", "trigger"],
                condition=Q(target_user__isnull=False),
                name="content_projectalert_user_unique",
            ),
            models.UniqueConstraint(
                fields=["target_lab", "project", "content", "trigger"],
                condition=Q(target_lab__isnull=False),
                name="content_projectalert_lab_unique",
            ),
        ]
        indexes = [models.Index(fields=["fired_on", "status"])]

    def clean(self) -> None:
        validate_exactly_one(self, "target_user", "target_lab")

    @property
    def target(self):
        return self.target_user or self.target_lab

    def __str__(self) -> str:
        return f"alert[{self.trigger}] {self.project} {self.fired_on}"


class ReflectionProposal(models.Model):
    """A change Mylo thinks a project's state should make, for a person to decide.

    Proposed from what the reader actually did — four saves on one topic, six
    dismissals sharing a word, a timeline Mylo could not judge because no
    milestone is dated, state nobody has confirmed in a month. The **rules are
    deterministic** (plan 7.2); the model only phrases them. A model deciding on
    its own that a project's method has changed, and writing that into the state,
    is exactly the failure invariant 9 exists to prevent.

    Every proposal expires (14 days) and is not re-proposed for a further 28, so
    declining one is a decision the system respects rather than a question it asks
    again next Monday.
    """

    class Kind(models.TextChoices):
        ADD_METHOD = "add_method", "Add a method"
        ADD_EXCLUSION = "add_exclusion", "Add an exclusion"
        SET_MILESTONE = "set_milestone", "Set a milestone"
        REVIEW_STATE = "review_state", "Review the state"
        # Ambient Plan 08: from a project development someone confirmed or told
        # Mylo — never applied until an editor accepts.
        CLOSE_BLOCKER = "close_blocker", "Close a blocker"
        DROP_METHOD = "drop_method", "Drop a method"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reflection_proposals",
    )
    target_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reflection_proposals",
    )
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="reflection_proposals",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    proposal = models.JSONField(
        default=dict,
        blank=True,
        help_text="The change itself, in the shape a state PATCH would take.",
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="What the reader did that produced it — counts, the shared term.",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    expires_on = models.DateField(db_index=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="content_reflectionproposal_exactly_one_target",
                condition=exactly_one("target_user", "target_lab"),
            ),
        ]
        indexes = [models.Index(fields=["status", "expires_on"])]

    def clean(self) -> None:
        validate_exactly_one(self, "target_user", "target_lab")

    def __str__(self) -> str:
        return f"proposal[{self.kind}] {self.project} ({self.status})"


# --------------------------------------------------------------------------- #
# Opportunity announcements (plan 20261105-mylo-opportunity-announcements)
# --------------------------------------------------------------------------- #
class AnnouncementSettings(models.Model):
    """How one lab or department wants its opportunities announced.

    One row per target. ``daily_cap = -1`` means no limit. ``activated_at`` is set
    when announcements are first switched on; ``seeded_at`` once the activation
    seed (the ``activation_seed`` best open items) has been chosen, after which
    only new slate entrants are announced.
    """

    class Nudge(models.TextChoices):
        NONE = "none", "No reminder"
        TWO_DAYS = "2d", "2 days before"
        ONE_WEEK = "1w", "1 week before"
        TWO_WEEKS = "2w", "2 weeks before"
        THREE_WEEKS = "3w", "3 weeks before"
        ONE_MONTH = "1m", "1 month before"
        TWO_MONTHS = "2m", "2 months before"

    target_lab = models.OneToOneField(
        "accounts.Lab",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcement_settings",
    )
    target_department = models.OneToOneField(
        "accounts.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcement_settings",
    )
    enabled = models.BooleanField(default=False)
    grants = models.BooleanField(default=True)
    fellowships = models.BooleanField(default=True)
    conferences = models.BooleanField(default=True)
    daily_cap = models.IntegerField(default=-1, help_text="-1 means no limit.")
    default_nudge = models.CharField(
        max_length=4, choices=Nudge.choices, default=Nudge.TWO_WEEKS
    )
    closing_soon_list = models.BooleanField(default=True)
    strong_match_tagging = models.BooleanField(default=False)
    save_on_interest = models.BooleanField(default=True)
    activation_seed = models.PositiveSmallIntegerField(default=6)
    min_award = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    seeded_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=exactly_one("target_lab", "target_department"),
                name="announcement_settings_one_target",
            )
        ]

    def __str__(self) -> str:
        target = self.target_lab_id or self.target_department_id
        return f"AnnouncementSettings({target})"


class Announcement(models.Model):
    """One decision about one opportunity for one lab or department.

    Unique per (target, item): an item is announced to a target at most once, and
    everything that follows — the thread in each server, updates, reactions —
    hangs off this row. ``content`` is SET_NULL with a snapshot, so a pruned item
    keeps a readable history.
    """

    class State(models.TextChoices):
        POSTED = "posted", "Posted"
        SKIPPED = "skipped", "Held back"
        SEEDED_SEEN = "seeded_seen", "Passed over at activation"
        CLOSED = "closed", "Closed"

    class Label(models.TextChoices):
        NEW_CALL = "new_call", "New call"
        NEWLY_RELEVANT = "newly_relevant", "Newly relevant"
        ALREADY_OPEN = "already_open", "Already open"

    class Origin(models.TextChoices):
        NIGHTLY = "nightly", "Nightly"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    target_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
    )
    snapshot = models.JSONField(default=dict, blank=True)  # title, url, funder
    category = models.CharField(max_length=20)  # ContentItem.Type
    origin = models.CharField(
        max_length=16, choices=Origin.choices, default=Origin.NIGHTLY
    )
    state = models.CharField(max_length=16, choices=State.choices)
    label = models.CharField(max_length=16, choices=Label.choices, blank=True)
    skip_reason = models.CharField(max_length=300, blank=True, default="")
    dept_reasons = models.JSONField(default=list, blank=True)
    checks = models.JSONField(default=list, blank=True)
    alignment = models.JSONField(default=dict, blank=True)
    write_up = models.JSONField(default=dict, blank=True)
    write_up_key = models.CharField(max_length=64, blank=True, default="")
    facts = models.JSONField(default=dict, blank=True)
    facts_fingerprint = models.CharField(max_length=64, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one("target_lab", "target_department"),
                name="announcement_one_target",
            ),
            models.UniqueConstraint(
                fields=["target_lab", "content"],
                condition=Q(target_lab__isnull=False, content__isnull=False),
                name="announcement_unique_lab_item",
            ),
            models.UniqueConstraint(
                fields=["target_department", "content"],
                condition=Q(target_department__isnull=False, content__isnull=False),
                name="announcement_unique_department_item",
            ),
        ]
        indexes = [models.Index(fields=["state", "category"])]

    def __str__(self) -> str:
        title = (self.snapshot or {}).get("title", "")[:40]
        return f"Announcement({self.category}, {self.state}, {title})"


class AnnouncementPost(models.Model):
    """Where one announcement was posted: one thread in one server binding."""

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="posts"
    )
    binding = models.ForeignKey(
        "integrations.DiscordTargetBinding",
        on_delete=models.CASCADE,
        related_name="announcement_posts",
    )
    channel_id = models.CharField(max_length=32)  # the forum
    thread_id = models.CharField(max_length=32, blank=True, default="")
    thread_name = models.CharField(max_length=100, blank=True, default="")
    outbox_key = models.CharField(max_length=200, blank=True, default="")
    # [{"on": "2026-11-05", "changes": [...], "reply_id": "..."}] — one per update.
    update_log = models.JSONField(default=list, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Someone deleted the thread by hand (gateway event, or a send found it gone).
    # Never linked again and never updated; the decision itself stands.
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "binding"], name="announcement_post_unique"
            )
        ]

    def __str__(self) -> str:
        where = self.thread_id or "queued"
        return f"AnnouncementPost({self.announcement_id} → {where})"


class AnnouncementReaction(models.Model):
    """One person's reaction to one announcement. Append-only: the latest row of
    ``interested`` / ``unfollow`` per person decides whether they follow it.
    ``remind`` (a Remind me choice) and ``link_click`` (a web link into the thread;
    ``reason`` holds the surface) are measurement only (plan Phase 8)."""

    class Kind(models.TextChoices):
        INTERESTED = "interested", "Interested"
        UNFOLLOW = "unfollow", "Stopped following"
        NOT_FOR_US = "not_for_us", "Not for us"
        REMIND = "remind", "Remind me"
        LINK_CLICK = "link_click", "Opened the thread from the web"

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_reactions",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["announcement", "user", "created_at"])]

    def __str__(self) -> str:
        return f"AnnouncementReaction({self.kind}, user={self.user_id})"


class ClosingSoonPost(models.Model):
    """One day's closing-soon thread in one binding's forum (plan D11). The next
    morning's thread replaces it, and this row is how yesterday's is found."""

    binding = models.ForeignKey(
        "integrations.DiscordTargetBinding",
        on_delete=models.CASCADE,
        related_name="closing_soon_posts",
    )
    category = models.CharField(max_length=20)  # grant | fellowship
    on_date = models.DateField()
    outbox_key = models.CharField(max_length=200)
    thread_id = models.CharField(max_length=32, blank=True, default="")
    replaced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-on_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["binding", "category", "on_date"],
                name="closing_soon_post_unique_day",
            )
        ]

    def __str__(self) -> str:
        return f"ClosingSoonPost({self.binding_id}, {self.category}, {self.on_date})"


class AnnouncementNudge(models.Model):
    """A reminder about one announcement for one person: the default nudge
    *Interested* sets, or a *Remind me* choice. A member's *Remind me* by DM is an
    ordinary ``ReminderSubscription`` instead; a **guest** (anyone in the server
    with no Mycelium account) has only nudges, keyed on ``discord_user_id`` with
    ``user`` empty, delivered as a thread tag or a DM (``delivery``).

    The fire date is computed each night from the call's *current* deadline, so a
    nudge follows a moved date; ``fired_for`` records which deadline it already
    fired for, so it never fires twice for the same one.
    """

    class Source(models.TextChoices):
        INTERESTED = "interested", "Interested (default nudge)"
        REMIND = "remind", "Remind me"

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="nudges"
    )
    class Delivery(models.TextChoices):
        THREAD = "thread", "Tag in the thread"
        DM = "dm", "Direct message"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcement_nudges",
    )
    discord_user_id = models.CharField(max_length=32, blank=True, default="")
    offset = models.CharField(max_length=4, choices=AnnouncementSettings.Nudge.choices)
    source = models.CharField(max_length=16, choices=Source.choices)
    delivery = models.CharField(
        max_length=8, choices=Delivery.choices, default=Delivery.THREAD
    )
    active = models.BooleanField(default=True)
    fired_for = models.JSONField(default=list, blank=True)  # ["2027-01-14", ...]
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user", "offset"],
                condition=Q(user__isnull=False),
                name="announcement_nudge_unique",
            ),
            models.UniqueConstraint(
                fields=["announcement", "discord_user_id", "offset"],
                condition=Q(user__isnull=True),
                name="announcement_nudge_guest_unique",
            ),
            models.CheckConstraint(
                condition=Q(user__isnull=False) | ~Q(discord_user_id=""),
                name="announcement_nudge_has_someone",
            ),
        ]

    def __str__(self) -> str:
        who = f"{self.announcement_id}, {self.user_id or self.discord_user_id}"
        return f"AnnouncementNudge({who}, {self.offset})"
