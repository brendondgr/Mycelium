import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.db import exactly_one, validate_exactly_one

SCOPE_FIELDS = ("scope_user", "scope_lab", "scope_department")


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
