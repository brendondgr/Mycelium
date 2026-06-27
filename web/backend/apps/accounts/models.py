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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


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
