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


class UnderstandingKind(models.TextChoices):
    """The six kinds of understanding in the plan series' opening table.

    Two distinctions the table is there to force. A week spent discussing a
    method the researcher dislikes because the project needs it is a project
    development, not an interest change. "I want to learn causal inference" is
    a learning goal, not a claim of expertise.
    """

    ENDURING_INTEREST = "enduring_interest", "Enduring interest"
    CURRENT_CURIOSITY = "current_curiosity", "Current curiosity"
    WORK_PREFERENCE = "work_preference", "Work preference"
    CAREER_DIRECTION = "career_direction", "Career direction"
    PROJECT_INTENT = "project_intent", "Project intent"
    PROJECT_DEVELOPMENT = "project_development", "Project development"


class Force(models.TextChoices):
    """How firmly a thing was said. "The experiment finished" and "we should
    finish the experiment" are different rows, not the same row twice."""

    FACT = "fact", "A statement of fact"
    QUESTION = "question", "A question"
    PREFERENCE = "preference", "A preference"
    POSSIBILITY = "possibility", "A possibility"
    DECISION = "decision", "A decision"
    REJECTION = "rejection", "A rejection"


class Subject(models.TextChoices):
    """Who or what the statement was about.

    Load-bearing: a person discussing a colleague's idea is not stating their
    own interest, and reading it as one is the most obvious way this feature
    could quietly corrupt a profile.
    """

    SELF = "self", "The speaker"
    COLLEAGUE = "colleague", "A colleague"
    PROJECT = "project", "A project"
    LAB = "lab", "The lab"
    UNKNOWN = "unknown", "Unknown"


class Visibility(models.TextChoices):
    """Visibility travels with the memory. A private career aspiration informs a
    personal report and never a lab one."""

    PERSONAL = "personal", "Personal"
    LAB = "lab", "Lab"


class Origin(models.TextChoices):
    """Whether a model or a rule produced this row.

    Extraction and explanation in this feature are model-written with **no**
    rule-based fallback (README principle 18): when the model is unavailable the
    stage does not run that night and is retried the next. ``RULE`` therefore
    exists so Plan 10's harm check — zero rows with ``origin = rule`` — is a
    query rather than an assumption.
    """

    MODEL = "model", "Written by a model"
    RULE = "rule", "Produced by a rule"


class Observation(models.Model):
    """The durable record: what Mylo understood, in Mylo's own words.

    ``text`` is Mylo's account of what was said and when — "on 12 Sep in
    #methods they said they wanted to try conformal prediction on the imaging
    data". It is **not** the person's words. There is no quote column on this
    model and there is not meant to be one: the evidence a person is ever shown
    is the explanation Mylo wrote, which is what OD-A6 settled.

    An observation is evidence, never a conclusion. It changes nothing on its
    own — Plan 04 decides what it means, Plan 06 asks, and only a confirmed
    answer reaches a recommendation.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        # The message it rests on was edited; it must be re-extracted before it
        # is read again (see :mod:`.reconcile`).
        STALE = "stale", "Stale — awaiting re-extraction"
        SUPERSEDED = "superseded", "Superseded by a later observation"

    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="observations"
    )
    # The messages this rests on: a window may yield one observation from three
    # of them. Ids only — the bodies are long gone.
    external_message_ids = models.JSONField(default=list, blank=True)
    observed_at = models.DateTimeField(
        help_text="When the conversation this rests on happened."
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    # Required. There is no such thing as an anonymous observation here: a
    # person without a linked, paid, opted-in account never reaches this table.
    speaker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_observations",
    )
    speaker_external_id = models.CharField(max_length=64, blank=True, default="")

    text = models.TextField(
        help_text="Mylo's own account of what was said, one or two sentences. "
        "Never the person's words."
    )
    subject = models.CharField(
        max_length=16, choices=Subject.choices, default=Subject.UNKNOWN
    )
    understanding_kind = models.CharField(
        max_length=24, choices=UnderstandingKind.choices
    )
    force = models.CharField(max_length=16, choices=Force.choices)

    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_observations",
        help_text="Set by Plan 03; null means attribution was honest about "
        "being unresolved.",
    )
    project_confidence = models.FloatField(null=True, blank=True)

    # True records that the extractor's grounding check passed against the
    # transient window before it was discarded. A row that failed it is not
    # written at all, which the check constraint below makes structural.
    grounded = models.BooleanField(default=True)
    place_kind = models.CharField(max_length=16, choices=PlaceKind.choices)
    place_label = models.CharField(max_length=120, blank=True, default="")

    explanation = models.TextField(
        blank=True,
        default="",
        help_text="Written at deliberation (Plan 04) for findings that reach a "
        "suggestion: what, on which dates, where, how often, and why Mylo read "
        "it that way. The only evidence a person is ever shown.",
    )

    # How sure the extractor is that it read the message correctly. Kept apart
    # from `influence`, which is how much this should be allowed to move
    # anything — Plan 04 sets it, Plan 05 reads it. Conflating the two is how a
    # confidently-read throwaway remark ends up reshaping a profile.
    extraction_confidence = models.FloatField(null=True, blank=True)
    influence = models.FloatField(null=True, blank=True)

    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_by",
    )
    superseded_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )

    visibility = models.CharField(max_length=16, choices=Visibility.choices)
    origin = models.CharField(
        max_length=16, choices=Origin.choices, default=Origin.MODEL
    )
    # Filled by Plan 05 so an old report stays interpretable: the version of the
    # understanding that was in force when this was written.
    context_version = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-observed_at", "-pk"]
        constraints = [
            # The acceptance criteria of Plan 01, as database constraints rather
            # than as intentions.
            models.CheckConstraint(
                name="ambient_observation_grounded",
                condition=models.Q(grounded=True),
            ),
            models.CheckConstraint(
                name="ambient_observation_has_visibility",
                condition=~models.Q(visibility=""),
            ),
            models.CheckConstraint(
                name="ambient_observation_has_text",
                condition=~models.Q(text=""),
            ),
            models.CheckConstraint(
                name="ambient_observation_confidence_range",
                condition=models.Q(project_confidence__isnull=True)
                | models.Q(project_confidence__gte=0, project_confidence__lte=1),
            ),
        ]
        indexes = [
            models.Index(fields=["speaker", "understanding_kind", "observed_at"]),
            models.Index(fields=["project", "observed_at"]),
            models.Index(fields=["source", "observed_at"]),
        ]

    def __str__(self) -> str:
        return f"Observation({self.understanding_kind}, speaker={self.speaker_id})"

    @property
    def is_lab_visible(self) -> bool:
        return self.visibility == Visibility.LAB


class ObservationFeedback(models.Model):
    """The person's own verdict on an observation. Append-only.

    This is the record that answers the question the whole feature rests on:
    is Mylo making correct changes, or is this an exercise in futility? Plan 06
    writes a row for every answer; Plan 10 reads them as labels. Nothing here is
    ever edited, because a label that can be rewritten is not a label.
    """

    class Verdict(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        CORRECTED = "corrected", "Corrected"
        IGNORED = "ignored", "Ignored"

    class Channel(models.TextChoices):
        DM_DIALOGUE = "dm_dialogue", "A conversation with Mylo"
        WEB_REVIEW = "web_review", "The web review page"
        UNDO = "undo", "An undo"

    observation = models.ForeignKey(
        Observation, on_delete=models.CASCADE, related_name="feedback"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_feedback",
    )
    verdict = models.CharField(max_length=16, choices=Verdict.choices)
    corrected_text = models.TextField(blank=True, default="")
    channel = models.CharField(max_length=16, choices=Channel.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["observation", "created_at"])]

    def __str__(self) -> str:
        return f"ObservationFeedback({self.verdict}, obs={self.observation_id})"

    def save(self, *args, **kwargs):
        """Append-only: a saved verdict is never rewritten.

        A correction is a new row with ``verdict = corrected``, so the sequence
        of what somebody said and then said differently stays readable.
        """
        if self.pk is not None:
            raise ValueError(
                "ObservationFeedback is append-only; record a new row instead."
            )
        return super().save(*args, **kwargs)


class Retraction(models.Model):
    """Something was removed, and these things must therefore be recomputed.

    A platform deletion, a person asking for evidence to be removed, an opt-out
    with deletion, a source losing consent: each deletes rows and each leaves a
    retraction behind naming what downstream work is now wrong. Plans 05 and 08
    subscribe to it. The retraction itself holds ids and counts — never any of
    the text it removed, which would defeat the point of removing it.
    """

    class Reason(models.TextChoices):
        PLATFORM_DELETE = "platform_delete", "The message was deleted"
        PERSON_REQUEST = "person_request", "The person asked for it to be removed"
        OPT_OUT = "opt_out", "The person opted out with deletion"
        SOURCE_REVOKED = "source_revoked", "The surface withdrew consent"

    reason = models.CharField(max_length=24, choices=Reason.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_retractions",
    )
    source = models.ForeignKey(
        Source,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retractions",
    )
    # What went. Ids only, so the retraction never becomes a copy of what it
    # retracted.
    observation_ids = models.JSONField(default=list, blank=True)
    project_ids = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    # Stamped by the downstream recompute (Plans 05 and 08). Null means the
    # influence this row removed has not been taken out of anything yet.
    recomputed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["recomputed_at"])]

    def __str__(self) -> str:
        return f"Retraction({self.reason}, {len(self.observation_ids)} observations)"
