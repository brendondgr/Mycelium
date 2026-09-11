import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField

from apps.core.db import exactly_one, validate_exactly_one

SCOPE_FIELDS = ("scope_user", "scope_lab", "scope_department")

# Membership roles that count as a "head" of a lab or department — the people
# who get cascade visibility into the org's projects (briefing §4, §5).
HEAD_ROLES = ("owner", "admin")


class ProjectQuerySet(models.QuerySet):
    """Visibility queries over the lab/department hierarchy.

    Who can see a project (user's verbal spec, 2026-06-21):

    * Anyone *involved* in the project — its members or its personal owner.
    * For a **lab** project — the *heads* of that lab (a lead PI, or an
      owner/admin member).
    * For a lab project — the *heads* of the department that lab belongs to.
      A department head therefore always sees every project of every lab
      under them ("if a lab is part of a project, the department will always
      be able to see it").
    * For a **department** project — the *heads* of that department.

    "Lab/department can see it" means the *heads*, not every member — only
    explicit project members get visibility from the rank-and-file side.
    """

    def active(self) -> "ProjectQuerySet":
        """Non-archived projects — the ones that still get scored / counted.

        Archiving a project keeps its row and its already-stored recommendations
        readable but stops any new search work; it also frees a slot against the
        owner's plan cap. Every cap count and every scoring fan-out reads through
        here so an archived project never consumes budget.
        """
        return self.filter(is_archived=False)

    def visible_to(self, user) -> "ProjectQuerySet":
        if not getattr(user, "is_authenticated", False):
            return self.none()

        # Imported lazily to avoid an import cycle at app-load time.
        from apps.accounts.models import (
            Department,
            DeptMembership,
            Lab,
            LabMembership,
        )

        lab_head_ids = (
            LabMembership.objects.filter(user=user)
            .filter(Q(is_lead=True) | Q(role__in=HEAD_ROLES))
            .values_list("lab_id", flat=True)
        )

        head_dept_ids = set(
            Department.objects.filter(owner=user).values_list("id", flat=True)
        ) | set(
            DeptMembership.objects.filter(user=user, role__in=HEAD_ROLES).values_list(
                "department_id", flat=True
            )
        )

        labs_under_head_depts = Lab.objects.filter(
            department_id__in=head_dept_ids
        ).values_list("id", flat=True)

        return self.filter(
            Q(members=user)
            | Q(scope_user=user)
            | Q(scope_lab_id__in=lab_head_ids)
            | Q(scope_lab_id__in=labs_under_head_depts)
            | Q(scope_department_id__in=head_dept_ids)
        ).distinct()


class Project(models.Model):
    """A unit of research the relevance engine scores against (briefing §3, §6).

    Polymorphic owner: a project is scoped to exactly one of a User (personal
    project), a Lab, or a Department, enforced by a database check constraint.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="personal_projects",
    )
    scope_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    scope_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=200)
    goals = models.JSONField(
        default=dict,
        blank=True,
        help_text="Goals, methods, datasets, deadlines, strategic needs.",
    )
    embedding = VectorField(
        null=True,
        blank=True,
        help_text="Derived from goals; the project relevance target.",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMember",
        related_name="projects",
        blank=True,
    )
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "An archived project keeps its stored recommendations visible but "
            "stops getting new ones and frees a slot against the plan cap."
        ),
    )
    share_in_lab_reports = models.BooleanField(
        default=False,
        help_text=(
            "Show this project in the lab's shared surfaces — its Discord "
            "channel post and the lab report PDF. Off by default: a lab report "
            "is readable by every lab member and posted to a channel, while "
            "project visibility (see ProjectQuerySet.visible_to) is narrower "
            "than that, so an unshared project's name and matches stay out of "
            "both. Members still see their own projects in their own reports."
        ),
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                name="research_project_one_scope",
                condition=exactly_one(*SCOPE_FIELDS),
            ),
        ]

    def clean(self) -> None:
        validate_exactly_one(self, *SCOPE_FIELDS)

    def is_visible_to(self, user) -> bool:
        """Whether ``user`` can see this project under the cascade rules."""
        return Project.objects.filter(pk=self.pk).visible_to(user).exists()

    @property
    def scope(self) -> str:
        """Derived discriminator: ``user`` / ``lab`` / ``department``."""
        if self.scope_user_id is not None:
            return "user"
        if self.scope_lab_id is not None:
            return "lab"
        return "department"

    @property
    def scope_target(self):
        return self.scope_user or self.scope_lab or self.scope_department

    def __str__(self) -> str:
        return self.name


class ProjectInvitation(models.Model):
    """An invitation for someone to join a project.

    Projects gained two different ways onto a roster, deliberately:

    * A lab's owner, admin, or PI **adds** one of that lab's own members to one of
      the lab's projects directly — no invitation, because that person can already
      see the lab's work (``ProjectMembersView.post``).
    * Everyone else is **invited** and has to accept: any collaborator on a
      personal project, and anyone outside the lab on a lab project.

    Accepting creates a :class:`ProjectMember` and nothing else. It never grants
    lab membership, so an outside collaborator sees exactly the one project they
    were invited to — its feed, collections, and recommendations — and no other
    part of the lab.

    Unlike a lab invitation, this targets an existing account only: a project is a
    working surface, not a front door, and sign-up stays the lab's invite path.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        IGNORED = "ignored", "Ignored"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_project_invitations",
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_invitations",
    )
    message = models.TextField(
        blank=True,
        default="",
        help_text="Optional note from the inviter, shown with the invitation.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most one live invitation per person per project.
            models.UniqueConstraint(
                fields=["project", "invitee"],
                condition=Q(status="pending"),
                name="research_unique_pending_project_invite",
            ),
        ]

    def __str__(self) -> str:
        return f"Invite<{self.invitee} -> {self.project} ({self.status})>"


class ProjectMember(models.Model):
    """Join between users and the projects they participate in (briefing §3)."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="research_unique_project_member",
            ),
        ]
        ordering = ["project__name", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} in {self.project}"
