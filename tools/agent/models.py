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
    """One conversation, owned by the person who started it.

    The scope says where it was opened: personal, or a lab, department or
    project. A thread opened in an org's scope is still that person's
    conversation; nobody else can read it.
    """

    class State(models.TextChoices):
        IDLE = "idle"
        RUNNING = "running"
        WAITING = "waiting"
        ERROR = "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_threads"
    )
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
            )
        ]

    @property
    def scope_object(self):
        return self.scope_lab or self.scope_department or self.scope_project

    def __str__(self) -> str:
        return f"{self.title or 'thread'} ({self.user_id}, {self.scope_kind})"


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
