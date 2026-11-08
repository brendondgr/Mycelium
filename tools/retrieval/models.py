import uuid

from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField


class DeadlineKind(models.TextChoices):
    """What a deadline is for: one vocabulary for the corpus's deadline rows,
    saves and reminders."""

    APPLICATION = "application", "Application"
    ABSTRACT = "abstract", "Abstract"
    MANUSCRIPT = "manuscript", "Manuscript"
    EVENT = "event", "Event"
    OTHER = "other", "Other"


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
    # Weighted full-text index for query-first search (tools.retrieval.search),
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


class ContentDeadline(models.Model):
    """One addressable deadline on a :class:`ContentItem` (Discord reminders R0).

    A **projection**, not a new source of truth: rebuilt on every opportunity
    upsert from the same status functions the feed already uses
    (:mod:`tools.retrieval.deadlines_projection`). A conference yields **one row per
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
    ``tools.retrieval.collect.conferences.record.Deadline.identity``, which is
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
        choices=DeadlineKind.choices,
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
