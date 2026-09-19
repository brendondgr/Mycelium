import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from pgvector.django import VectorField


class AcademicTitle(models.TextChoices):
    """Career stage on a person's profile — drives stage/eligibility matching.

    Orthogonal to a membership's permission role (briefing §5): a person whose
    title is ``pi`` may lead one lab and be a plain ``member`` of another.
    """

    STUDENT = "student", "Student"
    POSTDOC = "postdoc", "Postdoc"
    RESEARCHER = "researcher", "Researcher"
    PI = "pi", "PI"
    STAFF = "staff", "Staff"


class Department(models.Model):
    """Top-of-hierarchy container controlled by a single owning user.

    The owner manages which labs belong to the department and who its direct
    members are. ``institution`` is a denormalized string attribute, not a
    controlled entity (see briefing §8).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_departments",
    )
    name = models.CharField(max_length=200)
    institution = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Lab(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="labs",
        help_text="Set or cleared by the department owner.",
    )
    department_plan_included = models.BooleanField(
        default=False,
        help_text=(
            "When true, this lab's members are covered (and paid for) by the "
            "department's plan. Opt-in: the department head includes a lab "
            "explicitly. Only meaningful while the lab belongs to a department."
        ),
    )
    # Reminder scheduling (Discord reminders R4). Use the IANA zone name, not "EST":
    # the zone handles the DST transition, so a "9am" reminder is 9am local year-round.
    timezone = models.CharField(
        max_length=64,
        default="America/New_York",
        help_text="IANA time zone for lab reminders (e.g. America/New_York).",
    )
    send_hour_local = models.PositiveSmallIntegerField(
        default=9,
        help_text="Local hour (0–23) reminders target; day-granular for now.",
    )
    # Optional lab logo, shown as the workspace's brand mark in the sidebar. A
    # plain FileField (not ImageField) so Pillow isn't required; the upload view
    # sniffs the magic bytes and stores the validated content type for serving.
    # Served through the API (LabLogoView), never via MEDIA_URL directly.
    logo = models.FileField(upload_to="lab-logos/", null=True, blank=True)
    logo_content_type = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def has_logo(self) -> bool:
        return bool(self.logo)

    @property
    def logo_version(self) -> int | None:
        """A cache-busting token for the logo URL (its last-modified epoch)."""
        if not self.logo:
            return None
        return int(self.updated_at.timestamp()) if self.updated_at else 0


class LabMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lab_memberships",
    )
    lab = models.ForeignKey(
        Lab,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    is_lead = models.BooleanField(
        default=False,
        help_text="Marks a PI of this lab; counted against per-tier PI caps.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lab"],
                name="accounts_unique_lab_membership",
            ),
        ]
        ordering = ["lab__name", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.lab} ({self.role})"


class DeptMembership(models.Model):
    """Direct department membership for people not attached via a lab.

    Department admins and unaffiliated researchers join here. Members attached
    through a lab are folded in via the derived effective-membership set
    (briefing §4) rather than duplicated as rows here.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dept_memberships",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "department"],
                name="accounts_unique_dept_membership",
            ),
        ]
        ordering = ["department__name", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.department} ({self.role})"


class Profile(models.Model):
    """One per user: research identity, career stage, and interest embedding.

    ``academic_title`` and ``institution`` are person-global account attributes
    (briefing §3 USER). ``institution`` is never typed: it mirrors what the
    verified email proves (``apps.accounts.institution.sync``), and is empty
    until the address is verified or when it is a personal one. ``interests``
    and ``embedding`` are the interest
    relevance target used in scoring. The embedding dimension is intentionally
    left unlocked until the scoring phase (briefing §9).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    academic_title = models.CharField(
        max_length=20,
        choices=AcademicTitle.choices,
        default=AcademicTitle.RESEARCHER,
    )
    institution = models.CharField(max_length=255, blank=True, default="")
    orcid = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        help_text="ORCID iD (bare, e.g. 0000-0002-1825-0097). Audit trail for imports.",
    )
    openalex_id = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        help_text="OpenAlex author id (e.g. A5023888391); lets a profile re-import.",
    )
    scholar_id = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        help_text="Google Scholar author id (the scholar_id query param).",
    )
    interests = models.JSONField(
        default=dict,
        blank=True,
        help_text="Keywords, areas, skills, eligibility constraints, funding needs.",
    )
    embedding = VectorField(
        null=True,
        blank=True,
        help_text="Derived from interests; the interest relevance target.",
    )
    embedding_text = models.TextField(
        blank=True,
        default="",
        help_text="Canonical text the embedding hook (re)embeds; vector dim deferred.",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Email verified. Non-blocking at signup; gates sensitive actions.",
    )
    watch_topic_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Admin-granted override for how many watch topics this user may "
            "monitor. Null uses the plan's per-tier cap; set only from the admin "
            "dashboard. Read through apps.billing.entitlements.topic_cap."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile<{self.user}>"


class _InterestSurface(models.Model):
    """Shared interest-profile fields for labs and departments (brief Phase D).

    Mirrors :class:`Profile`: a free-form ``interests`` contract JSON, a curated
    ``embedding``, and a ``derived_embedding`` blended from member and project
    embeddings at score time. ``embedding_text`` is the canonical text the
    embedding hook persists now while the vector dimension stays unlocked.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement = models.TextField(blank=True, default="")
    areas = models.JSONField(default=list, blank=True)
    funding_needs = models.JSONField(default=list, blank=True)
    strategic_needs = models.JSONField(default=list, blank=True)
    interests = models.JSONField(
        default=dict,
        blank=True,
        help_text="Curated interests contract (apps.accounts.interests).",
    )
    embedding = VectorField(
        null=True,
        blank=True,
        help_text="Curated vector, derived from the contract text.",
    )
    derived_embedding = VectorField(
        null=True,
        blank=True,
        help_text="Vector blended from member and project embeddings.",
    )
    embedding_text = models.TextField(
        blank=True,
        default="",
        help_text="Canonical text the embedding hook (re)embeds; vector dim deferred.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LabProfile(_InterestSurface):
    """One interest profile per lab, auto-created via ``post_save`` on Lab."""

    lab = models.OneToOneField(
        Lab,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    def __str__(self) -> str:
        return f"LabProfile<{self.lab}>"


class DeptProfile(_InterestSurface):
    """One interest profile per department, auto-created via ``post_save``."""

    department = models.OneToOneField(
        Department,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    def __str__(self) -> str:
        return f"DeptProfile<{self.department}>"


class WatchCadence(models.TextChoices):
    """How often Mylo **pushes** what it is watching (plan D2).

    Cadence governs Discord — a DM to a person, a post to a lab's channel — and
    nothing else. The nightly run scores every scheduled-eligible target and writes
    its briefing every day regardless, and the web app shows that briefing, its
    alerts and its bell notifications every day regardless. Choosing Weekly asks
    not to be interrupted; it does not ask Mylo to stop working.
    """

    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"


#: Accepted ranges for the two timeline placeholders (open decision OD8). Wide on
#: purpose: they are a reader's own judgement about how much runway a submission
#: needs, and Mylo has no basis for narrowing them beyond "not negative" and "not
#: longer than a planning horizon anyone holds".
DEADLINE_BUFFER_RANGE = (0, 90)
MIN_PAPER_WINDOW_RANGE = (7, 365)
DEFAULT_DEADLINE_BUFFER_DAYS = 14
DEFAULT_MIN_PAPER_WINDOW_DAYS = 60


def _buffer_field(owner: str):
    """The deadline-buffer column, worded for whichever row carries it."""
    return models.PositiveSmallIntegerField(
        default=DEFAULT_DEADLINE_BUFFER_DAYS,
        validators=[
            MinValueValidator(DEADLINE_BUFFER_RANGE[0]),
            MaxValueValidator(DEADLINE_BUFFER_RANGE[1]),
        ],
        help_text=(
            f"Days of slack {owner} wants between a milestone and a deadline "
            "before Mylo calls the venue a fit. A placeholder, adjustable here "
            "and overridable per project."
        ),
    )


def _window_field(owner: str):
    """The minimum-paper-window column, worded for whichever row carries it."""
    return models.PositiveSmallIntegerField(
        default=DEFAULT_MIN_PAPER_WINDOW_DAYS,
        validators=[
            MinValueValidator(MIN_PAPER_WINDOW_RANGE[0]),
            MaxValueValidator(MIN_PAPER_WINDOW_RANGE[1]),
        ],
        help_text=(
            f"Fewest days {owner} considers enough to write a full paper. Below "
            "it Mylo calls a venue not viable rather than tight."
        ),
    )


class WatchPreference(models.Model):
    """What Mylo should keep an eye on for one user.

    Captured in the final onboarding step ("what should Mylo keep an eye on")
    and editable later: the topics to monitor (research areas and keywords,
    seeded from the user's interests), which kinds of signals to surface, and how
    often. One row per user, created on first save — no signal backfill, so
    existing users get a row the first time they set their watch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watch",
    )
    topics = models.JSONField(
        default=list,
        blank=True,
        help_text="Research areas/keywords Mylo monitors (seeded from interests).",
    )
    categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Signal kinds to surface: papers, grants, fellowships, etc.",
    )
    cadence = models.CharField(
        max_length=20,
        choices=WatchCadence.choices,
        default=WatchCadence.DAILY,
        help_text="How often Mylo messages this person on Discord (plan D1/D2).",
    )
    # Delivery timing (plan M1). A lab keeps the equivalent pair on ``Lab`` itself,
    # where the reminder scheduler already reads them; a person has no other row to
    # put them on, and this is where their other delivery preferences live.
    timezone = models.CharField(
        max_length=64,
        default="America/New_York",
        help_text="IANA zone the send hour is read in (e.g. America/New_York).",
    )
    send_hour_local = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Local hour (0–23) the Discord push targets; day-granular.",
    )
    urgent_alerts = models.BooleanField(
        default=False,
        help_text=(
            "Weekly cadence only (open decision OD2): allow one DM between "
            "Mondays when a deadline moves on a saved item due inside the "
            "buffer. Off by default — it is the single case where waiting until "
            "Monday costs something real, not a second daily."
        ),
    )
    deadline_buffer_days = _buffer_field("this person")
    min_paper_window_days = _window_field("this person")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"WatchPreference<{self.user}>"


class LabWatchPreference(models.Model):
    """What Mylo should keep an eye on for one lab.

    The lab-level counterpart of :class:`WatchPreference`: the shared topics a
    lab monitors (seeded from its collective purpose), which signals to surface,
    and how often. One row per lab, auto-created via ``post_save`` on Lab so a
    lab always has sensible defaults even before onboarding sets its watch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab = models.OneToOneField(
        Lab,
        on_delete=models.CASCADE,
        related_name="watch",
    )
    topics = models.JSONField(
        default=list,
        blank=True,
        help_text="Research areas/keywords Mylo monitors for the lab.",
    )
    categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Signal kinds to surface: papers, grants, conferences, etc.",
    )
    cadence = models.CharField(
        max_length=20,
        choices=WatchCadence.choices,
        default=WatchCadence.DAILY,
        help_text="How often Mylo posts to the lab's Discord channel.",
    )
    # The lab's timeline defaults (plan M2). The hour and zone stay on ``Lab``:
    # they were already there for reminders, and two places to set "when the lab's
    # morning is" would disagree within a release.
    deadline_buffer_days = _buffer_field("this lab")
    min_paper_window_days = _window_field("this lab")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"LabWatchPreference<{self.lab}>"


class LabInvitation(models.Model):
    """A PI/manager's invitation for a person to join a lab.

    The target is resolved from an email or username at invite time. An email
    with no matching account yet stays a *pending email* invite (``invitee``
    null); it is claimed onto the account when that person signs up with the same
    email (``claim_pending_invitations``). Accepting creates a
    :class:`LabMembership` in addition to the invitee's existing account. Reject
    is a definitive decline; ignore silently dismisses it from the invitee's feed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        IGNORED = "ignored", "Ignored"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab = models.ForeignKey(
        Lab,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_lab_invitations",
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="lab_invitations",
        help_text="Resolved recipient; null until a pending email invite is claimed.",
    )
    invited_email = models.EmailField(
        blank=True,
        default="",
        help_text="Normalized email the invite was addressed to (for pending invites).",
    )
    invited_username = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Username the invite was addressed to (audit/display).",
    )
    role = models.CharField(
        max_length=20,
        choices=LabMembership.Role.choices,
        default=LabMembership.Role.MEMBER,
        help_text="Membership role granted on accept.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most one live invite per person per lab, and per pending email.
            models.UniqueConstraint(
                fields=["lab", "invitee"],
                condition=models.Q(status="pending", invitee__isnull=False),
                name="accounts_unique_pending_lab_invite_user",
            ),
            models.UniqueConstraint(
                fields=["lab", "invited_email"],
                condition=models.Q(status="pending") & ~models.Q(invited_email=""),
                name="accounts_unique_pending_lab_invite_email",
            ),
            # An invite must target either a resolved user or an email.
            models.CheckConstraint(
                condition=models.Q(invitee__isnull=False) | ~models.Q(invited_email=""),
                name="accounts_lab_invite_has_target",
            ),
        ]

    def __str__(self) -> str:
        who = self.invitee or self.invited_email or self.invited_username
        return f"Invite<{who} -> {self.lab} ({self.status})>"


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"


class EmailVerification(models.Model):
    """An outstanding proof that someone controls an email address.

    One row per issued code, covering the three flows that need the proof:
    confirming the address a new account signed up with, confirming an address a
    signed-in user is moving to, and authorising a password change from inside
    the app. The pending address lives on the row rather than on ``User``, so a
    change only touches the account once the new mailbox has answered — a typo'd
    address can never lock anyone out of their own account.

    ``purpose`` is load-bearing, not a label: a code is looked up by purpose, so
    one issued to confirm an address can never be spent to change a password.

    The code itself is never stored. A six-digit code has a million-wide space,
    which a plain digest surrenders instantly to an offline sweep, so what is
    persisted is a ``SECRET_KEY``-keyed HMAC salted with this row's id. Online
    guessing is bounded separately by ``attempts`` and ``expires_at``.
    """

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Sign-up confirmation"
        CHANGE = "change", "Email change"
        PASSWORD = "password", "Password change"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )
    email = models.EmailField(
        help_text="The address being proved — for a change, the new one.",
    )
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.SIGNUP,
    )
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "purpose", "consumed_at"],
                name="accounts_emailver_lookup",
            ),
        ]

    def __str__(self) -> str:
        return f"EmailVerification<{self.email} ({self.purpose})>"


class OrgInvite(models.Model):
    """A way in to a lab or department for someone who may have no account yet.

    Two shapes of the same thing, distinguished by :class:`Kind`. An **email**
    invite is addressed to one mailbox: the link is mailed there and can only be
    spent by someone registering (or signed in) with that exact address, which is
    what makes it the tighter of the two. A **link** invite is handed out by the
    creator to whoever they like, bounded instead by a usage budget and a clock.

    This is deliberately not :class:`LabInvitation`. That one addresses a person
    Mycelium already knows and lands in their in-app notifications; this one leaves
    the building, works for departments too, and is the only invitation that puts
    Mycelium's name in a stranger's inbox.

    The token is stored in the clear, unlike a password-reset token. The two are
    not the same kind of secret: a reset token buys an account, is spent once, and
    is never shown again, whereas a share link exists to be re-copied by the person
    who made it and buys nothing but membership of one org. It is revocable,
    expiring, use-capped, and readable only by managers who can already add members
    directly — so hashing it would cost the feature its point and buy very little.
    """

    class Kind(models.TextChoices):
        EMAIL = "email", "Emailed to one address"
        LINK = "link", "Shareable link"

    class Role(models.TextChoices):
        """The four membership roles both org types share."""

        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab = models.ForeignKey(
        Lab,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="join_invites",
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="join_invites",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
        help_text="Membership role granted when the invite is redeemed.",
    )
    email = models.EmailField(
        blank=True,
        default="",
        help_text="Lower-cased address an email invite is bound to; blank for a link.",
    )
    message = models.TextField(
        blank=True,
        default="",
        help_text="Optional note from the creator, shown in the email and on the page.",
    )
    token = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_org_invites",
    )
    max_uses = models.PositiveIntegerField(
        default=1,
        help_text="How many accounts may join through this invite. Always 1 for email.",
    )
    used_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Exactly one org. A row with neither has nothing to join; a row with
            # both would silently grant membership of something nobody named.
            models.CheckConstraint(
                condition=(
                    models.Q(lab__isnull=False, department__isnull=True)
                    | models.Q(lab__isnull=True, department__isnull=False)
                ),
                name="accounts_org_invite_one_org",
            ),
            # An email invite must carry the address it is bound to, or the binding
            # that makes it the secure option quietly is not there.
            models.CheckConstraint(
                condition=~models.Q(kind="email") | ~models.Q(email=""),
                name="accounts_org_invite_email_has_address",
            ),
        ]
        indexes = [
            models.Index(fields=["token"], name="accounts_orginvite_token"),
        ]

    def __str__(self) -> str:
        return f"OrgInvite<{self.kind} -> {self.org_name}>"

    @property
    def org(self):
        """The lab or department this invite joins."""
        return self.lab or self.department

    @property
    def org_kind(self) -> str:
        return "lab" if self.lab_id else "department"

    @property
    def org_name(self) -> str:
        org = self.org
        return org.name if org else ""

    @property
    def uses_left(self) -> int:
        return max(self.max_uses - self.used_count, 0)


class OrgInviteRedemption(models.Model):
    """One account's use of one invite — the roster of who came in through it.

    Unique per (invite, user) so a person re-following their own link rejoins
    idempotently instead of spending another seat off the budget.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invite = models.ForeignKey(
        OrgInvite,
        on_delete=models.CASCADE,
        related_name="redemptions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_invite_redemptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["invite", "user"],
                name="accounts_unique_org_invite_redemption",
            ),
        ]

    def __str__(self) -> str:
        return f"Redemption<{self.user} via {self.invite_id}>"


class AuthorWork(models.Model):
    """One of a person's own published works, kept rather than reduced (plan M9).

    The author import reads up to a few dozen recent works from OpenAlex, Semantic
    Scholar or Scholar, extracts research areas and keywords out of them, and
    throws the works away. That was right while the only question was "what does
    this person work on". It is wrong for every question a project-aware report
    asks: whether a paper Mylo just found is one the reader *wrote*, whether it
    revises one of theirs, and which of their own results a claim sits against.

    So the works are kept — title, year, identifiers, abstract, coauthors — and
    the known-literature matcher reads them alongside the reader's collections.
    Surfacing someone their own paper as news is the single most credibility-
    destroying thing a research feed can do, and it is entirely avoidable.

    Keyed on ``(user, source, source_id)``: re-importing the same author updates
    each work in place rather than accumulating duplicates across runs. A work
    whose source gave no stable id is still stored, keyed on a hash of its title,
    because a title is what the matcher compares anyway.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="author_works",
    )
    source = models.CharField(
        max_length=40,
        help_text="Which import produced it: openalex / semantic / scholar.",
    )
    source_id = models.CharField(
        max_length=200,
        help_text="The source's own work id, or a hash of the title when it gave none.",
    )
    title = models.CharField(max_length=500, blank=True, default="")
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    doi = models.CharField(max_length=200, blank=True, default="")
    abstract = models.TextField(blank=True, default="")
    coauthors = models.JSONField(default=list, blank=True)
    # Co-authors by identity, where the source gives one (OpenAlex author ids).
    # Names alone cannot answer "does the seeker already work with this person"
    # — two people share a name, one person spells theirs three ways.
    coauthor_ids = models.JSONField(default=list, blank=True)
    cited_by = models.PositiveIntegerField(null=True, blank=True)
    # The OpenAlex field of the work's primary topic ("17" is Computer
    # Science), used only to measure distance between fields — never shown as a
    # label. Blank until known; ``field_checked_at`` records that a DOI lookup
    # was tried, so a work OpenAlex does not know is not looked up every night.
    openalex_field_id = models.CharField(max_length=32, blank=True, default="")
    field_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "source_id"],
                name="accounts_authorwork_unique_source_id",
            ),
        ]
        indexes = [models.Index(fields=["user", "year"])]

    def __str__(self) -> str:
        return f"{self.title[:60]} ({self.year or '—'})"
