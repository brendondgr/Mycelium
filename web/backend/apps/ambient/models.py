"""The ambient ledger's tables.

This module holds the durable half of the app. The transient half — the raw
message text itself — is deliberately **not** here: it lives in Redis under a
TTL (:mod:`.buffer`) and never reaches Postgres, a disk, or a backup.

Phase 1 covers the consent surface, which is what decides whether anything is
recorded at all:

* :class:`Source`   — one connected surface (a Discord guild, a Slack
  workspace, a DM, a transcript) and the consent the *server* gave.
* :class:`ListeningConsent` — the consent one *person* gave, per platform,
  default off. Both must say yes; either one saying no ends the matter.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Platform(models.TextChoices):
    """The conversation platforms an adapter can speak for."""

    DISCORD = "discord", "Discord"
    SLACK = "slack", "Slack"
    TEAMS = "teams", "Microsoft Teams"
    TRANSCRIPT = "transcript", "Meeting transcript"


class Source(models.Model):
    """One connected surface, and the consent its owner gave.

    A Discord guild ``Source`` is created from an existing
    :class:`~apps.integrations.models.DiscordGuildLink` when a lab manager turns
    listening on; a DM source is personal and has no lab. Consent here is the
    *server's* half — the person's half is :class:`ListeningConsent`, and
    :mod:`.eligibility` requires both.
    """

    class Kind(models.TextChoices):
        DISCORD_GUILD = "discord_guild", "Discord server"
        DISCORD_DM = "discord_dm", "Discord DM"
        SLACK_WORKSPACE = "slack_workspace", "Slack workspace"
        TEAMS_TEAM = "teams_team", "Microsoft Teams team"
        TRANSCRIPT = "transcript", "Meeting transcript"

    class Consent(models.TextChoices):
        PENDING = "pending", "Pending"  # known, never turned on
        ACTIVE = "active", "Active"  # listening allowed
        PAUSED = "paused", "Paused"  # temporarily off, settings kept
        REVOKED = "revoked", "Revoked"  # turned off for good

    # Which platform each kind belongs to. Kept as a mapping rather than a second
    # column so the two can never disagree.
    PLATFORM_BY_KIND = {
        Kind.DISCORD_GUILD: Platform.DISCORD,
        Kind.DISCORD_DM: Platform.DISCORD,
        Kind.SLACK_WORKSPACE: Platform.SLACK,
        Kind.TEAMS_TEAM: Platform.TEAMS,
        Kind.TRANSCRIPT: Platform.TRANSCRIPT,
    }

    kind = models.CharField(max_length=24, choices=Kind.choices)
    # The platform's own id for the surface (a guild snowflake, a Slack team id).
    external_id = models.CharField(max_length=64, db_index=True)
    # Display only, and cached: names change and are never a key.
    label = models.CharField(max_length=120, blank=True, default="")
    lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_sources",
        help_text="The lab this surface belongs to; null for a personal DM.",
    )
    consent_state = models.CharField(
        max_length=16, choices=Consent.choices, default=Consent.PENDING
    )
    consent_changed_at = models.DateTimeField(null=True, blank=True)
    consent_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_sources_changed",
    )
    # Per-source override of how long raw text may sit in the buffer, in hours.
    # Null means the deployment default (``AMBIENT_RAW_TTL_HOURS``). Either way
    # ``buffer.ttl_seconds`` clamps it to ``AMBIENT_RAW_TTL_HOURS_MAX``, so a
    # source can shorten the window but never lengthen it past the hard ceiling.
    raw_ttl_hours = models.PositiveSmallIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "external_id"], name="ambient_source_unique_external"
            ),
        ]
        indexes = [models.Index(fields=["consent_state"])]

    def __str__(self) -> str:
        return f"Source({self.kind}:{self.external_id}, {self.consent_state})"

    @property
    def platform(self) -> str:
        """The platform this source speaks for, derived from its kind."""
        return Source.PLATFORM_BY_KIND[self.Kind(self.kind)]

    @property
    def listening(self) -> bool:
        """Whether the surface's own consent currently allows listening."""
        return self.consent_state == self.Consent.ACTIVE


class ListeningConsent(models.Model):
    """One person's opt-in, per platform. Default off, revocable at any time.

    There is no row until somebody opts in, and an absent row reads as *off* —
    so the default is off by construction rather than by a flag somebody could
    flip the wrong way. ``enabled`` is the listening switch;
    ``questions_muted`` is the separate "shut off" switch, which silences Mylo's
    questions without discarding what it already understood (Plan 06 reads it).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_consents",
    )
    platform = models.CharField(max_length=16, choices=Platform.choices)
    enabled = models.BooleanField(default=False)
    enabled_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    # "Shut off" — said to Mylo in any conversation or toggled on the web. It
    # stops the questions; it does not stop the person's own explicit statements
    # from being recorded, and it deletes nothing.
    questions_muted = models.BooleanField(default=False)
    questions_muted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "platform"], name="ambient_consent_unique_platform"
            ),
        ]

    def __str__(self) -> str:
        state = "on" if self.enabled else "off"
        return f"ListeningConsent(user={self.user_id}, {self.platform}, {state})"


class PlaceKind(models.TextChoices):
    """The kind of place a message came up in — kept so an explanation can say
    *where* without naming an id a person cannot read."""

    DM = "dm", "Direct message"
    CHANNEL = "channel", "Channel"
    THREAD = "thread", "Thread"
    FORUM = "forum", "Forum post"
    TRANSCRIPT = "transcript", "Meeting transcript"


class SpeakerKind(models.TextChoices):
    """Who sent a buffered message.

    ``MYLO`` exists because a window has to read coherently — a question Mylo
    asked is what makes the next line an answer. Mylo's own messages are never
    evidence; Plan 04 excludes them at extraction, and they never become an
    :class:`Observation`, which always has a human speaker.
    """

    LINKED = "linked", "A linked Mycelium user"
    MYLO = "mylo", "Mylo itself"


class RawMessageRef(models.Model):
    """A pointer to one message. **No body, ever.**

    The body lives in Redis under a TTL (:mod:`.buffer`) and is gone within
    hours. What Postgres keeps is the id, the timestamp, the place, the speaker,
    and a content hash — enough to assemble a window, to tell a repeat from a
    new thought, and to reconcile a platform edit or deletion against whatever
    was derived from it. It is not enough to reconstruct what anybody said.

    A row only exists for a message that passed :mod:`.eligibility`, so there is
    no reference here to a person without a linked, paid, opted-in account.
    """

    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="raw_refs"
    )
    # The platform's own message id.
    external_id = models.CharField(max_length=64)

    place_kind = models.CharField(max_length=16, choices=PlaceKind.choices)
    place_id = models.CharField(max_length=64, blank=True, default="")
    # A channel name rather than a snowflake: an explanation has to be readable.
    place_label = models.CharField(max_length=120, blank=True, default="")

    speaker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_raw_refs",
        help_text="Null only for Mylo's own messages.",
    )
    speaker_kind = models.CharField(
        max_length=16, choices=SpeakerKind.choices, default=SpeakerKind.LINKED
    )
    speaker_external_id = models.CharField(max_length=64, blank=True, default="")

    sent_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    # When the body in the buffer expires. Null means it was never held (a Redis
    # outage) or has already been dropped after a window was read.
    buffered_until = models.DateTimeField(null=True, blank=True)

    # sha256 of the normalised text (:mod:`.text`). Blank for a message with no
    # comparable text of its own, such as an attachment-only post.
    content_hash = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    repeat_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="repeats",
        help_text="The earlier message this repeats; it counts as one piece of "
        "evidence, not two.",
    )

    # OD-01a: a pasted PDF contributes its URL, never its content. Extraction
    # from attachments is a later plan.
    attachment_urls = models.JSONField(default=list, blank=True)

    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="ambient_raw_unique_external"
            ),
            models.CheckConstraint(
                name="ambient_raw_speaker_required",
                condition=(
                    models.Q(speaker__isnull=False, speaker_kind="linked")
                    | models.Q(speaker__isnull=True, speaker_kind="mylo")
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["source", "sent_at"]),
            models.Index(fields=["speaker", "sent_at"]),
        ]

    def __str__(self) -> str:
        return f"RawMessageRef({self.source_id}:{self.external_id})"

    @property
    def is_repeat(self) -> bool:
        return self.repeat_of_id is not None
