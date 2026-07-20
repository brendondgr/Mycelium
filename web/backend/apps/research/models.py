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
