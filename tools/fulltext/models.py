"""What the full-text tool keeps: retrieved papers, requests, and remembered answers.

Files live on disk under ``data/fulltext/files/`` (see :mod:`.store`); a
document row records where, what the paper is, and where it came from. One
instance shares one store: everything fetched, open or licensed through the
instance's keys, is readable by every signed-in user of the instance.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class FulltextDocument(models.Model):
    """One retrieved paper: its original file and its markdown rendering."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_item = models.ForeignKey(
        "content.ContentItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fulltext_documents",
        help_text="The corpus paper this is the full text of, if the corpus has it.",
    )
    doi = models.CharField(max_length=255, blank=True, default="", db_index=True)
    pmid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    pmcid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    arxiv_id = models.CharField(max_length=64, blank=True, default="")
    title = models.TextField(blank=True, default="")
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Journal, year, authors, abstract."
    )
    source = models.CharField(
        max_length=32, help_text="The engine source that served it."
    )
    source_url = models.URLField(max_length=1000, blank=True, default="")
    licensed = models.BooleanField(
        default=False,
        help_text="Subscription content served through the instance's keys, as "
        "opposed to an open copy.",
    )
    original_path = models.CharField(
        max_length=255, blank=True, default="", help_text="Relative to data/fulltext/."
    )
    original_kind = models.CharField(max_length=10, blank=True, default="")
    markdown_path = models.CharField(
        max_length=255, help_text="Relative to data/fulltext/."
    )
    chars = models.PositiveIntegerField(
        default=0, help_text="Length of the full-text body."
    )
    sha256 = models.CharField(
        max_length=64, help_text="Of the original (else the markdown)."
    )
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fetched_at"]
        constraints = [
            # One document per DOI: a second request for the same paper reuses it.
            models.UniqueConstraint(
                fields=["doi"],
                condition=~Q(doi=""),
                name="fulltext_document_unique_doi",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.doi or self.pmid or self.pmcid} ({self.source})"


class FulltextRequest(models.Model):
    """One identifier someone asked for, and what came of it."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        FULL_TEXT = "full_text", "Full text retrieved"
        ABSTRACT_ONLY = "abstract_only", "No full text available"
        INVALID = "invalid_identifier", "Not an identifier"
        NOT_FOUND = "not_found", "Does not exist"
        MISMATCH = "identifier_mismatch", "Identifiers disagree"
        NEEDS_IDENTIFIER = "needs_identifier", "Title matched zero or several papers"
        ERROR = "error", "Failed"

    #: Statuses after which nothing more will happen without a retry.
    FINISHED = frozenset(
        {
            Status.FULL_TEXT,
            Status.ABSTRACT_ONLY,
            Status.INVALID,
            Status.NOT_FOUND,
            Status.MISMATCH,
            Status.NEEDS_IDENTIFIER,
            Status.ERROR,
        }
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.UUIDField(
        default=uuid.uuid4, db_index=True, help_text="Requests made together share one."
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fulltext_requests",
        help_text="Empty for a system job.",
    )
    identifier = models.JSONField(
        help_text="What was asked for: a string, or an object with pmid/doi/title/…"
    )
    content_item = models.ForeignKey(
        "content.ContentItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fulltext_requests",
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.QUEUED
    )
    document = models.ForeignKey(
        FulltextDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requests",
    )
    ids = models.JSONField(
        default=dict, blank=True, help_text="Resolved pmid/pmcid/doi/arxiv."
    )
    explanation = models.TextField(blank=True, default="")
    retryable = models.BooleanField(default=False)
    next_steps = models.JSONField(default=list, blank=True)
    route = models.JSONField(
        default=list, blank=True, help_text="Every source, tried or skipped."
    )
    attempts = models.JSONField(
        default=dict, blank=True, help_text="Each source's answer."
    )
    notes = models.JSONField(default=list, blank=True)
    candidates = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["requester", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.identifier} -> {self.status}"

    @property
    def finished(self) -> bool:
        return self.status in self.FINISHED


class SourceVerdict(models.Model):
    """A definitive "no" from one source for one article, never asked again.

    The engine's negative-answer memory (PubMedExtraction's attempts.json),
    shared by every worker. Transient answers (errors, quota) are never stored.
    """

    key = models.CharField(
        max_length=300, help_text="The DOI, or pmid:<PMID>, or url:<sha1>."
    )
    source = models.CharField(max_length=32)
    outcome = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "source"], name="fulltext_verdict_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.source} {self.key}: {self.outcome}"
