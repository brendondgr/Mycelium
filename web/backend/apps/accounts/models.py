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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile<{self.user}>"


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
