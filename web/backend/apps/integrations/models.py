"""Discord integration data model — all in Mycelium's Postgres.

Three tables, one per link concern:

* ``DiscordIdentity``   — a Mycelium user's Discord identity (Path A/B). An
  *authentication* artifact only; it confers no authorization (see the plan §7 and
  ``services.resolve``).
* ``DiscordActivationCode`` — the Path B fallback: a short-lived, single-use code a
  user redeems from Discord to bind their identity without OAuth.
* ``DiscordLabActivationCode`` — the Path C code: a short-lived, single-use, 10-digit
  code a lab manager issues on the website and redeems in a guild via
  ``/activate-lab`` to bind *that guild* to *that lab*. The manager authority lives
  at issuance; the code carries it into Discord (no linked identity required).
* ``DiscordGuildLink``  — a Discord server bound to a Lab (Path C). One guild ↔ one
  lab, gated on real Mycelium lab authority.

Auditing reuses ``apps.accounts.services.record_audit_event`` — no table here.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .fields import EncryptedTextField


class DiscordIdentity(models.Model):
    """A Mycelium user's Discord identity. Authentication only — no authorization."""

    class State(models.TextChoices):
        PENDING = "pending", "Pending"  # flow started, not confirmed
        ACTIVE = "active", "Active"  # bound
        REVOKED = "revoked", "Revoked"  # unlinked / deauthorized

    class LinkMethod(models.TextChoices):
        OAUTH = "oauth", "OAuth"
        ACTIVATION_CODE = "activation_code", "Activation code"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discord",
    )
    # The snowflake — the ONLY identity key. Usernames change and are never a key.
    discord_user_id = models.CharField(max_length=32, unique=True, db_index=True)
    username_cache = models.CharField(max_length=64, blank=True)  # display only
    global_name_cache = models.CharField(max_length=64, blank=True)
    dm_channel_id = models.CharField(max_length=32, blank=True)  # cached; stable

    link_method = models.CharField(max_length=16, choices=LinkMethod.choices)
    # OAuth scopes granted. JSONField (not ArrayField) so the model works on both
    # SQLite (tests) and Postgres; we never query by scope.
    scopes = models.JSONField(default=list, blank=True)
    access_token = EncryptedTextField(blank=True, default="")  # empty on code path
    refresh_token = EncryptedTextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)

    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    # Reachability, orthogonal to `state`: a link can be ACTIVE with dm_ok=False.
    # null = unknown, True = a probe DM landed, False = blocked (50007).
    dm_ok = models.BooleanField(null=True, blank=True)
    dm_checked_at = models.DateTimeField(null=True, blank=True)
    # Delivery preference for the daily "Mylo Report" DM (the PDF report). Opt-OUT,
    # not opt-in: an ACTIVE, entitled user is messaged by default, and unchecking the
    # toggle on the profile Discord card suppresses only this scheduled DM (reminders
    # and everything else are unaffected). Kept here, not on WatchPreference, because
    # it is meaningful only for a linked identity and reads/writes through the same
    # resolve boundary as the rest of the Discord state.
    daily_report_opt_out = models.BooleanField(default=False)

    linked_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Discord identity"
        verbose_name_plural = "Discord identities"

    def __str__(self) -> str:
        return f"DiscordIdentity(user={self.user_id}, state={self.state})"


class DiscordActivationCode(models.Model):
    """Path B: a short-lived, single-use code a user redeems from Discord.

    Only the sha256 of the plaintext is stored; the plaintext is shown once at
    issue and never persisted or logged.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discord_codes",
    )
    code_hash = models.CharField(max_length=64, db_index=True)  # sha256 hex
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # created_at + TTL
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_by_discord_id = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["code_hash", "expires_at"])]

    def __str__(self) -> str:
        state = "consumed" if self.consumed_at else "live"
        return f"DiscordActivationCode(user={self.user_id}, {state})"


class DiscordLabActivationCode(models.Model):
    """Path C: a short-lived, single-use code that binds a guild to a lab.

    A lab manager issues it on the website (authority checked there); it is redeemed
    in Discord via ``/activate-lab code:``. Only the sha256 of the plaintext is
    stored; the plaintext (10 digits) is shown once at issue and never persisted or
    logged. Redemption binds *the guild the command ran in* to ``lab``.
    """

    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.CASCADE,
        related_name="discord_lab_codes",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discord_lab_codes_issued",
    )
    code_hash = models.CharField(max_length=64, db_index=True)  # sha256 hex
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # created_at + TTL
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_by_discord_id = models.CharField(max_length=32, blank=True)
    consumed_guild_id = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["code_hash", "expires_at"])]

    def __str__(self) -> str:
        state = "consumed" if self.consumed_at else "live"
        return f"DiscordLabActivationCode(lab={self.lab_id}, {state})"


class DiscordGuildLink(models.Model):
    """A Discord server bound to a Lab. One guild ↔ one lab."""

    class State(models.TextChoices):
        PENDING_SETUP = "pending_setup", "Pending setup"  # installed, unclaimed
        ACTIVE = "active", "Active"  # confirmed by a lab manager
        KICKED = "kicked", "Kicked"

    lab = models.OneToOneField(
        "accounts.Lab",
        on_delete=models.CASCADE,
        related_name="discord_link",
    )
    guild_id = models.CharField(max_length=32, unique=True, db_index=True)
    guild_name_cache = models.CharField(max_length=100, blank=True)
    installed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discord_guild_installs",
    )
    # Load-bearing: the binding is trusted only because it came from the OAuth
    # code-grant token exchange (an authoritative `guild` object), not from the
    # forgeable redirect params. Downstream use gates on this being True.
    verified_via_code_grant = models.BooleanField(default=False)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING_SETUP
    )
    # Deadline-announcements channel for lab reminders (Discord reminders R4). Bound
    # and channel-scope-verified at `/setup` by posting a real confirmation (Discord
    # computes channel overwrites for us); blank until a channel is bound. Optional:
    # a blank value is an explicit opt-out of deadline announcements.
    announcement_channel_id = models.CharField(max_length=32, blank=True, default="")
    channel_verified_at = models.DateTimeField(null=True, blank=True)
    # Daily/weekly-updates channel — an independent, optional `/setup` binding (blank
    # = opt-out). Config only for now; recurring delivery to it is a follow-up.
    updates_channel_id = models.CharField(max_length=32, blank=True, default="")
    updates_channel_verified_at = models.DateTimeField(null=True, blank=True)
    # Live reachability of each bound channel, mirroring DiscordIdentity.dm_ok:
    # null = not checked, True = Mylo can post there, False = it cannot (deleted,
    # made private, or an overwrite denies posting). Written by the reconcile sweep,
    # by a permanent outbox failure, and by a gateway channel-delete event — three
    # sources for one fact, because none of them alone is reliable.
    announcement_channel_ok = models.BooleanField(null=True, blank=True)
    updates_channel_ok = models.BooleanField(null=True, blank=True)
    channel_checked_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.IntegerField(null=True, blank=True)
    # Whether the lab's Mylo add-on was live at the last check. A lapse stops
    # scheduled delivery and nothing else — see `lab_digest.eligible_labs`.
    addon_ok = models.BooleanField(null=True, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"DiscordGuildLink(lab={self.lab_id}, state={self.state})"


class DiscordOutboxMessage(models.Model):
    """One outbound Discord message, durable from decision to delivery.

    The problem this exists for: senders used to call Discord inline and record the
    attempt as done either way, so a thirty-second outage silently retired that
    person's reminder for good. The queue moves the "don't send this twice" record to
    **enqueue** time, so the guarantee survives while a failed attempt stays claimable
    instead of vanishing.

    ``dedupe_key`` is the logical identity of a message ("this subscription's fire for
    this deadline date"), unique so a producer can be re-run safely — re-enqueueing is
    a no-op, not a second message. ``id`` is a plain integer rather than a UUID
    specifically so it fits Discord's 25-character ``nonce`` limit: it is sent with
    ``enforce_nonce`` so an attempt Discord accepted but whose response we never saw
    returns the existing message instead of posting a duplicate.

    ``subject_type``/``subject_id`` are provenance, not a foreign key: they point back
    at whatever produced the message (a reminder fire, a daily briefing) across app
    boundaries and survive that row being deleted, which is what makes a dead letter
    traceable months later.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"  # claimed by a drain, attempt in flight
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"  # permanent — retrying cannot help
        DEAD = "dead", "Dead"  # attempts exhausted

    #: Statuses no drain will ever pick up again.
    TERMINAL = (Status.SENT, Status.FAILED, Status.DEAD)

    class Target(models.TextChoices):
        DM = "dm", "Direct message"
        CHANNEL = "channel", "Channel"

    dedupe_key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=40)  # reminder | daily_report | lab_digest | …
    target_type = models.CharField(max_length=16, choices=Target.choices)
    # DM: whose identity to resolve *at send time* — a cached dm_channel_id can go
    # stale between enqueue and delivery, so the channel is never frozen here.
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discord_outbox",
    )
    channel_id = models.CharField(max_length=32, blank=True, default="")
    # Provenance for a channel send: which lab's binding produced it, so a permanent
    # failure can flag that binding and reach the right managers.
    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discord_outbox",
    )
    content = models.TextField(blank=True, default="")
    embed = models.JSONField(null=True, blank=True)
    # Message components (action rows of buttons), passed to Discord as they
    # are. Only Mylo's own questions (ambient Plan 06) carry any; their button
    # ids are answered by the gateway, never by a stranger.
    components = models.JSONField(null=True, blank=True)
    allowed_mentions = models.JSONField(null=True, blank=True)
    # A path, not bytes: the daily report runs 0.2–2 MB and would bloat both this
    # table and every unqualified SELECT against it. The retention sweep owns deletion.
    attachment_path = models.CharField(max_length=500, blank=True, default="")
    attachment_filename = models.CharField(max_length=200, blank=True, default="")
    subject_type = models.CharField(max_length=40, blank=True, default="")
    subject_id = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    last_error_code = models.IntegerField(null=True, blank=True)
    last_error_reason = models.CharField(max_length=40, blank=True, default="")
    discord_message_id = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # The drain's only query: due, unsettled work in arrival order.
            models.Index(fields=["status", "next_attempt_at"]),
        ]
        ordering = ["next_attempt_at", "id"]

    def __str__(self) -> str:
        return f"DiscordOutboxMessage({self.kind}, {self.status}, {self.dedupe_key})"

    @property
    def nonce(self) -> str:
        """Discord's idempotency token for this row (25-char limit — an int fits)."""
        return str(self.pk)


# --------------------------------------------------------------------------- #
# Slack (ambient Plan 11) — the second platform, over the same ledger
# --------------------------------------------------------------------------- #


class SlackWorkspace(models.Model):
    """One Slack workspace Mylo was installed in, and the lab it belongs to.

    The bot token comes from Slack's OAuth install and is encrypted at rest.
    ``lab`` is bound separately, by a lab manager's link code posted in a
    channel of the workspace (the Discord Path C, carried over), so installing
    the app is not by itself authority over any lab.
    """

    team_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120, blank=True, default="")
    bot_token = EncryptedTextField(blank=True, default="")
    bot_user_id = models.CharField(max_length=32, blank=True, default="")
    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="slack_workspaces",
    )
    # Where the lab's reports go: the channel the lab was linked from.
    updates_channel_id = models.CharField(max_length=32, blank=True, default="")
    # A lab on both Discord and Slack chooses where its posts go (Plan 11,
    # rule 15). Off: Discord stays the lab's surface; on: Slack does.
    reports_primary = models.BooleanField(default=False)
    installed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"SlackWorkspace({self.team_id}, lab={self.lab_id})"


class SlackIdentity(models.Model):
    """A Mycelium user's Slack identity in one workspace.

    Slack user ids are unique per workspace, so the key is the pair. Like
    ``DiscordIdentity`` it authenticates and confers no authorization.
    """

    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="slack_identities",
    )
    team_id = models.CharField(max_length=32)
    slack_user_id = models.CharField(max_length=32)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.ACTIVE
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team_id", "slack_user_id"],
                condition=models.Q(state="active"),
                name="slack_identity_one_active_per_slack_user",
            ),
            models.UniqueConstraint(
                fields=["user", "team_id"],
                condition=models.Q(state="active"),
                name="slack_identity_one_active_per_user_and_team",
            ),
        ]

    def __str__(self) -> str:
        return f"SlackIdentity({self.team_id}:{self.slack_user_id} → {self.user_id})"


class LinkCode(models.Model):
    """A short-lived, single-use code that carries authority into Slack or
    Teams (ambient Plan 11).

    ``person``: issued to a signed-in user, redeemed by DMing it to Mylo, which
    binds the platform user who sent it to that account. ``lab``: issued by a
    lab manager, redeemed by mentioning Mylo with it in a channel, which binds
    the workspace or team to the lab and makes that channel the lab's updates
    channel. The code is stored only as a hash, and is good on its own
    platform only.
    """

    class Kind(models.TextChoices):
        PERSON = "person", "Link a person"
        LAB = "lab", "Link a lab"

    platform = models.CharField(max_length=16, default="slack")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    code_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_team_id = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class SlackOutboxMessage(models.Model):
    """One outbound Slack message, durable from decision to delivery.

    The same contract as :class:`DiscordOutboxMessage`: the dedupe key is the
    message's logical identity and is unique, so producers can be re-run; a
    failed attempt stays claimable until its attempts run out.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DEAD = "dead", "Dead"

    TERMINAL = (Status.SENT, Status.FAILED, Status.DEAD)

    class Target(models.TextChoices):
        DM = "dm", "Direct message"
        CHANNEL = "channel", "Channel"

    dedupe_key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=40)
    target_type = models.CharField(max_length=16, choices=Target.choices)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="slack_outbox",
    )
    team_id = models.CharField(max_length=32)
    channel_id = models.CharField(max_length=32, blank=True, default="")
    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="slack_outbox",
    )
    text = models.TextField(blank=True, default="")
    blocks = models.JSONField(null=True, blank=True)
    subject_type = models.CharField(max_length=40, blank=True, default="")
    subject_id = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    last_error = models.CharField(max_length=64, blank=True, default="")
    slack_ts = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        ordering = ["next_attempt_at", "id"]


# --------------------------------------------------------------------------- #
# Microsoft Teams (ambient Plan 11) — the Bot Framework, over the same ledger
# --------------------------------------------------------------------------- #


class TeamsTeamLink(models.Model):
    """A Teams team Mylo was installed in, and the lab it belongs to.

    Reading channel messages without a mention needs resource-specific consent
    (``ChannelMessage.Read.Group``) that a tenant admin grants at install; that
    is the Plan 02 "server" consent, held by an admin. The lab is bound by a
    lab manager's code, as on Slack.
    """

    team_id = models.CharField(max_length=128, unique=True)
    tenant_id = models.CharField(max_length=64)
    name = models.CharField(max_length=120, blank=True, default="")
    service_url = models.CharField(max_length=300)
    lab = models.ForeignKey(
        "accounts.Lab",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teams_links",
    )
    updates_conversation_id = models.CharField(max_length=300, blank=True, default="")
    reports_primary = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TeamsIdentity(models.Model):
    """A Mycelium user's Teams identity: the Azure AD object id in a tenant,
    and the personal chat Mylo can reach them in."""

    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teams_identities",
    )
    tenant_id = models.CharField(max_length=64)
    aad_object_id = models.CharField(max_length=64)
    service_url = models.CharField(max_length=300, blank=True, default="")
    conversation_id = models.CharField(max_length=300, blank=True, default="")
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.ACTIVE
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "aad_object_id"],
                condition=models.Q(state="active"),
                name="teams_identity_one_active_per_aad_user",
            ),
        ]


class TeamsOutboxMessage(models.Model):
    """One outbound Teams message; the Slack outbox's contract."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DEAD = "dead", "Dead"

    dedupe_key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=40)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="teams_outbox",
    )
    service_url = models.CharField(max_length=300)
    conversation_id = models.CharField(max_length=300)
    text = models.TextField(blank=True, default="")
    attachments = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    last_error = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        ordering = ["next_attempt_at", "id"]
