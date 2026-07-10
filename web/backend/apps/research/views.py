import logging
from collections import OrderedDict

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import (
    user_can_manage_lab,
    user_has_department_access,
    user_has_lab_access,
)
from apps.accounts.services import record_audit_event
from apps.content.collaboration import (
    mark_seen,
    project_seen_map,
    record_event,
    share_to_project,
)
from apps.content.fanout import trigger_fanout
from apps.content.models import (
    Collection,
    CollectionItem,
    ContentItem,
    ProjectItemSeen,
    ProjectProfile,
    ProjectShare,
    RelevanceEvent,
)
from apps.content.team_profile import recompute_project_profile
from apps.core.people import display_name, initials

from .models import Project, ProjectMember
from .serializers import (
    ProjectCreateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)

logger = logging.getLogger(__name__)


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

    ``POST`` creates a project scoped to a lab (``lab`` slug, requires manage
    rights on that lab) or, with no lab, a personal project scoped to the caller.
    """

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        qs = (
            Project.objects.visible_to(self.request.user)
            .select_related("scope_lab", "scope_department", "scope_user")
            .prefetch_related("members")
        )
        lab_slug = self.request.query_params.get("lab", "").strip()
        if lab_slug:
            qs = qs.filter(scope_lab__slug=lab_slug)
        return qs

    def perform_create(self, serializer: ProjectCreateSerializer) -> None:
        lab_slug = (serializer.validated_data.pop("lab", "") or "").strip()
        user = self.request.user
        if lab_slug:
            lab = get_object_or_404(Lab, slug=lab_slug)
            if not user_can_manage_lab(user, lab):
                raise PermissionDenied(
                    "Only a lab owner or admin can add projects to this lab."
                )
            project = serializer.save(scope_lab=lab)
            target = {"scope": "lab", "lab_id": str(lab.id)}
        else:
            project = serializer.save(scope_user=user)
            target = {"scope": "user"}
        record_audit_event(
            actor=user,
            action="project.create",
            target_type="project",
            target_id=str(project.id),
            metadata={"name": project.name, **target},
        )


class LabProjectsView(ListAPIView):
    """Every project of one lab, for any member of that lab.

    Unlike the personal project list (``visible_to``, which only shows a
    rank-and-file member the projects they already belong to), this lets any lab
    member browse *all* of the lab's projects so they can decide to join one.
    Each row carries ``is_member`` so the UI can offer Join vs Leave.
    """

    serializer_class = ProjectSerializer

    def get_queryset(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_has_lab_access(self.request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        return (
            Project.objects.filter(scope_lab=lab)
            .select_related("scope_lab")
            .prefetch_related("members")
        )


def _user_can_edit(user, project: Project) -> bool:
    """Who may edit a project's name / focus.

    The personal owner edits their own project; a lab owner/admin edits their lab's
    projects (mirroring who may create them). Department-scoped projects are not
    editable through this API yet.
    """
    if project.scope_user_id is not None:
        return project.scope_user_id == user.id
    if project.scope_lab_id is not None:
        return user_can_manage_lab(user, project.scope_lab)
    return False


class ProjectDetailView(APIView):
    """Read one project (any viewer) or edit its name / research focus (managers)."""

    def _get_visible(self, request, pk) -> Project:
        project = get_object_or_404(
            Project.objects.select_related(
                "scope_lab", "scope_department", "scope_user"
            ).prefetch_related("members"),
            pk=pk,
        )
        if not project.is_visible_to(request.user):
            raise PermissionDenied("You do not have access to this project.")
        return project

    def get(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        return Response(ProjectSerializer(project, context={"request": request}).data)

    def patch(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot edit this project.")
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
        return Response(ProjectSerializer(project, context={"request": request}).data)


def _user_can_join(user, project: Project) -> bool:
    """A lab/department member may self-join that org's projects."""
    if project.scope_lab_id is not None:
        return user_has_lab_access(user, project.scope_lab)
    if project.scope_department_id is not None:
        return user_has_department_access(user, project.scope_department)
    return False  # personal projects have no self-join


class ProjectJoinView(APIView):
    """The caller joins a lab/department project they are eligible for."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(
            Project.objects.select_related("scope_lab", "scope_department"), pk=pk
        )
        if not _user_can_join(request.user, project):
            raise PermissionDenied(
                "Only members of this project's lab or department can join it."
            )
        _, created = ProjectMember.objects.get_or_create(
            project=project, user=request.user
        )
        if created:
            record_audit_event(
                actor=request.user,
                action="project.join",
                target_type="project",
                target_id=str(project.id),
                metadata={"name": project.name},
            )
            _maybe_recompute_team(project)
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


class ProjectLeaveView(APIView):
    """The caller leaves a project they belong to."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(Project, pk=pk)
        deleted, _ = ProjectMember.objects.filter(
            project=project, user=request.user
        ).delete()
        record_audit_event(
            actor=request.user,
            action="project.leave",
            target_type="project",
            target_id=str(project.id),
            metadata={"name": project.name},
        )
        if deleted:
            _maybe_recompute_team(project)
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


class ProjectMembersView(APIView):
    """A lab manager adds another lab member to one of the lab's projects."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(
            Project.objects.select_related("scope_lab"), pk=pk
        )
        if project.scope_lab_id is None:
            raise ValidationError("Members can only be added to lab projects.")
        if not user_can_manage_lab(request.user, project.scope_lab):
            raise PermissionDenied(
                "Only a lab owner or admin can add project members."
            )
        username = str(request.data.get("username", "")).strip()
        if not username:
            raise ValidationError({"username": ["A username is required."]})
        target = get_object_or_404(User, username=username)
        if not LabMembership.objects.filter(
            user=target, lab=project.scope_lab
        ).exists():
            raise ValidationError("That person is not a member of this lab.")
        _, created = ProjectMember.objects.get_or_create(
            project=project, user=target
        )
        if created:
            _maybe_recompute_team(project)
        return Response(
            ProjectSerializer(project, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# --------------------------------------------------------------------------- #
# Project collaboration surface — shared feed, external ingest, seen + events.
# Papers a team shares into a project. Reuses the same visibility cascade that
# guards the project itself; writes go through apps.content.collaboration.
# --------------------------------------------------------------------------- #


def _user_is_project_participant(user, project: Project) -> bool:
    """Who may write into a project's feed.

    A project member, the personal owner, or a lab owner/admin of a lab project.
    Anyone else who can merely *see* the project must join it first before sharing —
    so the feed stays the shared workspace of people actually on the project.
    """
    if not user.is_authenticated:
        return False
    if project.scope_user_id == user.id:
        return True
    if ProjectMember.objects.filter(project=project, user=user).exists():
        return True
    if project.scope_lab_id is not None and user_can_manage_lab(
        user, project.scope_lab
    ):
        return True
    return False


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
    if not project.is_visible_to(request.user):
        raise PermissionDenied("You do not have access to this project.")
    return project


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
        from apps.scraper.resolver import ResolveError, resolve_external

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
