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
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Other names people use for this project in conversation — "
            "'the imaging pipeline', 'IMG-seg'. Maintained by a project editor "
            "and read by ambient attribution (apps.ambient.attribution), where "
            "a name or alias in a message is the strongest single signal of "
            "which project it is about."
        ),
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


class ProjectState(models.Model):
    """What a project claims, what blocks it, and what is due when (plan M5).

    One row per :class:`Project`. The shape and its rules live in
    :mod:`apps.research.state`; this is the storage, and it is deliberately three
    JSON columns plus four scalars rather than thirty columns. The state is
    written by a wizard, an extractor and an API, all of which produce partial
    answers, and a table that demands every column be decided before any of it can
    be saved collects nothing at all.

    ``slow_fingerprint`` is the load-bearing scalar. Model-written project
    write-ups record the fingerprint they were written against and invalidate on
    it, so moving a milestone costs nothing and changing the claimed contribution
    costs a refresh. It is maintained here rather than by the caller, because a
    caller that forgets is a caller that silently serves stale reasoning.

    ``confirmed_at`` is the last time a person said "yes, this is still true". The
    weekly reports how long ago that was and proposes a review past thirty days:
    project state that nobody has looked at in two months is the most dangerous
    input the reports have, because it reads as current.
    """

    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name="state",
    )
    slow = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "The research identity: problem, claimed_contribution, method, "
            "planned_components, data, blockers. Changing it invalidates "
            "model-written project write-ups."
        ),
    )
    fast = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Operational state: stage, milestones, venue_targets, constraints, "
            "timeline_overrides, needs, known_literature, exclusions. Read by the "
            "deterministic matchers, which cost nothing to re-run."
        ),
    )
    provenance = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "{field: stated|inferred}. A stated field is never auto-edited; an "
            "inferred one is a proposal until someone accepts it."
        ),
    )
    state_version = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Bumped on every save — the reader-visible 'this changed' signal. "
            "Zero means the row exists but nothing has been written to it, which "
            "is a real state: a project asked but not yet answered."
        ),
    )
    slow_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Hash of the slow half alone; write-ups invalidate on it.",
    )
    confirmed_at = models.DateField(
        null=True,
        blank=True,
        help_text="Last time a person confirmed this state is still true.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_states_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def apply(self, payload: dict, *, actor=None) -> "ProjectState":
        """Merge a (possibly partial) payload in, normalising and refingerprinting.

        Partial by design: the wizard answers five questions, the extractor fills
        what a document actually said, and the state panel edits one section. Each
        writes what it knows and leaves the rest alone, so ``slow`` and ``fast``
        are merged key by key rather than replaced wholesale — a PATCH that sent
        only ``fast`` must not erase the research identity.
        """
        from apps.research import state as schema

        payload = payload if isinstance(payload, dict) else {}
        merged = {
            "slow": {**(self.slow or {}), **(payload.get("slow") or {})},
            "fast": {**(self.fast or {}), **(payload.get("fast") or {})},
            "provenance": {
                **(self.provenance or {}),
                **(payload.get("provenance") or {}),
            },
        }
        normalised = schema.normalise_state(merged)
        self.slow = normalised["slow"]
        self.fast = normalised["fast"]
        self.provenance = normalised["provenance"]
        self.slow_fingerprint = schema.slow_fingerprint(self.slow)
        self.state_version = (self.state_version or 0) + 1
        if actor is not None:
            self.updated_by = actor
        return self

    @property
    def is_empty(self) -> bool:
        from apps.research import state as schema

        return schema.is_empty({"slow": self.slow, "fast": self.fast})

    def days_since_confirmed(self, today=None) -> int | None:
        """How stale this state is, or ``None`` when it was never confirmed.

        ``None`` and ``0`` are different answers and both are shown: "never
        confirmed" is a prompt, "confirmed today" is reassurance.
        """
        if self.confirmed_at is None:
            return None
        from django.utils import timezone

        return ((today or timezone.localdate()) - self.confirmed_at).days

    def __str__(self) -> str:
        return f"ProjectState<{self.project}> v{self.state_version}"
