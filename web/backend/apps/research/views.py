import logging
from collections import OrderedDict

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from tools.delivery.collaboration import (
    mark_seen,
    project_seen_map,
    record_event,
    share_to_project,
)
from tools.delivery.fanout import trigger_fanout
from tools.delivery.models import (
    Collection,
    CollectionItem,
    ProjectItemSeen,
    ProjectShare,
)
from tools.recommendation.models import ProjectProfile, RelevanceEvent
from tools.recommendation.team_profile import recompute_project_profile
from tools.retrieval.models import ContentItem

from apps.accounts.models import Department, Lab, LabMembership
from apps.accounts.permissions import (
    user_has_department_access,
    user_has_lab_access,
)
from apps.accounts.services import record_audit_event
from apps.core.people import display_name, initials

from . import visibility as scope
from .limits import (
    ScopeCap,
    department_scope_cap,
    in_cap_ids,
    lab_scope_cap,
    personal_scope_cap,
)
from .models import Project, ProjectInvitation, ProjectJoinRequest, ProjectMember
from .permissions import (
    user_can_change_visibility,
    user_can_create_in_scope,
    user_can_edit_project,
    user_can_invite_outside,
    user_can_request_to_join,
)
from .serializers import (
    ProjectCreateSerializer,
    ProjectDirectorySerializer,
    ProjectInvitationSerializer,
    ProjectJoinRequestSerializer,
    ProjectNameOnlySerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)

logger = logging.getLogger(__name__)


def _over_cap_ids(projects) -> set:
    """The ids among ``projects`` that sit beyond their owner's active plan cap.

    Groups the active projects by scope owner, computes each owner's in-cap set
    (oldest-first, :func:`in_cap_ids`), and returns the active ids that fall
    outside it — the ones a downgrade pushed over the limit. Archived projects are
    ignored (they already don't consume budget).
    """
    by_owner: dict[tuple[str, object], list] = {}
    for project in projects:
        if project.is_archived:
            continue
        if project.scope_user_id is not None:
            key = ("scope_user", project.scope_user_id)
        elif project.scope_lab_id is not None:
            key = ("scope_lab", project.scope_lab_id)
        elif project.scope_department_id is not None:
            key = ("scope_department", project.scope_department_id)
        else:
            continue
        by_owner.setdefault(key, []).append(project)

    over: set = set()
    for (field, owner_id), group in by_owner.items():
        cap = _cap_for(field, owner_id)
        keep = in_cap_ids(field, owner_id, cap)
        over |= {p.id for p in group if p.id not in keep}
    return over


_SCOPE_NOUN = {"user": "account", "lab": "lab", "department": "department"}


def _cap_for(scope_field: str, owner_id) -> int | None:
    """The numeric active-project cap for one resolved scope owner."""
    if scope_field == "scope_user":
        return personal_scope_cap(User.objects.get(pk=owner_id)).cap
    if scope_field == "scope_lab":
        return lab_scope_cap(Lab.objects.get(pk=owner_id)).cap
    return department_scope_cap(Department.objects.get(pk=owner_id)).cap


def _maybe_recompute_team(project: "Project") -> None:
    """Refresh a project's team signal after a membership change (Feature D).

    Inline and best-effort — a recompute failure must never block join/leave/add.
    Uses stored member vectors only (no on-demand embedding) to keep the request
    fast; the nightly task / command does the fuller recompute.
    """
    from django.conf import settings

    if not settings.TEAM_PROFILE_AUTORECOMPUTE:
        return
    try:
        recompute_project_profile(
            project,
            reason=ProjectProfile.Reason.MEMBERSHIP_CHANGE,
            embed_missing=False,
        )
    except Exception:  # pragma: no cover - defensive; membership already changed
        logger.warning(
            "team-profile recompute failed for project %s", project.id, exc_info=True
        )


class ProjectListView(ListCreateAPIView):
    """List the projects the caller may see, or create a new one.

    Visibility is delegated to ``Project.objects.visible_to`` (members, personal
    owners, lab heads, and department heads). An optional ``?lab=<slug>`` filter
    narrows to a single lab's projects — the switcher's scope — and never widens
    visibility beyond what the caller could already see.

    ``POST`` creates a project scoped to a lab (``lab`` slug) or a department
    (``department`` id) — allowed by that scope's *Who can create projects*
    setting, any member by default — or, with neither, a personal project
    scoped to the caller. The creator of a lab or department project becomes
    its owner; ``visibility`` (default ``invite_only``) must be one the scope
    can take. The active-project cap is still the lab's (or department's).
    """

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        qs = (
            Project.objects.visible_to(self.request.user)
            .select_related("scope_lab", "scope_department", "scope_user")
            .prefetch_related("members", "memberships__user")
        )
        lab_slug = self.request.query_params.get("lab", "").strip()
        if lab_slug:
            qs = scope.visible_in_lab_slug(qs, lab_slug)
        return qs

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        # Only meaningful for the read (list) side; the create serializer ignores it.
        if self.request.method == "GET":
            context["over_cap_ids"] = _over_cap_ids(list(self.get_queryset()))
        return context

    def perform_create(self, serializer: ProjectCreateSerializer) -> None:
        data = serializer.validated_data
        lab_slug = (data.pop("lab", "") or "").strip()
        dept_slug = (data.pop("department", "") or "").strip()
        focus = data.pop("focus", None)
        wanted_scope = data.pop("visibility", None)
        user = self.request.user

        # Resolve the scope, check the manage permission, and enforce the plan cap
        # atomically: the count-then-create runs under a row lock on the scope
        # owner so two concurrent creates can't both slip past the last slot.
        if lab_slug and dept_slug:
            raise ValidationError(
                "A project belongs to a lab OR a department, not both."
            )

        with transaction.atomic():
            if lab_slug:
                lab = get_object_or_404(
                    Lab.objects.select_for_update(), slug=lab_slug
                )
                if not user_can_create_in_scope(user, lab=lab):
                    raise PermissionDenied(
                        "Only the lab's PI, owner or admins can start projects in "
                        "this lab."
                    )
                self._enforce_cap(lab_scope_cap(lab))
                save_kwargs = {"scope_lab": lab}
                target = {"scope": "lab", "lab_id": str(lab.id)}
            elif dept_slug:
                department = get_object_or_404(
                    Department.objects.select_for_update(), pk=dept_slug
                )
                if not user_can_create_in_scope(user, department=department):
                    raise PermissionDenied(
                        "Only the department's owner or admins can start projects "
                        "in it."
                    )
                self._enforce_cap(department_scope_cap(department))
                save_kwargs = {"scope_department": department}
                target = {"scope": "department", "department_id": str(department.id)}
            else:
                User.objects.select_for_update().get(pk=user.pk)
                self._enforce_cap(personal_scope_cap(user))
                save_kwargs = {"scope_user": user}
                target = {"scope": "user"}

            if wanted_scope:
                allowed = scope.allowed_visibilities(Project(**save_kwargs))
                if wanted_scope not in allowed:
                    raise ValidationError(
                        {
                            "visibility": [
                                f"This project cannot be scoped to {wanted_scope!r}."
                            ]
                        }
                    )
                save_kwargs["visibility"] = wanted_scope
            if focus is not None:
                from .serializers import apply_focus

                data["goals"] = apply_focus(data.get("goals") or {}, focus)
            project = serializer.save(**save_kwargs)
            if project.scope_user_id is None:
                # The creator owns a lab or department project. A personal
                # project's owner is its scope_user already.
                ProjectMember.objects.create(
                    project=project, user=user, role=ProjectMember.Role.OWNER
                )

        record_audit_event(
            actor=user,
            action="project.create",
            target_type="project",
            target_id=str(project.id),
            metadata={
                "name": project.name,
                "visibility": project.visibility,
                **target,
            },
        )
        # Seed the new project's recommendations over the existing corpus (Phase 6
        # wires the background task; a no-op stub keeps creation working until then).
        _seed_project(project)

    @staticmethod
    def _enforce_cap(cap: ScopeCap) -> None:
        if not cap.has_headroom:
            raise PermissionDenied(
                {
                    "detail": (
                        f"This {_SCOPE_NOUN.get(cap.scope, cap.scope)} has reached "
                        f"its limit of {cap.cap} active projects. Archive one to "
                        "add another; an administrator can raise the limit."
                    ),
                    "code": "project_cap_reached",
                    "scope": cap.scope,
                    "cap": cap.cap,
                    "active": cap.active,
                }
            )


def _seed_project(project: "Project") -> None:
    """Kick off initial recommendation seeding for a just-created project.

    Phase 6 replaces this with a background ``seed_project_recommendations`` task
    (whole-corpus refit + a "researching…" flag). Kept as a best-effort no-op stub
    now so creation is fully wired end-to-end without waiting on that phase.
    """
    try:
        from tools.recommendation.tasks import enqueue_project_seed

        enqueue_project_seed(project)
    except Exception:  # pragma: no cover - seeding is best-effort, never blocks create
        logger.warning("project seed enqueue failed for %s", project.id, exc_info=True)


class LabProjectsView(ListAPIView):
    """The projects of one lab that the caller may see.

    Narrowed to :meth:`ProjectQuerySet.visible_to`: a rank-and-file member gets
    only the projects they belong to, while the lab's PI, owner and admins (and a
    department head over the lab) get every project, as they do everywhere else.
    It used to return every project — goals and full roster — to any lab member,
    which made each project's own visibility rule meaningless. Each row carries
    ``is_member`` so the UI can offer Leave.
    """

    serializer_class = ProjectSerializer

    def get_queryset(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_has_lab_access(self.request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        return (
            scope.visible_in_lab(self.request.user, lab)
            .select_related("scope_lab")
            .prefetch_related("members", "memberships__user")
        )


class DepartmentProjectsView(APIView):
    """A department's projects and its labs' projects, as the caller may see them.

    ``projects``: full rows for everything the caller may open — for a
    department head, every department project and every project of a lab that
    shows its department *Everything*. ``names_only``: for a department head,
    the reduced row (name, owner, member count, scope) of each project in a lab
    whose PI set *Names only*. Nobody gets the reduced rows for a lab they can
    already open.
    """

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, pk=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        visible = (
            scope.department_projects_visible(request.user, department)
            .select_related("scope_lab", "scope_department", "scope_user")
            .prefetch_related("members", "memberships__user")
        )
        names_only = scope.names_only_for(request.user, department).select_related(
            "scope_lab"
        )
        return Response(
            {
                "projects": ProjectSerializer(
                    visible, many=True, context={"request": request}
                ).data,
                "names_only": ProjectNameOnlySerializer(names_only, many=True).data,
            }
        )


# --------------------------------------------------------------------------- #
# The directory — projects the caller can see exist but is not on.
# --------------------------------------------------------------------------- #


def _directory_response(request: Request, queryset) -> Response:
    """Directory rows (reduced: name, focus line, owner, member count, scope)."""
    rows = list(
        queryset.select_related(
            "scope_lab", "scope_department", "scope_user"
        ).prefetch_related("memberships__user")
    )
    ids = [row.id for row in rows]
    pending = set(
        ProjectJoinRequest.objects.filter(
            user=request.user,
            project_id__in=ids,
            state=ProjectJoinRequest.State.PENDING,
        ).values_list("project_id", flat=True)
    )
    data = ProjectDirectorySerializer(
        rows,
        many=True,
        context={
            "request": request,
            "openable": scope.openable_ids(request.user, ids),
            "pending": pending,
        },
    ).data
    return Response({"count": len(data), "items": data})


class ProjectDirectoryView(APIView):
    """Every project on the instance the caller can see exists but is not on:
    their labs' and departments' scoped projects, and ``public`` ones (for a
    verified account). Reduced rows only."""

    def get(self, request: Request) -> Response:
        return _directory_response(request, scope.directory(request.user))


class LabProjectDirectoryView(APIView):
    """"Projects in this lab": the lab's projects the caller can see but is not
    on. Lab members only — an outside collaborator on one project gets no
    directory of the lab."""

    def get(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        return _directory_response(request, scope.directory(request.user, lab=lab))


class DepartmentProjectDirectoryView(APIView):
    """"Projects in this department": the department's projects and its labs'
    that the caller can see but is not on. Effective members only."""

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, pk=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        return _directory_response(
            request, scope.directory(request.user, department=department)
        )


# --------------------------------------------------------------------------- #
# Join requests — the "ask" half of membership (the other is an invitation).
# --------------------------------------------------------------------------- #


def _join_request_qs():
    return ProjectJoinRequest.objects.select_related(
        "project", "user", "decided_by"
    )


def _tell_requester(join_request: ProjectJoinRequest) -> None:
    """Put the decision on the requester's bell — theirs alone; a refusal is
    never announced to the lab. Best-effort: the decision already stands."""
    from tools.delivery.models import Notification

    approved = join_request.state == ProjectJoinRequest.State.APPROVED
    title = (
        f"You're on {join_request.project.name} now"
        if approved
        else f"Your request to join {join_request.project.name} was declined"
    )
    try:
        Notification.objects.get_or_create(
            dedupe_key=f"project-join:{join_request.id}:{join_request.state}",
            defaults={
                "user": join_request.user,
                "kind": Notification.Kind.PROJECT_JOIN,
                "title": title,
                "body": (
                    "It is in your projects."
                    if approved
                    else "Only you were told. You can ask again later."
                ),
            },
        )
    except Exception:  # pragma: no cover - the bell is a courtesy
        logger.warning(
            "join-request notification failed for %s", join_request.id, exc_info=True
        )


class ProjectJoinRequestsView(APIView):
    """``POST``: ask to join a project you can see but are not on. ``GET``: the
    open requests, for the people who decide (owner, editors, the scope's
    managers).

    A request is possible only when the project is not ``invite_only`` and the
    caller can see it exists. Someone who cannot see it gets the same 404 as
    an id that names nothing.
    """

    def get(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot decide this project's join requests.")
        rows = _join_request_qs().filter(
            project=project, state=ProjectJoinRequest.State.PENDING
        )
        data = ProjectJoinRequestSerializer(rows, many=True).data
        return Response({"count": len(data), "items": data})

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(
            Project.objects.select_related("scope_lab", "scope_department"), pk=pk
        )
        if not scope.can_see(request.user, project):
            raise NotFound("No such project.")
        if scope.is_participant(request.user, project):
            raise ValidationError("You are already on this project.")
        if not user_can_request_to_join(request.user, project):
            raise PermissionDenied(
                "This project is joined by invitation only."
                if not scope.admits_requests(project)
                else "This project is not taking requests."
            )
        if ProjectJoinRequest.objects.filter(
            project=project,
            user=request.user,
            state=ProjectJoinRequest.State.PENDING,
        ).exists():
            raise ValidationError("You already asked to join this project.")
        try:
            with transaction.atomic():
                join_request = ProjectJoinRequest.objects.create(
                    project=project,
                    user=request.user,
                    note=str(request.data.get("note", ""))[:2000],
                )
        except IntegrityError:
            # A double click: the partial unique constraint caught the second.
            raise ValidationError("You already asked to join this project.") from None
        record_audit_event(
            actor=request.user,
            action="project.join_request",
            target_type="project",
            target_id=str(project.id),
            metadata={"request_id": str(join_request.id)},
        )
        return Response(
            ProjectJoinRequestSerializer(join_request).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectJoinRequestDecideView(APIView):
    """The owner or an editor approves or refuses one open request.

    Approval makes the requester a ``member``. A refusal tells the requester
    alone."""

    _ACTIONS = {
        "approve": ProjectJoinRequest.State.APPROVED,
        "refuse": ProjectJoinRequest.State.REFUSED,
    }

    def post(self, request: Request, pk, rid) -> Response:
        project = _visible_project(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot decide this project's join requests.")
        action = str(request.data.get("action", "")).strip().lower()
        if action not in self._ACTIONS:
            raise ValidationError({"action": ["Must be one of: approve, refuse."]})

        created = False
        with transaction.atomic():
            # Lock the row so two deciders (or a decide racing a withdraw)
            # cannot both act on one request.
            join_request = get_object_or_404(
                ProjectJoinRequest.objects.select_for_update(of=("self",)).select_related(
                    "project", "user"
                ),
                pk=rid,
                project=project,
            )
            if join_request.state != ProjectJoinRequest.State.PENDING:
                return Response(
                    {"detail": "This request has already been answered."},
                    status=status.HTTP_409_CONFLICT,
                )
            if action == "approve":
                requester = join_request.user
                # The scope may have narrowed, or the requester left the lab,
                # since they asked: approval still needs them inside the scope.
                if not scope.can_see(requester, project):
                    raise PermissionDenied(
                        "They are no longer inside this project's scope. "
                        "Invite them instead."
                    )
                _, created = ProjectMember.objects.get_or_create(
                    project=project, user=requester
                )
            join_request.state = self._ACTIONS[action]
            join_request.decided_by = request.user
            join_request.decided_at = timezone.now()
            join_request.save(update_fields=["state", "decided_by", "decided_at"])
        record_audit_event(
            actor=request.user,
            action=f"project.join_request.{action}",
            target_type="project",
            target_id=str(project.id),
            metadata={
                "request_id": str(join_request.id),
                "username": join_request.user.get_username(),
            },
        )
        if action == "approve" and created:
            _maybe_recompute_team(project)
        _tell_requester(join_request)
        return Response(ProjectJoinRequestSerializer(join_request).data)


class MyProjectJoinRequestsView(APIView):
    """The bell's join-request rows: ``to_decide`` (open requests on projects
    the caller decides for) and ``mine`` (the caller's own open requests)."""

    def get(self, request: Request) -> Response:
        pending = _join_request_qs().filter(state=ProjectJoinRequest.State.PENDING)
        mine = pending.filter(user=request.user)
        # Candidate projects: ones the caller can open; each is then checked
        # against the one edit rule, so the bell and the team card agree.
        openable = Project.objects.visible_to(request.user).values("id")
        to_decide = [
            row
            for row in pending.filter(project_id__in=openable).exclude(
                user=request.user
            )
            if _user_can_edit(request.user, row.project)
        ]
        return Response(
            {
                "to_decide": ProjectJoinRequestSerializer(to_decide, many=True).data,
                "mine": ProjectJoinRequestSerializer(mine, many=True).data,
            }
        )


class ProjectJoinRequestWithdrawView(APIView):
    """The requester withdraws their own open request."""

    def post(self, request: Request, rid) -> Response:
        with transaction.atomic():
            join_request = get_object_or_404(
                ProjectJoinRequest.objects.select_for_update(of=("self",)).select_related(
                    "project", "user"
                ),
                pk=rid,
            )
            if join_request.user_id != request.user.id:
                raise NotFound("No such request.")
            if join_request.state != ProjectJoinRequest.State.PENDING:
                return Response(
                    {"detail": "This request has already been answered."},
                    status=status.HTTP_409_CONFLICT,
                )
            join_request.state = ProjectJoinRequest.State.WITHDRAWN
            join_request.decided_at = timezone.now()
            join_request.save(update_fields=["state", "decided_at"])
        return Response(ProjectJoinRequestSerializer(join_request).data)


#: Kept under its old name for the call sites below; the rule lives in
#: apps.research.permissions so the Mylo agent's gate and these views share it.
_user_can_edit = user_can_edit_project


class ProjectDetailView(APIView):
    """Read one project (any viewer) or edit its name / research focus (managers)."""

    def _get_visible(self, request, pk) -> Project:
        project = get_object_or_404(
            Project.objects.select_related(
                "scope_lab", "scope_department", "scope_user"
            ).prefetch_related("members"),
            pk=pk,
        )
        _require_open(request.user, project)
        return project

    def _context(self, request, project) -> dict:
        return {"request": request, "over_cap_ids": _over_cap_ids([project])}

    def get(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        return Response(
            ProjectSerializer(project, context=self._context(request, project)).data
        )

    @staticmethod
    def _search_surface(project: Project) -> tuple:
        """What this project searches on — the seed's only real input.

        A whole-corpus re-seed is only warranted when this changes. The editor
        sends the whole form on every save, so keying off "was `focus` in the
        body?" would refit the corpus every time someone fixed a typo in the
        project's name.
        """
        from tools.recommendation.targets import (
            project_interests,
            project_watch_categories,
            project_watch_topics,
        )

        interests = project_interests(project)
        return (
            tuple(interests["areas"]),
            tuple(interests["keywords"]),
            interests["statement"],
            tuple(project_watch_topics(project)),
            tuple(project_watch_categories(project)),
        )

    def patch(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot edit this project.")
        new_scope = getattr(request.data, "get", lambda _key: None)("visibility")
        old_scope = project.visibility
        if (
            new_scope is not None
            and new_scope != old_scope
            and not user_can_change_visibility(request.user, project)
        ):
            raise PermissionDenied("Only the project's owner can change who sees it.")
        before = self._search_surface(project)
        serializer = ProjectUpdateSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit_event(
            actor=request.user,
            action="project.update",
            target_type="project",
            target_id=str(project.id),
            metadata={"name": project.name},
        )
        scope_change = {}
        if project.visibility != old_scope:
            from . import lifecycle

            record_audit_event(
                actor=request.user,
                action="project.visibility",
                target_type="project",
                target_id=str(project.id),
                metadata={"from": old_scope, "to": project.visibility},
            )
            # Widening tells every member; narrowing takes effect on everything
            # not yet sent, which every read already re-checks (Phase 5).
            scope_change = lifecycle.scope_changed(
                project, old_scope, actor=request.user
            )
        # A focus / category edit changes what the project should match — re-seed
        # over the existing corpus (best-effort) so the feed reflects the change.
        # A rename or a status change does not, and must not cost a refit.
        if self._search_surface(project) != before:
            _seed_project(project)
        context = self._context(request, project)
        payload = ProjectSerializer(project, context=context).data
        if scope_change:
            payload = {**payload, "scope_change": scope_change}
        return Response(payload)


class ProjectArchiveView(APIView):
    """Archive or unarchive a project (its editor only).

    Archiving keeps the project and its already-stored recommendations visible but
    drops it from every scoring path and frees a slot against the plan cap.
    Unarchiving re-checks the cap so a team can't exceed its limit by reviving an
    old project — they must archive another or upgrade first. A project is never
    deleted here.
    """

    def _get_editable(self, request, pk) -> Project:
        project = get_object_or_404(
            Project.objects.select_related(
                "scope_lab", "scope_department", "scope_user"
            ),
            pk=pk,
        )
        _require_open(request.user, project)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot archive this project.")
        return project

    def post(self, request: Request, pk) -> Response:
        """Archive the project."""
        project = self._get_editable(request, pk)
        if not project.is_archived:
            project.is_archived = True
            project.archived_at = timezone.now()
            project.save(update_fields=["is_archived", "archived_at", "updated_at"])
            record_audit_event(
                actor=request.user,
                action="project.archive",
                target_type="project",
                target_id=str(project.id),
                metadata={"name": project.name},
            )
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )

    def delete(self, request: Request, pk) -> Response:
        """Unarchive the project (re-checking the plan cap)."""
        project = self._get_editable(request, pk)
        if project.is_archived:
            with transaction.atomic():
                cap = _scope_cap_for_project(project, lock=True)
                if not cap.has_headroom:
                    raise PermissionDenied(
                        {
                            "detail": (
                                "Restoring this project would exceed your plan's "
                                f"limit ({cap.cap}). Archive another or upgrade first."
                            ),
                            "code": "project_cap_reached",
                            "scope": cap.scope,
                            "cap": cap.cap,
                            "active": cap.active,
                        }
                    )
                project.is_archived = False
                project.archived_at = None
                project.save(
                    update_fields=["is_archived", "archived_at", "updated_at"]
                )
            record_audit_event(
                actor=request.user,
                action="project.unarchive",
                target_type="project",
                target_id=str(project.id),
                metadata={"name": project.name},
            )
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


def _scope_cap_for_project(project: Project, *, lock: bool = False) -> ScopeCap:
    """The active-project cap for whichever scope owns ``project``.

    ``lock`` takes a row lock on the scope owner so an unarchive's cap check and
    flip run atomically against concurrent creates.
    """
    if project.scope_user_id is not None:
        owner = project.scope_user
        if lock:
            User.objects.select_for_update().get(pk=owner.pk)
        return personal_scope_cap(owner)
    if project.scope_lab_id is not None:
        lab = project.scope_lab
        if lock:
            Lab.objects.select_for_update().get(pk=lab.pk)
        return lab_scope_cap(lab)
    department = project.scope_department
    if lock:
        Department.objects.select_for_update().get(pk=department.pk)
    return department_scope_cap(department)


class ProjectLeaveView(APIView):
    """The caller leaves a project they belong to."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(Project, pk=pk)
        # Only someone who can see the project may learn anything about it. Without
        # this, "leaving" a project you were never on returned its full row —
        # goals and roster — to anyone holding the id.
        if not project.is_visible_to(request.user):
            raise NotFound("No such project.")
        deleted, _ = ProjectMember.objects.filter(
            project=project, user=request.user
        ).delete()
        if deleted:
            record_audit_event(
                actor=request.user,
                action="project.leave",
                target_type="project",
                target_id=str(project.id),
                metadata={"name": project.name},
            )
            _maybe_recompute_team(project)
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


class ProjectMembersView(APIView):
    """Read a project's roster, or add a lab member to a lab project directly.

    The direct add is the "no invitation needed" path: a lab's owner, admin, or PI
    puts one of the lab's own members straight onto one of the lab's projects,
    because that person can already see the lab's work. Everyone else — anyone
    outside the lab, and every personal-project collaborator — arrives through
    :class:`ProjectInvitationsView` and has to accept.
    """

    def get(self, request: Request, pk) -> Response:
        """The current roster, readable by anyone who can see the project."""
        project = _visible_project(request, pk)
        items = ProjectSerializer(context={"request": request}).get_members(project)
        return Response({"count": len(items), "items": items})

    def post(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if project.scope_lab_id is None:
            raise ValidationError("Members can only be added directly to lab projects.")
        if not _user_can_edit(request.user, project):
            raise PermissionDenied(
                "Only the project's owner, its editors, or the lab's PI can add "
                "project members."
            )
        username = str(request.data.get("username", "")).strip()
        if not username:
            raise ValidationError({"username": ["A username is required."]})
        target = get_object_or_404(User, username=username)
        if not LabMembership.objects.filter(
            user=target, lab=project.scope_lab
        ).exists():
            raise ValidationError(
                "That person is not a member of this lab — invite them instead."
            )
        _, created = ProjectMember.objects.get_or_create(
            project=project, user=target
        )
        if created:
            record_audit_event(
                actor=request.user,
                action="project.member_add",
                target_type="project",
                target_id=str(project.id),
                metadata={"username": target.get_username()},
            )
            _maybe_recompute_team(project)
        return Response(
            ProjectSerializer(project, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectMemberDetailView(APIView):
    """Remove one member from a project (its editor only).

    Removing someone drops their `ProjectMember` row, which for a personal-project
    collaborator also drops their visibility of the project. The scope owner can
    never be removed — a personal project's owner and a lab's own projects keep
    their anchor regardless of the roster.
    """

    def delete(self, request: Request, pk, username) -> Response:
        project = _visible_project(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot manage this project's members.")
        target = get_object_or_404(User, username=username)
        if project.scope_user_id == target.id or ProjectMember.objects.filter(
            project=project, user=target, role=ProjectMember.Role.OWNER
        ).exists():
            raise ValidationError("The project's owner cannot be removed from it.")
        deleted, _ = ProjectMember.objects.filter(
            project=project, user=target
        ).delete()
        if deleted:
            record_audit_event(
                actor=request.user,
                action="project.member_remove",
                target_type="project",
                target_id=str(project.id),
                metadata={"username": target.get_username()},
            )
            _maybe_recompute_team(project)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request: Request, pk, username) -> Response:
        """Make a member an editor, or an editor a member — the owner's call.

        Ownership itself is not handed over here (plan Phase 5)."""
        project = _visible_project(request, pk)
        if not user_can_change_visibility(request.user, project):
            raise PermissionDenied("Only the project's owner changes roles.")
        role = str(request.data.get("role", "")).strip()
        if role not in (ProjectMember.Role.EDITOR, ProjectMember.Role.MEMBER):
            raise ValidationError({"role": ["Choose editor or member."]})
        row = get_object_or_404(
            ProjectMember, project=project, user__username=username
        )
        if row.role == ProjectMember.Role.OWNER:
            raise ValidationError("The owner's role is not changed here.")
        if row.role != role:
            before = row.role
            row.role = role
            row.save(update_fields=["role"])
            record_audit_event(
                actor=request.user,
                action="project.member_role",
                target_type="project",
                target_id=str(project.id),
                metadata={"username": username, "from": before, "to": role},
            )
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


# --------------------------------------------------------------------------- #
# Project invitations — the "has to accept" half of member management.
#
# A lab manager adds a lab member straight onto a lab project (no invite needed);
# everyone else is invited here and joins only once they accept. Accepting grants
# a ProjectMember row and nothing more — never lab membership.
# --------------------------------------------------------------------------- #


def _resolve_invitee(identifier: str) -> User:
    """Find the account an invitation is addressed to (username or email).

    Project invitations target existing accounts only: a project is a working
    surface, not a front door. Someone without an account is pointed at the lab
    invitation flow, which does support pending email invites.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        raise ValidationError({"identifier": ["An email or username is required."]})
    if "@" in identifier:
        user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            raise ValidationError(
                {
                    "identifier": [
                        "No Mycelium account uses that email. Invite them to the "
                        "lab first, or ask them to sign up.",
                    ]
                }
            )
        return user
    user = User.objects.filter(username__iexact=identifier).first()
    if user is None:
        raise ValidationError(
            {"identifier": ["No Mycelium user found with that username."]}
        )
    return user


class ProjectInvitationsView(APIView):
    """List a project's invitations, or invite someone to it (editors only)."""

    def get(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot manage this project's invitations.")
        invitations = project.invitations.select_related(
            "project", "project__scope_lab", "project__scope_department",
            "invitee", "inviter",
        ).filter(status=ProjectInvitation.Status.PENDING)
        data = ProjectInvitationSerializer(invitations, many=True).data
        return Response({"count": len(data), "items": data})

    def post(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot invite people to this project.")
        if project.is_archived:
            raise ValidationError("Unarchive this project before inviting people.")

        invitee = _resolve_invitee(str(request.data.get("identifier", "")))
        if ProjectMember.objects.filter(project=project, user=invitee).exists():
            raise ValidationError(
                {"identifier": ["That person is already on this project."]}
            )
        if project.scope_user_id == invitee.id:
            raise ValidationError(
                {"identifier": ["That person already owns this project."]}
            )
        home = scope.scope_people_ids(project)
        if (
            home is not None
            and invitee.id not in home
            and not user_can_invite_outside(request.user, project)
        ):
            raise PermissionDenied(
                "Only the project's owner can invite someone from outside the "
                f"{project.scope}."
            )
        if ProjectInvitation.objects.filter(
            project=project, invitee=invitee, status=ProjectInvitation.Status.PENDING
        ).exists():
            raise ValidationError(
                {"identifier": ["That person already has a pending invitation."]}
            )

        invitation = ProjectInvitation.objects.create(
            project=project,
            inviter=request.user,
            invitee=invitee,
            message=str(request.data.get("message", ""))[:2000],
        )
        record_audit_event(
            actor=request.user,
            action="project.invite",
            target_type="project",
            target_id=str(project.id),
            metadata={"invitation_id": str(invitation.id),
                      "username": invitee.get_username()},
        )
        return Response(
            ProjectInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectInvitationCancelView(APIView):
    """An editor withdraws a pending invitation they sent."""

    def post(self, request: Request, pk, iid) -> Response:
        project = _visible_project(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot manage this project's invitations.")
        invitation = get_object_or_404(ProjectInvitation, pk=iid, project=project)
        if invitation.status != ProjectInvitation.Status.PENDING:
            raise ValidationError("That invitation is no longer pending.")
        _close_invitation(
            invitation, ProjectInvitation.Status.CANCELLED, request.user,
            "project.invitation.cancel",
        )
        return Response({"id": str(invitation.id), "status": invitation.status})


class MyProjectInvitationsView(APIView):
    """The caller's pending project invitations — the notifications feed."""

    def get(self, request: Request) -> Response:
        invitations = (
            ProjectInvitation.objects.filter(
                invitee=request.user, status=ProjectInvitation.Status.PENDING
            )
            .select_related(
                "project", "project__scope_lab", "project__scope_department",
                "invitee", "inviter",
            )
        )
        data = ProjectInvitationSerializer(invitations, many=True).data
        return Response({"count": len(data), "items": data})


class ProjectInvitationRespondView(APIView):
    """The invitee accepts, rejects, or ignores one of their invitations."""

    _ACTIONS = {
        "accept": ProjectInvitation.Status.ACCEPTED,
        "reject": ProjectInvitation.Status.REJECTED,
        "ignore": ProjectInvitation.Status.IGNORED,
    }

    def post(self, request: Request, pk) -> Response:
        invitation = get_object_or_404(
            ProjectInvitation.objects.select_related("project"), pk=pk
        )
        if invitation.invitee_id != request.user.id:
            raise PermissionDenied("This invitation is not addressed to you.")
        if invitation.status != ProjectInvitation.Status.PENDING:
            return Response(
                {"detail": "This invitation has already been answered."},
                status=status.HTTP_409_CONFLICT,
            )
        action = str(request.data.get("action", "")).strip().lower()
        if action not in self._ACTIONS:
            raise ValidationError(
                {"action": ["Must be one of: accept, reject, ignore."]}
            )

        if action == "accept":
            _, created = ProjectMember.objects.get_or_create(
                project=invitation.project, user=request.user
            )
            if created:
                _maybe_recompute_team(invitation.project)
        _close_invitation(
            invitation, self._ACTIONS[action], request.user,
            f"project.invitation.{action}",
        )
        return Response({"id": str(invitation.id), "status": invitation.status})


def _close_invitation(
    invitation: ProjectInvitation, new_status: str, actor, action: str
) -> None:
    invitation.status = new_status
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    record_audit_event(
        actor=actor,
        action=action,
        target_type="project_invitation",
        target_id=str(invitation.id),
        metadata={"project_id": str(invitation.project_id)},
    )


# --------------------------------------------------------------------------- #
# Project collaboration surface — shared feed, external ingest, seen + events.
# Papers a team shares into a project. Reuses the same visibility cascade that
# guards the project itself; writes go through tools.delivery.collaboration.
# --------------------------------------------------------------------------- #


def _user_is_project_participant(user, project: Project) -> bool:
    """Who may write into a project's feed.

    A project member, the personal owner, or a manager of the owning lab (owner,
    admin, PI) or department (owner, admin).
    Anyone else who can merely *see* the project must join it first before sharing —
    so the feed stays the shared workspace of people actually on the project.
    """
    if not user.is_authenticated:
        return False
    if project.scope_user_id == user.id:
        return True
    if ProjectMember.objects.filter(project=project, user=user).exists():
        return True
    # The managers of the owning lab or department — the same people who edit it.
    return user_can_edit_project(user, project)


def _member_brief(user) -> dict:
    return {
        "username": user.get_username(),
        "name": display_name(user),
        "initials": initials(user),
    }


def _paper_fields(content: ContentItem) -> dict:
    """The item's display fields for a feed row (mirrors the paper serializer)."""
    meta = content.metadata or {}
    authors = meta.get("authors")
    return {
        "content_id": str(content.id),
        "type": content.type,
        "source": content.source,
        "title": meta.get("title") or meta.get("name") or "Untitled",
        "abstract": meta.get("abstract") or "",
        "url": meta.get("pdf_url") or content.source_url or "",
        "venue": meta.get("venue") or "",
        "year": meta.get("year"),
        "authors": authors[:6] if isinstance(authors, list) else [],
    }


def _project_feed_payload(project: Project) -> dict:
    """Shares in a project, collapsed by content (co-sharers credited), seen-badged.

    Most-recent share of each item wins the row; earlier sharers become
    ``co_sharers``. ``seen`` carries the ledger's ``first_seen_via`` +
    ``seen_by_count`` so the UI can show "also seen by N teammates".
    """
    shares = list(
        ProjectShare.objects.filter(project=project)
        .select_related("content", "shared_by")
        .order_by("-created_at")
    )
    groups: OrderedDict = OrderedDict()
    for share in shares:
        groups.setdefault(share.content_id, []).append(share)

    seen_map = project_seen_map(project, list(groups.keys()))
    items = []
    for content_id, group in groups.items():
        primary = group[0]
        co_sharers = []
        credited = {primary.shared_by_id}
        for share in group[1:]:
            if share.shared_by_id in credited:
                continue
            credited.add(share.shared_by_id)
            co_sharers.append(_member_brief(share.shared_by))
        items.append(
            {
                **_paper_fields(primary.content),
                "share_id": str(primary.id),
                "note": primary.note,
                "share_source": primary.source,
                "shared_by": _member_brief(primary.shared_by),
                "shared_at": primary.created_at.isoformat(),
                "co_sharers": co_sharers,
                "share_count": len(group),
                "seen": seen_map.get(str(content_id)),
            }
        )
    return {"count": len(items), "items": items}


def _get_content(request: Request) -> ContentItem:
    """Resolve the ``content_item`` id from the request body (400/404 on failure)."""
    content_id = request.data.get("content_item") or request.data.get("content_id")
    if not content_id:
        raise ValidationError({"content_item": ["A content_item id is required."]})
    content = ContentItem.objects.filter(pk=content_id).first()
    if content is None:
        raise NotFound("No such content item.")
    return content


def _visible_project(request: Request, pk) -> Project:
    project = get_object_or_404(
        Project.objects.select_related("scope_lab", "scope_department", "scope_user"),
        pk=pk,
    )
    _require_open(request.user, project)
    return project


def _require_open(user, project: Project) -> None:
    """Refuse unless ``user`` may open ``project``.

    Someone who cannot even see the project exists gets a 404, the same answer
    as an id that names nothing — so guessing an ``invite_only`` project's id
    confirms nothing. Someone who can see it (a directory row) but not open it
    gets a 403: they already know it is there, and the answer is "join it".
    """
    if project.is_visible_to(user):
        return
    if scope.can_see(user, project):
        raise PermissionDenied("Join this project to open it.")
    raise NotFound("No such project.")


class ProjectShareView(APIView):
    """Share a content item into a project's collaboration feed (Feature A)."""

    def post(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if not _user_is_project_participant(request.user, project):
            raise PermissionDenied("Join this project to share into it.")
        content = _get_content(request)
        source = request.data.get("source") or ProjectShare.Source.DIGEST
        if source not in ProjectShare.Source.values:
            source = ProjectShare.Source.DIGEST
        share = share_to_project(
            project,
            content,
            request.user,
            note=str(request.data.get("note", "")),
            source=source,
        )
        trigger_fanout(share)  # Feature F: notify members this may be relevant to
        record_audit_event(
            actor=request.user,
            action="project.share",
            target_type="project",
            target_id=str(project.id),
            metadata={"content_id": str(content.id), "source": source},
        )
        return Response(
            {"share_id": str(share.id), "content_id": str(content.id)},
            status=status.HTTP_201_CREATED,
        )


class ProjectFeedView(APIView):
    """The project's shared feed — readable by anyone who can see the project."""

    def get(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        return Response(_project_feed_payload(project))


class ProjectIngestLinkView(APIView):
    """Paste a DOI / arXiv id / URL → resolve, dedup, embed, share (Feature E)."""

    def post(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if not _user_is_project_participant(request.user, project):
            raise PermissionDenied("Join this project to add papers to it.")
        raw_input = str(request.data.get("raw_input", "")).strip()
        if not raw_input:
            raise ValidationError({"raw_input": ["Paste a DOI, arXiv id, or link."]})

        # Imported here so the scraper (and its optional embedding extra) stays out
        # of the research app's import graph unless a link is actually ingested.
        from tools.retrieval.resolver import ResolveError, resolve_external

        try:
            result = resolve_external(raw_input)
        except ResolveError as exc:
            return Response(
                {"detail": str(exc) or "Couldn't find a paper for that link."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        share = share_to_project(
            project,
            result.content_item,
            request.user,
            note=str(request.data.get("note", "")),
            source=ProjectShare.Source.EXTERNAL_LINK,
        )
        trigger_fanout(share)  # Feature F: notify members this may be relevant to
        record_audit_event(
            actor=request.user,
            action="project.ingest_link",
            target_type="project",
            target_id=str(project.id),
            metadata={
                "content_id": str(result.content_item.id),
                "created": result.created,
                "embed_status": result.embed_status,
            },
        )
        return Response(
            {
                "share_id": str(share.id),
                "content_id": str(result.content_item.id),
                "created": result.created,
                "embed_status": result.embed_status,
                "title": (result.content_item.metadata or {}).get("title")
                or "Untitled",
            },
            status=status.HTTP_201_CREATED,
        )


class ProjectItemSeenView(APIView):
    """Record that the caller has viewed an item in the project (Feature B/D)."""

    def post(self, request: Request, pk, content_id) -> Response:
        project = _visible_project(request, pk)
        content = get_object_or_404(ContentItem, pk=content_id)
        seen = mark_seen(
            project, content, ProjectItemSeen.Via.DIGEST, user=request.user
        )
        record_event(
            request.user, content, RelevanceEvent.Action.VIEW, project=project
        )
        return Response(
            {
                "content_id": str(content.id),
                "first_seen_via": seen.first_seen_via,
                "seen_by_count": seen.seen_by.count(),
            }
        )


class ProjectEventView(APIView):
    """Record a weighted engagement event on a project item (Feature D)."""

    def post(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        action = str(request.data.get("action", ""))
        if action not in RelevanceEvent.Action.values:
            raise ValidationError({"action": ["Unknown engagement action."]})
        content = _get_content(request)
        event = record_event(request.user, content, action, project=project)
        return Response(
            {
                "content_id": str(content.id),
                "action": action,
                "weight": event.weight,
            },
            status=status.HTTP_201_CREATED,
        )


# --------------------------------------------------------------------------- #
# Shared collections / reading lists (Feature C)
# --------------------------------------------------------------------------- #


def _collection_brief(collection: Collection) -> dict:
    return {
        "id": str(collection.id),
        "name": collection.name,
        "description": collection.description,
        "is_archived": collection.is_archived,
        "item_count": collection.items.count(),
        "created_by": (
            _member_brief(collection.created_by) if collection.created_by_id else None
        ),
        "created_at": collection.created_at.isoformat(),
    }


def _collection_detail(collection: Collection) -> dict:
    items = [
        {
            **_paper_fields(item.content),
            "item_id": str(item.id),
            "note": item.note,
            "added_by": _member_brief(item.added_by) if item.added_by_id else None,
            "added_at": item.added_at.isoformat(),
        }
        for item in collection.items.select_related("content", "added_by")
    ]
    return {**_collection_brief(collection), "items": items}


def _get_project_collection(request, pk, cid, *, require_participant=False):
    project = _visible_project(request, pk)
    if require_participant and not _user_is_project_participant(request.user, project):
        raise PermissionDenied("Join this project to change its collections.")
    collection = get_object_or_404(Collection, pk=cid, project=project)
    return project, collection


class ProjectCollectionsView(APIView):
    """List a project's collections, or create one (Feature C)."""

    def get(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        qs = Collection.objects.filter(project=project)
        if request.query_params.get("archived") not in ("1", "true", "yes"):
            qs = qs.filter(is_archived=False)
        collections = [_collection_brief(c) for c in qs]
        return Response({"count": len(collections), "items": collections})

    def post(self, request: Request, pk) -> Response:
        project = _visible_project(request, pk)
        if not _user_is_project_participant(request.user, project):
            raise PermissionDenied("Join this project to create a collection.")
        name = str(request.data.get("name", "")).strip()
        if not name:
            raise ValidationError({"name": ["A collection needs a name."]})
        collection = Collection.objects.create(
            project=project,
            name=name[:200],
            description=str(request.data.get("description", "")),
            created_by=request.user,
        )
        record_audit_event(
            actor=request.user,
            action="project.collection_create",
            target_type="project",
            target_id=str(project.id),
            metadata={"collection_id": str(collection.id), "name": collection.name},
        )
        return Response(_collection_detail(collection), status=status.HTTP_201_CREATED)


class ProjectCollectionDetailView(APIView):
    """Read one collection (with items) or rename / archive it (Feature C)."""

    def get(self, request: Request, pk, cid) -> Response:
        _project, collection = _get_project_collection(request, pk, cid)
        return Response(_collection_detail(collection))

    def patch(self, request: Request, pk, cid) -> Response:
        _project, collection = _get_project_collection(
            request, pk, cid, require_participant=True
        )
        if "name" in request.data:
            name = str(request.data.get("name", "")).strip()
            if not name:
                raise ValidationError({"name": ["A collection needs a name."]})
            collection.name = name[:200]
        if "description" in request.data:
            collection.description = str(request.data.get("description", ""))
        if "is_archived" in request.data:
            collection.is_archived = bool(request.data.get("is_archived"))
        collection.save()
        return Response(_collection_detail(collection))


class ProjectCollectionItemsView(APIView):
    """Add a content item to a collection (Feature C).

    A duplicate add is a no-op (unique constraint) returning 200, not 500. Adding
    from a digest item also marks it seen and logs a ``save`` engagement event.
    """

    def post(self, request: Request, pk, cid) -> Response:
        project, collection = _get_project_collection(
            request, pk, cid, require_participant=True
        )
        content = _get_content(request)
        _item, created = CollectionItem.objects.get_or_create(
            collection=collection,
            content=content,
            defaults={
                "added_by": request.user,
                "note": str(request.data.get("note", "")),
            },
        )
        mark_seen(project, content, ProjectItemSeen.Via.SHARE, user=request.user)
        if created:
            record_event(
                request.user, content, RelevanceEvent.Action.SAVE, project=project
            )
        return Response(
            _collection_detail(collection),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProjectCollectionItemDetailView(APIView):
    """Remove a content item from a collection (Feature C)."""

    def delete(self, request: Request, pk, cid, content_id) -> Response:
        _project, collection = _get_project_collection(
            request, pk, cid, require_participant=True
        )
        CollectionItem.objects.filter(
            collection=collection, content_id=content_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Project state (plan 2.2)
# --------------------------------------------------------------------------- #
def _state_payload(project: Project, reader=None) -> dict:
    """One project's state, plus the two things a reader needs around it.

    The resolved timeline is included rather than left for the client to compute:
    it depends on the reader's own settings and the lab's, neither of which the
    project page holds, and a page that showed a project override while the report
    used a lab default would be describing a different judgement from the one Mylo
    is actually making.
    """
    from tools.delivery.timeline_settings import effective_timeline

    from apps.research.state import normalise_state

    state = getattr(project, "state", None)
    normalised = normalise_state(
        {
            "slow": getattr(state, "slow", None),
            "fast": getattr(state, "fast", None),
            "provenance": getattr(state, "provenance", None),
        }
    )
    return {
        "project_id": str(project.id),
        "slow": normalised["slow"],
        "fast": normalised["fast"],
        "provenance": normalised["provenance"],
        "state_version": getattr(state, "state_version", 0),
        "slow_fingerprint": getattr(state, "slow_fingerprint", ""),
        "confirmed_at": (
            state.confirmed_at.isoformat()
            if state is not None and state.confirmed_at
            else None
        ),
        "days_since_confirmed": (
            state.days_since_confirmed() if state is not None else None
        ),
        "is_empty": state is None or state.is_empty,
        "effective_timeline": effective_timeline(project, reader).as_dict(),
    }


class ProjectStateView(APIView):
    """Read or edit one project's state — what it claims, blocks on, and aims at.

    Read by anyone who can see the project; written only by an editor, the same
    permission that governs its focus. Project state is the most sensitive thing
    Mycelium stores: unpublished research plans, what is not working, and what the
    team cannot do yet.

    PATCH is a **merge**, not a replace (see :meth:`ProjectState.apply`). A client
    sending only ``fast`` leaves the research identity untouched, which is what
    lets the wizard, the extractor and the state panel each write the part they
    know about without holding the whole document.
    """

    def _get_visible(self, request, pk) -> Project:
        project = get_object_or_404(
            Project.objects.select_related(
                "scope_lab", "scope_department", "scope_user", "state"
            ),
            pk=pk,
        )
        _require_open(request.user, project)
        return project

    def get(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        return Response(_state_payload(project, request.user))

    def patch(self, request: Request, pk) -> Response:
        from apps.research.models import ProjectState

        project = self._get_visible(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot edit this project.")

        state, _created = ProjectState.objects.get_or_create(project=project)
        before = state.slow_fingerprint
        state.apply(request.data, actor=request.user)
        # An edit *is* a confirmation of what the editor just looked at: asking
        # someone to type the state and then separately assert it is current is a
        # step nobody takes, and the staleness prompt would fire on state edited
        # an hour ago.
        state.confirmed_at = timezone.localdate()
        state.save()

        record_audit_event(
            actor=request.user,
            action="project.state.update",
            target_type="project",
            target_id=str(project.id),
            # Deliberately no field values: this log is read by staff, and the
            # state is the one thing in the product they have no business seeing.
            metadata={
                "state_version": state.state_version,
                "identity_changed": before != state.slow_fingerprint,
            },
        )
        project.refresh_from_db()
        return Response(_state_payload(project, request.user))


class ProjectStateConfirmView(APIView):
    """Mark a project's state as still true today, changing nothing else.

    Separate from PATCH because it is a different act. "I read this and it is
    still right" is the cheap, frequent one, and folding it into an edit would
    mean a reader has to change something to say nothing changed.
    """

    def post(self, request: Request, pk) -> Response:
        from apps.research.models import ProjectState

        project = get_object_or_404(
            Project.objects.select_related("scope_lab", "scope_user", "state"), pk=pk
        )
        _require_open(request.user, project)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot edit this project.")

        state, _created = ProjectState.objects.get_or_create(project=project)
        state.confirmed_at = timezone.localdate()
        state.updated_by = request.user
        state.save(update_fields=["confirmed_at", "updated_by", "updated_at"])
        project.refresh_from_db()
        return Response(_state_payload(project, request.user))


class ProjectStateExtractView(APIView):
    """Read a project's state out of a document, as a **proposal**.

    Nobody wants to answer five questions about a project whose abstract or
    proposal already answers them. This reads one, and returns what it found
    without saving any of it: every field comes back marked ``inferred``, and it
    is the person who decides whether to apply it.

    Deliberately not a PATCH. An extractor that wrote straight into the state
    would overwrite what the team stated with what a model read, which is the one
    thing invariant 9 forbids. The client sends the accepted fields back through
    :class:`ProjectStateView` if and when someone accepts them.

    Reuses the résumé path's ``extract_text`` for the file itself — the size
    limit, the PDF sniffing and the "no readable text" error are already decided
    there, and a second set of answers to those questions would drift.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request: Request, pk) -> Response:
        from apps.accounts.intake import AuthorImportError, extract_text
        from apps.research.state_extract import extract_project_state

        project = get_object_or_404(Project, pk=pk)
        _require_open(request.user, project)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot edit this project.")

        upload = request.FILES.get("file")
        text = str(request.data.get("text") or "")
        if upload is not None:
            try:
                text = extract_text(
                    upload.read(),
                    content_type=getattr(upload, "content_type", ""),
                    filename=getattr(upload, "name", ""),
                )
            except AuthorImportError as exc:
                raise ValidationError({"file": [str(exc)]}) from exc
        if not text.strip():
            raise ValidationError(
                {"non_field_errors": ["Send a file or some text to read."]}
            )

        outcome = extract_project_state(text)
        return Response(outcome.as_dict())


# --------------------------------------------------------------------------- #
# Ownership and transfer (scoping plan, Phase 5)
# --------------------------------------------------------------------------- #


class ProjectOwnershipView(APIView):
    """``POST {"username"}``: hand a project to someone.

    The owner hands it to a member. The scope's managers — the lab's PI, owner
    and admins, or a department's heads — may take it themselves (audited, the
    members told), as the plan's oversight allows."""

    def post(self, request: Request, pk) -> Response:
        from . import lifecycle
        from .permissions import user_manages_project_scope

        project = _visible_project(request, pk)
        username = str(request.data.get("username") or "").strip()
        target = get_object_or_404(User, username=username)
        taking = target == request.user and user_manages_project_scope(
            request.user, project
        )
        if not taking and not user_can_change_visibility(request.user, project):
            raise PermissionDenied("Only the project's owner hands it over.")
        if not taking and not scope.is_participant(target, project):
            raise ValidationError(
                {"username": ["Ownership goes to someone already on the project."]}
            )
        if project.scope_user_id is not None:
            raise ValidationError("A personal project stays with its person.")
        lifecycle.make_owner(
            project,
            target,
            actor=request.user,
            reason="taken by the lab's managers" if taking else "handed over",
        )
        return Response(ProjectSerializer(project, context={"request": request}).data)


class ProjectTransferView(APIView):
    """``POST``: the owner offers a lab project to its lab's department.
    ``DELETE``: the owner withdraws the open offer."""

    def post(self, request: Request, pk) -> Response:
        from . import lifecycle

        project = _visible_project(request, pk)
        if not user_can_change_visibility(request.user, project):
            raise PermissionDenied("Only the project's owner offers it.")
        try:
            row = lifecycle.offer_transfer(project, request.user)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {"id": row.pk, "state": row.state, "department": row.department_id},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request: Request, pk) -> Response:
        from .models import ProjectTransfer

        project = _visible_project(request, pk)
        if not user_can_change_visibility(request.user, project):
            raise PermissionDenied("Only the project's owner withdraws it.")
        ProjectTransfer.objects.filter(
            project=project, state=ProjectTransfer.State.PENDING
        ).update(
            state=ProjectTransfer.State.WITHDRAWN,
            decided_by=request.user,
            decided_at=timezone.now(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectTransferAcceptView(APIView):
    """``POST``: a head of the department accepts the open offer."""

    def post(self, request: Request, pk) -> Response:
        from apps.accounts.permissions import user_can_edit_dept_profile

        from . import lifecycle
        from .models import ProjectTransfer

        project = get_object_or_404(Project, pk=pk)
        transfer = ProjectTransfer.objects.filter(
            project=project, state=ProjectTransfer.State.PENDING
        ).select_related("department").first()
        if transfer is None or not user_can_edit_dept_profile(
            request.user, transfer.department
        ):
            if transfer is None or not scope.can_see(request.user, project):
                raise NotFound()
            raise PermissionDenied("Only a head of the department accepts it.")
        if (
            project.scope_lab_id is None
            or project.scope_lab.department_id != transfer.department_id
        ):
            raise ValidationError("The lab is no longer in that department.")
        project = lifecycle.accept_transfer(transfer, request.user)
        return Response(ProjectSerializer(project, context={"request": request}).data)
