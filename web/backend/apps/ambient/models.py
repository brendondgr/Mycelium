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
    #: Conversations with Mylo in the app (the agent tool). The one platform
    #: where listening is on unless the person turned it off (agent plan D-3).
    AGENT_CHAT = "agent_chat", "Mylo chat"


class Source(models.Model):
    """One connected surface, and the consent its owner gave.

    A Discord guild ``Source`` is created from a server's lab binding
    (:class:`~apps.integrations.models.DiscordTargetBinding`) when a lab manager turns
    listening on; a DM source is personal and has no lab. Consent here is the
    *server's* half — the person's half is :class:`ListeningConsent`, and
    :mod:`.eligibility` requires both.
    """

    class Kind(models.TextChoices):
        DISCORD_GUILD = "discord_guild", "Discord server"
        DISCORD_DM = "discord_dm", "Discord DM"
        SLACK_WORKSPACE = "slack_workspace", "Slack workspace"
        # One person's DMs with Mylo in one workspace (Plan 11).
        SLACK_DM = "slack_dm", "Slack DM"
        TEAMS_TEAM = "teams_team", "Microsoft Teams team"
        # One person's personal chat with Mylo in Teams (Plan 11).
        TEAMS_CHAT = "teams_chat", "Teams personal chat"
        TRANSCRIPT = "transcript", "Meeting transcript"
        AGENT_CHAT = "agent_chat", "Mylo chat"

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
        Kind.SLACK_DM: Platform.SLACK,
        Kind.TEAMS_CHAT: Platform.TEAMS,
        Kind.TEAMS_TEAM: Platform.TEAMS,
        Kind.TRANSCRIPT: Platform.TRANSCRIPT,
        Kind.AGENT_CHAT: Platform.AGENT_CHAT,
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

    # Channels a manager said Mylo must never read. Checked at the edge, before
    # anything is forwarded, and again on arrival — an exclusion that only held
    # in the bot process would be one restart away from not holding.
    excluded_place_ids = models.JSONField(default=list, blank=True)
    # Channels a manager marked as social. Not excluded — Mylo may still answer
    # a direct question there — but nothing is drawn from them as evidence.
    social_place_ids = models.JSONField(default=list, blank=True)
    # The pinned "Mylo is listening" post, so it is edited rather than
    # duplicated every time the settings change.
    marker_message_id = models.CharField(max_length=64, blank=True, default="")
    marker_channel_id = models.CharField(max_length=64, blank=True, default="")

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

    def excludes(self, place_id: str) -> bool:
        """Whether a channel is on the never-read list."""
        return str(place_id) in {str(one) for one in (self.excluded_place_ids or [])}

    def is_social(self, place_id: str) -> bool:
        """Whether a channel is marked social — heard, but never evidence."""
        return str(place_id) in {str(one) for one in (self.social_place_ids or [])}


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
    # A quiet period (Plan 06, step 5): no questions until this date. Unlike
    # "shut off" it ends by itself.
    questions_quiet_until = models.DateField(null=True, blank=True)
    # The personal-information opt-out (Q-071). Per person, kept on the
    # Discord row like the questions switch, and read for every platform:
    # facts about the person's life rather than their work (health,
    # immigration, family, money, relationships, plans to leave) are not
    # recorded, and those already recorded are deleted (:mod:`.personal`).
    personal_withheld = models.BooleanField(default=False)
    personal_withheld_at = models.DateTimeField(null=True, blank=True)

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


class RecordingExclusion(models.Model):
    """One person's "don't record me" for one server or one project.

    Finer than :class:`ListeningConsent`, which is per platform: a person who
    listens on Discord can still keep one server, or one project, out of it. A
    row is an exclusion — no row means the platform switch decides alone, so
    adding these never turned anybody *on*.

    The server's own switch (:attr:`Source.consent_state`, the lab or department
    head's) is a different thing and wins: while it is off nobody there is
    recorded, whatever these rows say (settings plan, decision 16).

    A project exclusion stops messages in a channel tied to that project from
    being recorded at all, and takes the project out of the person's
    attribution candidates everywhere else.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recording_exclusions",
    )
    source = models.ForeignKey(
        Source,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="exclusions",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="recording_exclusions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="ambient_exclusion_one_target",
                condition=(
                    models.Q(source__isnull=False, project__isnull=True)
                    | models.Q(source__isnull=True, project__isnull=False)
                ),
            ),
            models.UniqueConstraint(
                fields=["user", "source"],
                condition=models.Q(source__isnull=False),
                name="ambient_exclusion_unique_source",
            ),
            models.UniqueConstraint(
                fields=["user", "project"],
                condition=models.Q(project__isnull=False),
                name="ambient_exclusion_unique_project",
            ),
        ]

    def __str__(self) -> str:
        target = (
            f"source={self.source_id}"
            if self.source_id
            else f"project={self.project_id}"
        )
        return f"RecordingExclusion(user={self.user_id}, {target})"


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

    # True when the person deliberately told Mylo: a DM, an @mention, a note
    # command, the message action, a reaction on Mylo's own post. Ambient talk
    # overheard in a channel is false. Plan 04 weighs the two differently —
    # somebody addressing Mylo meant to be understood.
    explicit = models.BooleanField(default=False)

    # -- attribution (Plan 03) ------------------------------------------------
    # Which project this message is about, decided on arrival from cheap
    # signals and, for what that left unresolved, again at the nightly read
    # with semantic similarity. Null is a real answer — "unresolved" — never a
    # missing one: guessing is the failure mode.
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_refs",
    )
    project_confidence = models.FloatField(null=True, blank=True)
    # {"scores": {project_id: {signal: score}}, "matched": {project_id: [term]},
    #  "decided_by": "...", "corrected": bool}. The matched terms are the
    # *project's* vocabulary — an alias, a dataset name — never the person's
    # words, so this column can outlive the body without becoming a quote.
    attribution = models.JSONField(default=dict, blank=True)
    attributed_at = models.DateTimeField(null=True, blank=True)
    # How many other people the message named. A message that names a
    # colleague is about them as much as by the speaker, which is what lets
    # Plan 04 set subject = colleague. Ids are kept only for mentioned people
    # who have opted in themselves; anybody else is at most a number.
    mentions_count = models.PositiveSmallIntegerField(default=0)
    mentioned_user_ids = models.JSONField(default=list, blank=True)

    # The platform id of the message this one answers, when it answers one.
    # A reply to Mylo is engagement with what Mylo said, never independent
    # evidence of interest (Plan 04, step 5).
    reply_to_external_id = models.CharField(max_length=64, blank=True, default="")
    # When the reasoning agent read the window this message belongs to (Plan
    # 04). Set once, with the body released in the same step; null means the
    # message is still waiting to be read.
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

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
            models.Index(fields=["source", "place_id", "sent_at"]),
            models.Index(fields=["project", "sent_at"]),
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
    # Plan 04: "I ran X again", "I built Y" — a claim of doing, which may become
    # a declared skill and never an area. And "I want to learn Z", which is
    # explicitly not a claim of expertise.
    CAPABILITY = "capability", "Capability"
    LEARNING_GOAL = "learning_goal", "Learning goal"


#: The kinds that describe the speaker rather than a project. Only a ``self``
#: observation of one of these may move anything about a person.
PERSONAL_KINDS = frozenset(
    {
        UnderstandingKind.ENDURING_INTEREST,
        UnderstandingKind.CURRENT_CURIOSITY,
        UnderstandingKind.WORK_PREFERENCE,
        UnderstandingKind.CAREER_DIRECTION,
        UnderstandingKind.CAPABILITY,
        UnderstandingKind.LEARNING_GOAL,
    }
)
PROJECT_KINDS = frozenset(
    {UnderstandingKind.PROJECT_INTENT, UnderstandingKind.PROJECT_DEVELOPMENT}
)


class Change(models.TextChoices):
    """What happened to a project, for a project development (Plan 05).

    Each is a different event downstream: a closed blocker stops the
    ``unblocks`` alert firing for it, a dropped method leaves what
    ``overlap_risk`` compares against, a moved milestone is a date Plan 08 may
    propose.
    """

    DATASET_ARRIVED = "dataset_arrived", "Data arrived"
    EXPERIMENT_FAILED = "experiment_failed", "An experiment failed"
    RESULT_OBTAINED = "result_obtained", "A result came in"
    VENUE_CHANGED = "venue_changed", "The target venue changed"
    MILESTONE_MOVED = "milestone_moved", "A milestone moved"
    BLOCKER_OPENED = "blocker_opened", "A blocker opened"
    BLOCKER_CLOSED = "blocker_closed", "A blocker closed"
    METHOD_ADOPTED = "method_adopted", "A method was adopted"
    METHOD_DROPPED = "method_dropped", "A method was dropped"
    OTHER = "other", "Something else changed"


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
    #: About an ``invite_only`` project, wherever it was said: for the people
    #: who can open that project, never a lab surface (scoping plan, Phase 4).
    PROJECT = "project", "Project"


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

    # -- Plan 04 ---------------------------------------------------------------
    # The side of the work the topic names, and the short topic phrase itself —
    # a term ("conformal prediction"), never a sentence. The phrase is what the
    # knowledge core links to a concept, so one topic said three ways is one
    # topic seen three times.
    facet = models.CharField(max_length=16, blank=True, default="")
    topic = models.CharField(max_length=200, blank=True, default="")
    # The extractor's own answer to "is this about the speaker's personal life
    # rather than their work?" (Q-071), asked in the same call. Null means it
    # was never asked — written before prompt a5, or the model left it out —
    # and :mod:`.personal` asks once if the speaker opts out.
    personal_life = models.BooleanField(null=True, blank=True)
    # For a project development only: what kind of change it was (Plan 05).
    change = models.CharField(
        max_length=24, choices=Change.choices, blank=True, default=""
    )
    concept = models.ForeignKey(
        "knowledge.Concept",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_observations",
        help_text="Null until linked; the embedder being down only delays it.",
    )
    # Copied from the messages it rests on: somebody addressing Mylo meant to be
    # understood, and weighs more than something overheard.
    explicit = models.BooleanField(default=False)
    # Which conversation this came from — the window's key. Repetition is
    # counted across distinct conversations, so one long debugging session is
    # one piece of evidence however many times a topic comes up in it.
    conversation_key = models.CharField(max_length=128, blank=True, default="")
    run = models.ForeignKey(
        "ExtractionRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="observations",
    )

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


class SourceActivity(models.Model):
    """What one surface produced on one day, in counts.

    This is the aggregate a discarded message is allowed to leave behind. It is
    keyed on the source and the reason and **never on a person**: "forty-one
    messages were dropped here yesterday because their senders have not opted
    in" is an operational fact, while "this person's messages were dropped" is
    a record of somebody who asked not to be recorded.

    It exists for two jobs: showing a manager that listening is working, and
    giving Plan 04 real numbers to size its extraction windows from.
    """

    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="activity"
    )
    day = models.DateField()

    # Everything the gateway saw in a consented server.
    heard = models.IntegerField(default=0)
    # Reached the ledger and is waiting to be read.
    stored = models.IntegerField(default=0)
    # Why the rest did not. One counter per refusal, so a quiet day and a
    # misconfigured one look different.
    dropped_not_opted_in = models.IntegerField(default=0)
    dropped_unlinked = models.IntegerField(default=0)
    dropped_free_tier = models.IntegerField(default=0)
    dropped_excluded_channel = models.IntegerField(default=0)
    dropped_too_short = models.IntegerField(default=0)
    dropped_bot = models.IntegerField(default=0)
    # Recorded, then discarded at the nightly read because the speaker was no
    # longer eligible by then — an opt-out, an unlink, a lapsed plan.
    dropped_lapsed = models.IntegerField(default=0)
    dropped_other = models.IntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "source activity"
        ordering = ["-day"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "day"], name="ambient_activity_unique_day"
            ),
        ]

    def __str__(self) -> str:
        return f"SourceActivity({self.source_id}, {self.day}, heard={self.heard})"


class MemberNotice(models.Model):
    """That somebody was told, once, that a server they are in is listening.

    Without this the notice either never arrives or arrives every night. It
    records that a thing was said and when — not what was said, and not a
    reply.
    """

    class Kind(models.TextChoices):
        SERVER_LISTENING = "server_listening", "This server is listening"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_notices",
    )
    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="member_notices"
    )
    kind = models.CharField(
        max_length=24, choices=Kind.choices, default=Kind.SERVER_LISTENING
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    delivered = models.BooleanField(
        default=True,
        help_text="False when the DM could not be delivered — blocked DMs are "
        "common, and a notice nobody received should not read as one that was.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "kind"], name="ambient_notice_once"
            ),
        ]

    def __str__(self) -> str:
        return f"MemberNotice({self.kind}, user={self.user_id})"


class ChannelHint(models.Model):
    """An optional default project for one channel.

    A hint, never a binding. It adds a small score that cannot resolve a
    message on its own; the content still decides, and a channel that carries
    three projects in an afternoon is attributed three ways.
    """

    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="channel_hints"
    )
    place_id = models.CharField(max_length=64)
    place_label = models.CharField(max_length=120, blank=True, default="")
    project = models.ForeignKey(
        "research.Project", on_delete=models.CASCADE, related_name="channel_hints"
    )
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_channel_hints",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "place_id"], name="ambient_hint_one_per_channel"
            ),
        ]

    def __str__(self) -> str:
        return f"ChannelHint({self.place_label or self.place_id} -> {self.project_id})"


class AttributionCorrection(models.Model):
    """A person said "this was about a different project". Append-only.

    Two jobs. It fixes the one attribution — the reference, and any observation
    already resting on it. And it is a labelled example: ``scores`` snapshots
    what every signal said at the time, in numbers and project ids only, so the
    floor and margin can be set from real disagreements rather than by taste
    (OD-03b).
    """

    ref = models.ForeignKey(
        RawMessageRef,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="corrections",
    )
    source = models.ForeignKey(
        Source,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attribution_corrections",
    )
    from_project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    to_project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    from_confidence = models.FloatField(null=True, blank=True)
    scores = models.JSONField(default=dict, blank=True)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="ambient_attribution_corrections",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"AttributionCorrection({self.from_project_id} -> {self.to_project_id})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "AttributionCorrection is append-only; record a new row instead."
            )
        return super().save(*args, **kwargs)


class ProjectAttention(models.Model):
    """Which project a person is actually spending their conversation on.

    The fraction of their *attributed* conversation that went to each project
    over the last 7 and 28 days. Derived, recomputed nightly, never edited by
    hand — it is a measurement, and a measurement somebody can type into is an
    opinion. It feeds Plan 05 (what is useful now) and Plan 09 ("you spent most
    of this week on X"), and it is personal: it is read by the person it
    describes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_attention",
    )
    project = models.ForeignKey(
        "research.Project", on_delete=models.CASCADE, related_name="ambient_attention"
    )
    share_7d = models.FloatField(default=0.0)
    share_28d = models.FloatField(default=0.0)
    messages_7d = models.PositiveIntegerField(default=0)
    messages_28d = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField()

    class Meta:
        ordering = ["-share_7d", "-share_28d"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "project"], name="ambient_attention_unique"
            ),
        ]

    def __str__(self) -> str:
        return (
            f"ProjectAttention(user={self.user_id}, project={self.project_id}, "
            f"7d={self.share_7d:.2f})"
        )


class ExtractionRun(models.Model):
    """One window read by the extractor (Plan 04). Counts and codes, no text.

    Keyed on the window's content hash, so an unchanged window is never sent to
    the model twice. ``refused`` holds the validator's *codes* ("not_grounded",
    "quote_in_text") and never its messages, which name the sentence that
    failed — and that sentence is a person's words.
    """

    class Outcome(models.TextChoices):
        READ = "read", "Read; observations kept"
        EMPTY = "empty", "Read; nothing groundable"
        REFUSED = "refused", "Read; every observation failed validation"
        UNAVAILABLE = "unavailable", "The model could not be reached"
        EXPIRED = "expired", "The text was gone before it could be read"

    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="extraction_runs"
    )
    # Null for a person's DMs, which belong to no lab. The per-lab daily cap
    # counts on this column.
    lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_extraction_runs",
    )
    place_id = models.CharField(max_length=64, blank=True, default="")
    conversation_key = models.CharField(max_length=128)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    content_hash = models.CharField(max_length=64)
    messages = models.PositiveSmallIntegerField(default=0)
    readable = models.PositiveSmallIntegerField(default=0)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    observations_kept = models.PositiveSmallIntegerField(default=0)
    refused = models.JSONField(default=list, blank=True)
    # Observations the extractor found but did not write because the speaker
    # keeps personal information out (Q-071). A count, never what they were.
    withheld = models.PositiveSmallIntegerField(default=0)
    engagement = models.PositiveSmallIntegerField(
        default=0,
        help_text="Replies to Mylo and reactions on its posts: engagement, "
        "never interest evidence.",
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["lab", "created_at"]),
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["content_hash"]),
        ]

    def __str__(self) -> str:
        return f"ExtractionRun({self.conversation_key}, {self.outcome})"


class Finding(models.Model):
    """What the deliberation step decided about one topic (Plan 04).

    One row per (person, concept, kind); per (person, project, concept, kind)
    for what one person said privately about a project; or per (project,
    concept, kind) for a lab project, built only from lab-visible observations
    so nothing said in a DM reaches the lab through a finding. Rewritten each
    night from the ledger, which is what makes deliberation pure: it costs no
    model call and can be rerun at will. The outcome is exactly one
    of the plan's six, and ``reason`` names the rule that chose it, so the trace
    Plan 07 shows and Plan 10 audits is the rule and its numbers, not a story.

    A finding changes nothing on its own. Plan 05 turns a ``suggest`` into a
    pending conversational edge, Plan 06 asks, Plan 08 applies what was agreed.
    """

    class Outcome(models.TextChoices):
        IGNORE = "ignore", "Ignore"
        RECORD = "record", "Record a stated project fact"
        SUGGEST = "suggest", "Suggest, and wait for an answer"
        CAPABILITY = "capability", "Suggest adding a skill"
        PROPOSE = "propose", "Propose an edit to the record"
        ASK = "ask", "Ask a clarifying question"

    class Explained(models.TextChoices):
        NOT_NEEDED = "not_needed", "No explanation needed"
        PENDING = "pending", "Waiting for the model"
        WRITTEN = "written", "Written"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_findings",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_findings",
    )
    concept = models.ForeignKey(
        "knowledge.Concept",
        on_delete=models.CASCADE,
        related_name="ambient_findings",
    )
    topic = models.CharField(max_length=200)
    facet = models.CharField(max_length=16, blank=True, default="")
    understanding_kind = models.CharField(
        max_length=24, choices=UnderstandingKind.choices
    )
    relation = models.CharField(max_length=24)
    visibility = models.CharField(max_length=16, choices=Visibility.choices)

    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    reason = models.CharField(max_length=48)
    # The consistency facts Plan 06 reads: distinct days, distinct
    # conversations, the span, the force mix, explicit count, the last
    # rejection, first and last seen.
    facts = models.JSONField(default=dict, blank=True)
    influence = models.FloatField(default=0.0)
    # Whether the declared profile has room, and what a swap would replace.
    budget = models.JSONField(default=dict, blank=True)
    trace = models.JSONField(default=dict, blank=True)
    observation_ids = models.JSONField(default=list, blank=True)

    explanation = models.TextField(blank=True, default="")
    explained = models.CharField(
        max_length=16, choices=Explained.choices, default=Explained.NOT_NEEDED
    )
    # The evidence the explanation was written from; a new observation makes it
    # stale and it is written again.
    explained_from = models.CharField(max_length=64, blank=True, default="")
    # Which outcome the downstream plans already acted on, so tonight's rerun
    # does not raise the same question twice.
    handled_outcome = models.CharField(max_length=16, blank=True, default="")
    handled_at = models.DateTimeField(null=True, blank=True)

    decided_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-decided_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                name="ambient_finding_has_subject",
                condition=models.Q(user__isnull=False)
                | models.Q(project__isnull=False),
            ),
            # About a person, from anything they said.
            models.UniqueConstraint(
                fields=["user", "concept", "understanding_kind"],
                condition=models.Q(user__isnull=False, project__isnull=True),
                name="ambient_finding_unique_personal",
            ),
            # About a project, from what one person said privately (a DM, or a
            # personal project): theirs alone, never the lab's.
            models.UniqueConstraint(
                fields=["user", "project", "concept", "understanding_kind"],
                condition=models.Q(user__isnull=False, project__isnull=False),
                name="ambient_finding_unique_personal_project",
            ),
            # About a lab project, from what was said on the lab's own surface.
            models.UniqueConstraint(
                fields=["project", "concept", "understanding_kind"],
                condition=models.Q(user__isnull=True, project__isnull=False),
                name="ambient_finding_unique_lab_project",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "outcome"]),
            models.Index(fields=["project", "outcome"]),
        ]

    def __str__(self) -> str:
        who = f"user={self.user_id}" if self.user_id else f"project={self.project_id}"
        return f"Finding({who}, {self.topic!r}, {self.outcome})"


class ProjectDevelopment(models.Model):
    """A dated event in a project, as Mylo understood it (Plan 05).

    "What is useful right now" for a project. It never edits ``ProjectState``
    — Plan 08 proposes state edits from it — and it is visible on the web with
    what, when, where it came from, and undo (Plan 07).

    Born one of two ways. A fact the person told Mylo directly is recorded
    ``active`` at once (OD-A3) with undo. A development seen consistently in
    ambient talk is ``pending`` until someone confirms it (Plan 06). A later
    development on the same subject supersedes an earlier one.

    Personal visibility means one person said it privately (a DM, or about a
    personal project): it is theirs, and no lab surface ever shows it.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for a confirmation"
        ACTIVE = "active", "Active"
        CONFIRMED = "confirmed", "Confirmed"
        SUPERSEDED = "superseded", "Superseded by a later development"
        REJECTED = "rejected", "Rejected, or undone"

    class Origin(models.TextChoices):
        TOLD = "told", "Told to Mylo directly"
        CONVERSATION = "conversation", "Seen in conversation, then confirmed"

    project = models.ForeignKey(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="ambient_developments",
    )
    # Who said it. For a personal development, also who may see it.
    speaker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_developments",
    )
    change = models.CharField(max_length=24, choices=Change.choices)
    topic = models.CharField(max_length=200)
    concept = models.ForeignKey(
        "knowledge.Concept",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_developments",
    )
    # Mylo's own account (the observation's), and its explanation of why.
    text = models.TextField()
    explanation = models.TextField(blank=True, default="")
    force = models.CharField(max_length=16, choices=Force.choices)
    occurred_on = models.DateField()
    recorded_on = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    origin = models.CharField(max_length=16, choices=Origin.choices)
    visibility = models.CharField(max_length=16, choices=Visibility.choices)
    finding = models.ForeignKey(
        Finding,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="developments",
    )
    observation_ids = models.JSONField(default=list, blank=True)
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_by",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Who confirmed, rejected, or undid it.",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-occurred_on", "-pk"]
        indexes = [
            models.Index(fields=["project", "status", "occurred_on"]),
            models.Index(fields=["speaker", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="ambient_development_has_text", condition=~models.Q(text="")
            ),
            models.CheckConstraint(
                name="ambient_development_has_visibility",
                condition=~models.Q(visibility=""),
            ),
        ]

    def __str__(self) -> str:
        return f"ProjectDevelopment({self.project_id}, {self.change}, {self.status})"

    @property
    def in_effect(self) -> bool:
        """Whether it changes anything: told, or confirmed; not undone."""
        return self.status in (self.Status.ACTIVE, self.Status.CONFIRMED)


class PendingSuggestion(models.Model):
    """One question Mylo wants to ask, on whichever surface is answered first.

    Plan 06. Created nightly from a decided :class:`Finding` (or a pending
    :class:`ProjectDevelopment`, or an exploration due for review), with the
    explanation the person will read and the choices that actually exist for
    them. It lives once and is read by both surfaces:

        pending → asked (DM and/or web) → answered | expired | withdrawn

    The first answer wins; the other surface shows where it was answered.
    Nothing it proposes changes anything until it is answered yes.
    """

    class Kind(models.TextChoices):
        INTEREST = "interest", "Include this interest?"
        SKILL = "skill", "Add this skill?"
        DEVELOPMENT = "development", "Did this happen in the project?"
        INTENT = "intent", "Has the project's aim changed?"
        CLARIFY = "clarify", "A clarifying question"
        REVIEW = "review", "Keep exploring this?"

    class State(models.TextChoices):
        PENDING = "pending", "Waiting to be asked"
        ASKED = "asked", "Asked"
        ANSWERED = "answered", "Answered"
        EXPIRED = "expired", "Expired unanswered"
        WITHDRAWN = "withdrawn", "Withdrawn (evidence gone, or shut off)"

    class Verdict(models.TextChoices):
        CONFIRMED = "confirmed", "Yes"
        REJECTED = "rejected", "No"
        CORRECTED = "corrected", "Corrected"
        DEFER = "defer", "Not now"
        UNCLEAR = "unclear", "Unclear"

    class Surface(models.TextChoices):
        DM = "dm", "A conversation with Mylo"
        WEB = "web", "The web"

    OPEN = (State.PENDING, State.ASKED)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_suggestions",
        help_text="Who is asked. For a lab project, a manager or the PI.",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    finding = models.ForeignKey(
        Finding,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suggestions",
    )
    development = models.ForeignKey(
        "ProjectDevelopment",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="suggestions",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_suggestions",
    )
    concept = models.ForeignKey(
        "knowledge.Concept",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ambient_suggestions",
    )
    relation = models.CharField(max_length=24, blank=True, default="")
    topic = models.CharField(max_length=200)
    # Why a clarifying question is being asked (attribution_unresolved,
    # subject_unclear, never_decided).
    reason = models.CharField(max_length=48, blank=True, default="")
    explanation = models.TextField(blank=True, default="")
    # [{"key": ..., "label": ...}] — only the choices that exist for this person
    # today: no "new theme" without a free slot, a swap offered instead.
    choices = models.JSONField(default=list, blank=True)
    influence = models.FloatField(default=0.0)

    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING, db_index=True
    )
    asked_at = models.DateTimeField(null=True, blank=True)
    # The Discord message the question went out as, so a reply to it is read
    # as an answer to this question and nothing else.
    dm_message_id = models.CharField(max_length=32, blank=True, default="")
    turns = models.PositiveSmallIntegerField(
        default=0, help_text="Dialogue turns taken: one question, two follow-ups."
    )

    answered_at = models.DateTimeField(null=True, blank=True)
    answered_on = models.CharField(
        max_length=8, choices=Surface.choices, blank=True, default=""
    )
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    verdict = models.CharField(
        max_length=16, choices=Verdict.choices, blank=True, default=""
    )
    choice = models.CharField(max_length=64, blank=True, default="")
    # A correction is the person's own words, typed to Mylo on purpose: a
    # stated edit, like one typed on the web. Short, and theirs.
    correction = models.CharField(max_length=200, blank=True, default="")
    # When the consequence was applied (the edge confirmed, the development
    # confirmed, the proposal raised), so the morning bell says so once.
    applied_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-influence", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind", "topic"],
                condition=models.Q(state__in=["pending", "asked"]),
                name="ambient_suggestion_one_open_per_topic",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "state"]),
            models.Index(fields=["dm_message_id"]),
        ]

    def __str__(self) -> str:
        return f"PendingSuggestion({self.kind}, {self.topic!r}, {self.state})"

    @property
    def is_open(self) -> bool:
        return self.state in self.OPEN


class ValidationRecord(models.Model):
    """One asked question and its answer — the labelled dataset. Append-only.

    What Plan 10 measures: was Mylo right? The finding as it stood, the
    explanation shown, the choices offered, where and when it was answered,
    and how. Nothing here is the person's words from conversation; a
    correction they typed to Mylo on purpose is kept as theirs.
    """

    suggestion = models.ForeignKey(
        PendingSuggestion,
        null=True,
        on_delete=models.SET_NULL,
        related_name="records",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_validations",
    )
    kind = models.CharField(max_length=16)
    understanding_kind = models.CharField(max_length=24, blank=True, default="")
    topic = models.CharField(max_length=200)
    finding_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="outcome, reason, facts, influence and trace at asking time.",
    )
    explanation = models.TextField(blank=True, default="")
    choices = models.JSONField(default=list, blank=True)
    surface = models.CharField(max_length=8, blank=True, default="")
    verdict = models.CharField(max_length=16)
    choice = models.CharField(max_length=64, blank=True, default="")
    correction = models.CharField(max_length=200, blank=True, default="")
    asked_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["kind", "verdict"])]

    def __str__(self) -> str:
        return f"ValidationRecord({self.kind}, {self.verdict})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("ValidationRecord is append-only; record a new row.")
        return super().save(*args, **kwargs)


class AppliedChange(models.Model):
    """Something Mylo understood that took effect — and how, and why (Plan 07).

    One row per change: an exploration confirmed, kept or let go; a skill, a
    preference, a direction or a learning goal confirmed; a project fact told
    to Mylo or confirmed; an edit to the declared profile or a project's state
    that the person accepted (Plan 08). It is what the "What changed" tab
    shows, with Undo, and what the weekly reports (Plan 09).

    An undo never erases the row: it stamps ``undone_at`` and writes its own
    row (``kind = undone``), so the history reads as it happened (OD-07b).
    """

    class Kind(models.TextChoices):
        EXPLORATION_CONFIRMED = "exploration_confirmed", "Exploration confirmed"
        EXPLORATION_KEPT = "exploration_kept", "Exploration kept"
        EXPLORATION_DROPPED = "exploration_dropped", "Exploration let go"
        UNDERSTANDING_CONFIRMED = "understanding_confirmed", "Understanding confirmed"
        DEVELOPMENT_RECORDED = "development_recorded", "Project fact recorded"
        DEVELOPMENT_CONFIRMED = "development_confirmed", "Project development confirmed"
        PROFILE_EDIT = "profile_edit", "Profile edited"
        STATE_EDIT = "state_edit", "Project state edited"
        UNDONE = "undone", "Undone"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ambient_changes",
        help_text="Whose change it is: the person, or who confirmed a lab one.",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_changes",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    topic = models.CharField(max_length=200)
    # For profile and state edits: the field path, and what it held before and
    # after — so an undo can put back exactly what was there.
    field = models.CharField(max_length=120, blank=True, default="")
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    # How it took effect: which surface, and from which question.
    surface = models.CharField(max_length=16, blank=True, default="")
    suggestion = models.ForeignKey(
        PendingSuggestion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="changes",
    )
    development = models.ForeignKey(
        ProjectDevelopment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="changes",
    )
    finding = models.ForeignKey(
        Finding, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    proposal_id = models.CharField(max_length=64, blank=True, default="")
    # The knowledge-core edge an undo reverses, by its key (ids only).
    concept = models.ForeignKey(
        "knowledge.Concept",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    relation = models.CharField(max_length=24, blank=True, default="")
    # Why — Mylo's explanation as the person saw it.
    explanation = models.TextField(blank=True, default="")
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PERSONAL
    )
    undo_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="undone_by",
    )
    undone_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["project", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"AppliedChange({self.kind}, {self.topic!r})"

    @property
    def undoable(self) -> bool:
        return self.kind != self.Kind.UNDONE and self.undone_at is None


class TranscriptMeeting(models.Model):
    """One meeting's transcript, read once (Plan 11, steps 9–12).

    The source it created is the consent: the organiser enabled Mylo for this
    meeting by uploading it. Turns by people who are not Mycelium users, not
    mapped, or not opted in to transcripts are dropped before the buffer and
    only counted here. The participants are told on the bell.
    """

    source = models.OneToOneField(
        Source, on_delete=models.CASCADE, related_name="meeting"
    )
    organiser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    project = models.ForeignKey(
        "research.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    title = models.CharField(max_length=200)
    occurred_at = models.DateTimeField()
    participant_ids = models.JSONField(default=list, blank=True)
    turns = models.PositiveIntegerField(default=0)
    counts = models.JSONField(default=dict, blank=True)
    announced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"TranscriptMeeting({self.title!r}, {self.occurred_at:%Y-%m-%d})"
