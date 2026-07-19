import uuid

from django.conf import settings
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
    (briefing §3 USER); ``interests`` and ``embedding`` are the interest
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
    """How often Mylo surfaces what it is watching for a user."""

    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"


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
        default=WatchCadence.WEEKLY,
    )
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
        default=WatchCadence.WEEKLY,
    )
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
                condition=models.Q(invitee__isnull=False)
                | ~models.Q(invited_email=""),
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
