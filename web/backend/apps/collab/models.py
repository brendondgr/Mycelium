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


class Audience(models.TextChoices):
    """Who may find a person (design §7). Narrowest first."""

    INSTITUTION = "institution", "My institution"
    COUNTRY = "country", "My country"
    ANYWHERE = "anywhere", "Anywhere"


class OpenTo(models.TextChoices):
    CO_AUTHORING = "co_authoring", "Co-authoring"
    GRANT_PARTNER = "grant_partner", "Grant partner"
    DATA_SHARING = "data_sharing", "Sharing data"
    MENTORING = "mentoring", "Mentoring"


class CollaborationSetting(models.Model):
    """Whether a person can be found by collaboration search, by whom, until when.

    No row means off: nobody is findable without choosing to be (plan CN-04).
    ``is_open`` reads the expiry at query time, so a setting that lapsed is off
    whether or not any job has run since.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="collaboration_setting",
    )
    open = models.BooleanField(default=False)
    audience = models.CharField(
        max_length=16, choices=Audience.choices, default=Audience.INSTITUTION
    )
    open_to = models.JSONField(
        default=list, blank=True, help_text="Any of OpenTo; a filter and a label."
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    renewal_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"CollaborationSetting({self.user_id}, open={self.open})"

    def is_open(self, now=None) -> bool:
        from django.utils import timezone

        now = now or timezone.now()
        return bool(self.open and self.expires_at and self.expires_at > now)


class VerifiedAffiliation(models.Model):
    """The institution and country a person's **verified** email places them at.

    Derived from the email's domain against the affiliation directory, never
    from the free-text ``Profile.institution``: a scope a person can type is a
    scope anyone can claim. Empty ``domain`` means the address matched no
    institution (a personal address) — such a person has no institution scope.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verified_affiliation",
    )
    email = models.CharField(max_length=254)
    domain = models.CharField(max_length=253, blank=True, default="", db_index=True)
    institution = models.CharField(max_length=255, blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="", db_index=True)
    derived_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"VerifiedAffiliation({self.user_id}, {self.domain or 'none'})"


class Appearance(models.Model):
    """That a person was shown to a seeker in a given ISO week (design §7).

    The appearance cap reads this. It is never shown to the candidate — people
    are never told someone searched for them (design §9.3) — nor to the seeker.
    Rows older than eight weeks are deleted.
    """

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    seeker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    week = models.CharField(max_length=8, help_text='ISO week, e.g. "2026-W38".')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "seeker", "week"], name="collab_one_appearance"
            )
        ]
        indexes = [models.Index(fields=["candidate", "week"])]
