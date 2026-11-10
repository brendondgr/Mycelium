"""The agent's own records: threads, their append-only event log, messages
queued during a turn, the org and personal policy rows, and per-thread digests
for recall. Nothing here is a user-visible object the agent could change."""

from __future__ import annotations

import uuid

from apps.core.db import exactly_one
from django.conf import settings
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField

SCOPE_KINDS = ("personal", "lab", "department", "project")


class AgentThread(models.Model):
    """One conversation, owned by the person who started it, or shared.

    The scope says where it was opened: personal, or a lab, department or
    project. A thread opened in an org's scope is still that person's
    conversation; nobody else can read it.

    A **shared** thread (Discord: a forum or Discord thread, plan D) has no
    owner and belongs to its place: everyone who asks there takes turns in
    one conversation, each turn under its own asker (the ``speaker`` and
    ``turn`` of its ``user`` event). No web route returns a shared thread.
    """

    class State(models.TextChoices):
        IDLE = "idle"
        RUNNING = "running"
        WAITING = "waiting"
        ERROR = "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_threads",
    )
    #: No owner: the thread belongs to its place (exactly when ``user`` is null).
    shared = models.BooleanField(default=False)
    scope_kind = models.CharField(
        max_length=12, choices=[(k, k) for k in SCOPE_KINDS], default="personal"
    )
    scope_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    scope_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    scope_project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    surface = models.CharField(max_length=12, default="web")
    title = models.CharField(max_length=200, blank=True, default="")
    #: One line on why the person is asking, written with the title.
    purpose = models.CharField(max_length=300, blank=True, default="")
    state = models.CharField(max_length=10, choices=State.choices, default=State.IDLE)
    mode = models.CharField(max_length=10, default="read")
    #: Loaded functions, numbered references, todos. Survives compaction.
    settings = models.JSONField(default=dict, blank=True)
    archived = models.BooleanField(default=False)
    #: Kept at the top of the person's list (S3).
    pinned = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="forks"
    )
    fork_seq = models.PositiveIntegerField(null=True, blank=True)
    #: Learning: the last seq the learning pass read, and its backoff.
    learned_seq = models.PositiveIntegerField(default=0)
    learn_after = models.DateTimeField(null=True, blank=True)
    learn_failures = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    #: The last time the person or the agent added to the thread.
    last_activity_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-last_activity_at"]
        constraints = [
            models.CheckConstraint(
                name="agent_thread_shared_has_no_owner",
                condition=Q(shared=True, user__isnull=True)
                | Q(shared=False, user__isnull=False),
            ),
            models.CheckConstraint(
                name="agent_thread_scope_matches_kind",
                condition=(
                    Q(
                        scope_kind="personal",
                        scope_lab__isnull=True,
                        scope_department__isnull=True,
                        scope_project__isnull=True,
                    )
                    | (
                        Q(scope_kind="lab")
                        & exactly_one("scope_lab", "scope_department", "scope_project")
                        & Q(scope_lab__isnull=False)
                    )
                    | (
                        Q(scope_kind="department")
                        & exactly_one("scope_lab", "scope_department", "scope_project")
                        & Q(scope_department__isnull=False)
                    )
                    | (
                        Q(scope_kind="project")
                        & exactly_one("scope_lab", "scope_department", "scope_project")
                        & Q(scope_project__isnull=False)
                    )
                ),
            ),
        ]

    @property
    def scope_object(self):
        return self.scope_lab or self.scope_department or self.scope_project

    def __str__(self) -> str:
        owner = "shared" if self.shared else self.user_id
        return f"{self.title or 'thread'} ({owner}, {self.scope_kind})"


class AgentEvent(models.Model):
    """One entry in a thread's append-only log. ``seq`` starts at 1."""

    TYPES = (
        "user",
        "recall",
        "thinking",
        "assistant",
        "tool_call",
        "tool_result",
        "question",
        "answer",
        "todos",
        "usage",
        "compact",
        "note",
        "error",
        "state",
        "verdict",
    )

    thread = models.ForeignKey(
        AgentThread, on_delete=models.CASCADE, related_name="events"
    )
    seq = models.PositiveIntegerField()
    ts = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=16, choices=[(t, t) for t in TYPES])
    payload = models.JSONField(default=dict, blank=True)
    tokens = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["thread", "seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "seq"], name="agent_event_unique_seq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.thread_id}#{self.seq} {self.type}"


class AgentQueuedMessage(models.Model):
    """A message sent while a turn was running, answered when it ends."""

    thread = models.ForeignKey(
        AgentThread, on_delete=models.CASCADE, related_name="queued"
    )
    text = models.TextField()
    mentions = models.JSONField(default=list, blank=True)
    #: Who asked and from where (shared threads): copied into the ``user``
    #: event when the message gets its own turn.
    speaker = models.JSONField(default=dict, blank=True)
    turn = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class AgentOrgPolicy(models.Model):
    """What a lab or department narrows for its members. Optional: with no
    row nothing is narrowed. It can never turn the agent on (D-5)."""

    lab = models.OneToOneField(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    department = models.OneToOneField(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    groups_off = models.JSONField(default=list, blank=True)
    discord_channels_off = models.JSONField(default=list, blank=True)
    #: What a guest (someone in the org's Discord server with no account) is
    #: told: ``full``, ``no_people``, ``public`` or ``off``. The host's
    #: ``discord_guest_level`` caps it; the lower of the two wins (S-16).
    discord_guests = models.CharField(max_length=12, default="full")
    max_risk = models.CharField(max_length=12, default="read")
    #: Whether members' chats may inform the lab's shared understanding.
    members_inform_org = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="agent_org_policy_one_org",
                condition=exactly_one("lab", "department"),
            )
        ]


class AgentPreference(models.Model):
    """A person's own switches. No row: chat on, Discord allowed. Learning
    from chats is not here: it is ambient's ``ListeningConsent`` for the
    ``agent_chat`` platform (on unless the person turned it off, D-3), so
    "Mylo & you" and the agent read one switch."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_preference",
    )
    chat_enabled = models.BooleanField(default=True)
    discord_allowed = models.BooleanField(default=True)
    groups_off = models.JSONField(default=list, blank=True)
    #: When the person was told, once, that Mylo learns from chats.
    learning_notice_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class AgentThreadDigest(models.Model):
    """What recall matches a later question against: the thread's purpose,
    title, summary and the person's own words (never the agent's)."""

    thread = models.OneToOneField(
        AgentThread, on_delete=models.CASCADE, related_name="digest"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    text = models.TextField(blank=True, default="")
    embedding = VectorField(null=True, blank=True)
    upto_seq = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class AgentThreadLink(models.Model):
    """Which Discord place a thread answers in (plan D).

    A forum or Discord thread has one shared link (``discord_user_id`` empty);
    an open channel and a DM have one link per person. ``binding_id`` is the
    owning integrations binding, kept as a plain id (no foreign key from a
    tool into a platform app that does not need one)."""

    thread = models.ForeignKey(
        AgentThread, on_delete=models.CASCADE, related_name="discord_links"
    )
    guild_id = models.CharField(max_length=32, blank=True, default="")
    place_id = models.CharField(max_length=32)
    discord_user_id = models.CharField(max_length=32, blank=True, default="")
    binding_id = models.BigIntegerField(null=True, blank=True)
    #: ``{kind, key}`` of what the place is about, or ``{}``.
    anchor = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["guild_id", "place_id", "discord_user_id"],
                condition=Q(closed_at__isnull=True),
                name="agent_thread_link_one_open",
            )
        ]
        indexes = [models.Index(fields=["place_id"], name="agent_link_place")]

    def __str__(self) -> str:
        who = self.discord_user_id or "shared"
        return f"AgentThreadLink({self.guild_id or 'dm'}/{self.place_id}, {who})"


class AgentDiscordTurn(models.Model):
    """One question asked in Discord and where its answer goes. What makes
    delivery survive a bot restart: pending rows are looked for on start."""

    class State(models.TextChoices):
        PENDING = "pending"
        ANSWERED = "answered"
        FAILED = "failed"
        CANCELLED = "cancelled"

    link = models.ForeignKey(
        AgentThreadLink, on_delete=models.CASCADE, related_name="turns"
    )
    #: The ``user`` event, or 0 while the question waits in the queue.
    user_event_seq = models.PositiveIntegerField(default=0)
    #: The ``AgentQueuedMessage`` while it waits; its ``user`` event carries
    #: the same id as ``queued_id`` once it gets its turn.
    queued_id = models.BigIntegerField(null=True, blank=True)
    trigger_message_id = models.CharField(max_length=32, db_index=True)
    channel_id = models.CharField(max_length=32, blank=True, default="")
    status_message_id = models.CharField(max_length=32, blank=True, default="")
    #: Every other message the answer was posted as (later chunks, a slow
    #: answer's ping), so a reply to any of them finds this conversation.
    message_ids = models.JSONField(default=list, blank=True)
    discord_user_id = models.CharField(max_length=32)
    #: Asked without an account: counted against the guest limits.
    guest = models.BooleanField(default=False)
    state = models.CharField(
        max_length=10, choices=State.choices, default=State.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["state"], name="agent_dturn_state")]
