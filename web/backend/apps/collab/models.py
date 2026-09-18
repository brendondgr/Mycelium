"""Collaboration matching (the collaboration-network plan series).

This app sits on the knowledge core and reads it only through
:mod:`apps.knowledge.read` — and only the functions that cannot return what
conversation taught the graph about anyone (``apps/knowledge/tests/
test_import_boundary.py`` enforces the list). Plan CN-03 adds what a call
*needs*: its requirement slots, and the feedback people give on them.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class SlotFacet(models.TextChoices):
    """What a slot asks for. ``role`` is a requirement that is not expertise —
    "a co-investigator at a minority-serving institution", "a border authority
    as a partner" — shown to the reader and never matched against anyone."""

    PROBLEM = "problem", "Problem"
    METHOD = "method", "Method"
    DATA = "data", "Data or setting"
    ROLE = "role", "Role"


class RequirementSlots(models.Model):
    """What one funding call needs, as structured slots, read once per text.

    ``slots`` is a list of ``{"facet", "text", "required", "vector"}``:
    ``required`` marks what the call says a team must include, as opposed to
    what it is about. Kept apart from the call's verified extraction
    (``metadata["ai_fields"]``) so that reading slots never rewrites the
    summaries or the text that is embedded for search.
    """

    class Status(models.TextChoices):
        OK = "ok", "Read"
        NONE = "none", "Read; the call states nothing to match"
        THIN = "thin", "Too little text to read"

    content = models.OneToOneField(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="requirement_slots",
    )
    slots = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices)
    refused = models.JSONField(default=list, blank=True)
    prompt_version = models.CharField(max_length=32)
    source_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "requirement slots"

    def __str__(self) -> str:
        return f"RequirementSlots({self.content_id}, {len(self.slots)} slots)"

    @property
    def required(self) -> list[dict]:
        return [slot for slot in self.slots if slot.get("required")]


class SlotFeedback(models.Model):
    """A reader's correction to a call's slots or to its coverage. Append-only.

    The labelled set plan CN-08 measures slot quality with: "this isn't a
    requirement" (precision), "you missed one" (recall), "we do cover this"
    (coverage).
    """

    class Kind(models.TextChoices):
        NOT_A_REQUIREMENT = "not_a_requirement", "This isn't a requirement"
        WE_COVER_THIS = "we_cover_this", "We do cover this"
        MISSED_ONE = "missed_one", "You missed one"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    content = models.ForeignKey(
        "content.ContentItem", on_delete=models.CASCADE, related_name="slot_feedback"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    slot_text = models.CharField(max_length=200, blank=True, default="")
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["content", "kind"])]

    def __str__(self) -> str:
        return f"SlotFeedback({self.kind}, {self.content_id})"
