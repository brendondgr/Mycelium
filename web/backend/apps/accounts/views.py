import dataclasses
import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.billing.services import create_lab_workspace, provision_workspace

from .intake import (
    AuthorImportError,
    IntakeAgent,
    ResolutionError,
    extract_text,
    import_author,
    source_text_from_links,
    synthesize_interests,
    synthesize_lab_interests,
)
from .interests import validate_interests
from .models import (
    Department,
    DeptMembership,
    Lab,
    LabInvitation,
    LabMembership,
    LabWatchPreference,
    WatchPreference,
)
from .permissions import (
    user_can_edit_dept_profile,
    user_can_edit_lab_profile,
    user_can_invite_to_lab,
    user_can_manage_department,
    user_can_manage_lab,
    user_has_department_access,
    user_has_lab_access,
)
from .serializers import (
    DeptProfileSerializer,
    LabInvitationSerializer,
    LabMemberSerializer,
    LabProfileSerializer,
    LabWatchPreferenceSerializer,
    MyInvitationSerializer,
    MyLabSerializer,
    ProfileSerializer,
    RegisterSerializer,
    WatchPreferenceSerializer,
    user_to_dict,
)
from .services import (
    accept_invitation,
    add_dept_member,
    add_lab_member,
    attach_existing_lab_to_department,
    cancel_invitation,
    claim_pending_invitations,
    create_lab_in_department,
    decline_invitation,
    department_labs_payload,
    department_members_payload,
    detach_lab_from_department,
    invite_to_lab,
    record_audit_event,
    set_lab_department_inclusion,
    remove_dept_member,
    remove_lab_member,
    set_lab_member_role,
)

INVALID_CREDENTIALS_MESSAGE = "Invalid username or password."


class RegisterRateThrottle(AnonRateThrottle):
    """Throttle anonymous account creation (rate from DEFAULT_THROTTLE_RATES)."""

    scope = "register"


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request: Request) -> Response:
    get_token(request)
    return Response({"detail": "ok"})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    username = str(request.data.get("username", "")).strip()
    password = str(request.data.get("password", ""))

    if not username or not password:
        return Response(
            {"non_field_errors": ["Enter both username and password."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"non_field_errors": [INVALID_CREDENTIALS_MESSAGE]},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    login(request, user)
    return Response(user_to_dict(user))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register_view(request: Request) -> Response:
    """Create a user + workspace in one atomic step, then log them in.

    Two phases inside one transaction: create the ``User`` (the post_save signal
    creates the ``Profile``), then ``provision_workspace`` builds the org +
    billing rows. A failure in either phase rolls back the whole thing, so a
    half-built account never persists.
    """
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)  # -> 400 with field errors
    data = serializer.validated_data

    with transaction.atomic():
        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password"],  # hashed by the project's password hashers
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )  # post_save signal creates the Profile

        result = provision_workspace(
            user,
            data["account_type"],
            org_name=data.get("org_name", ""),
            institution=data.get("institution", ""),
        )

        # Surface any lab invitations that were sent to this email before signup.
        claim_pending_invitations(user)

        record_audit_event(
            actor=user,
            action="account.register",
            target_type="user",
            target_id=str(user.pk),
            metadata={
                "account_type": data["account_type"],
                "tier": result.subscription.tier,
                "lab_id": str(result.lab.id) if result.lab else None,
                "department_id": (
                    str(result.department.id) if result.department else None
                ),
            },
        )

    login(request, user)  # set the session immediately, same as login_view
    return Response(user_to_dict(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request: Request) -> Response:
    if not request.user.is_authenticated:
        return Response(status=status.HTTP_204_NO_CONTENT)

    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request: Request) -> Response:
    user = request.user
    if not isinstance(user, User) or not user.is_authenticated:
        return Response(status=status.HTTP_401_UNAUTHORIZED)

    return Response(user_to_dict(user))


@api_view(["POST"])
def verify_email_view(request: Request) -> Response:
    """Mark the caller's email verified (scaffold).

    Email verification is non-blocking this sprint: a signed-in user confirms
    their own email. Real token signing, email templates, and SMTP delivery are
    deferred; the endpoint and the ``Profile.is_verified`` flag are wired so the
    flow exists end to end.
    """
    profile = request.user.profile
    profile.is_verified = True
    profile.save()
    return Response({"is_verified": True})


# -- Profile read/update (object-level permissions, brief Phase G) -------------


class MyProfileView(RetrieveUpdateAPIView):
    """A user reads and edits their own profile."""

    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user.profile


class LabProfileView(RetrieveUpdateAPIView):
    """Lab members read the lab profile; the lead PI / owner / admin edit it."""

    serializer_class = LabProfileSerializer

    def get_object(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        user = self.request.user
        if self.request.method in SAFE_METHODS:
            if not user_has_lab_access(user, lab):
                raise PermissionDenied("You do not have access to this lab.")
        elif not user_can_edit_lab_profile(user, lab):
            raise PermissionDenied("Only a lab lead or admin can edit this profile.")
        return lab.profile


#: Max lab-logo upload size (2 MB) and the raster/vector types we accept.
LAB_LOGO_MAX_BYTES = 2 * 1024 * 1024


def _lab_logo_payload(lab: Lab) -> dict[str, object]:
    """The write-response shape for the logo endpoint (also the serializer fields)."""
    return {"has_logo": lab.has_logo, "logo_version": lab.logo_version}


def sniff_image_content_type(data: bytes) -> str | None:
    """Return the image content type from magic bytes, or ``None`` if unknown.

    Dependency-free (no Pillow): recognises PNG/JPEG/GIF/WebP by signature and
    SVG by a leading ``<svg``/``<?xml`` marker. SVG is safe here because the logo
    is only ever rendered via ``<img src>`` (scripts inside it never execute) and
    served with ``X-Content-Type-Options: nosniff``.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:512].lstrip().lstrip(b"\xef\xbb\xbf").lstrip()
    if head[:5].lower() == b"<?xml" or head[:4].lower() == b"<svg":
        lowered = data[:4096].lower()
        if b"<svg" in lowered:
            return "image/svg+xml"
    return None


class LabLogoView(APIView):
    """Serve, replace, or clear a lab's logo — served through the API gateway.

    ``GET`` streams the stored file to any lab member. ``POST``/``PUT`` accept a
    multipart ``file`` upload (validated by size + magic bytes) from a lead PI /
    owner / admin. ``DELETE`` clears it. Kept off ``MEDIA_URL`` so no static
    media route or nginx location is needed — the existing ``/api`` gateway
    already reaches the backend.
    """

    parser_classes = [MultiPartParser, FormParser]

    def _lab(self) -> Lab:
        return get_object_or_404(Lab, slug=self.kwargs["slug"])

    def get(self, request: Request, slug: str) -> Response | FileResponse:
        lab = self._lab()
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        if not lab.logo:
            raise Http404("This lab has no logo.")
        response = FileResponse(
            lab.logo.open("rb"),
            content_type=lab.logo_content_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response

    def _save(self, request: Request) -> Response:
        lab = self._lab()
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can change the logo.")
        upload = request.FILES.get("file") or request.FILES.get("logo")
        if upload is None:
            return Response(
                {"file": ["No file was uploaded."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > LAB_LOGO_MAX_BYTES:
            return Response(
                {"file": ["The logo must be 2 MB or smaller."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = sniff_image_content_type(upload.read(4096))
        upload.seek(0)
        if content_type is None:
            return Response(
                {"file": ["Use a PNG, JPG, GIF, WebP, or SVG image."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ext = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/svg+xml": "svg",
        }[content_type]
        if lab.logo:
            lab.logo.delete(save=False)
        lab.logo.save(f"{lab.slug}.{ext}", upload, save=False)
        lab.logo_content_type = content_type
        lab.save(update_fields=["logo", "logo_content_type", "updated_at"])
        record_audit_event(
            actor=request.user,
            action="lab.logo.update",
            target_type="lab",
            target_id=str(lab.id),
            metadata={"content_type": content_type},
        )
        return Response(_lab_logo_payload(lab))

    def post(self, request: Request, slug: str) -> Response:
        return self._save(request)

    def put(self, request: Request, slug: str) -> Response:
        return self._save(request)

    def delete(self, request: Request, slug: str) -> Response:
        lab = self._lab()
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can change the logo.")
        if lab.logo:
            lab.logo.delete(save=False)
        lab.logo_content_type = ""
        lab.save(update_fields=["logo", "logo_content_type", "updated_at"])
        return Response(_lab_logo_payload(lab))


class LabWatchView(RetrieveUpdateAPIView):
    """Lab members read what Mylo watches for the lab; the lead / owner / admin edit it.

    The row is auto-created with the lab, but ``get_or_create`` guards labs that
    predate the watch model so an old lab still gets sensible defaults.
    """

    serializer_class = LabWatchPreferenceSerializer

    def get_object(self) -> LabWatchPreference:
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        user = self.request.user
        if self.request.method in SAFE_METHODS:
            if not user_has_lab_access(user, lab):
                raise PermissionDenied("You do not have access to this lab.")
        elif not user_can_edit_lab_profile(user, lab):
            raise PermissionDenied("Only a lab lead or admin can edit this.")
        watch, _ = LabWatchPreference.objects.get_or_create(lab=lab)
        return watch


class DeptProfileView(RetrieveUpdateAPIView):
    """Department members read the dept profile; the owner / admin edit it."""

    serializer_class = DeptProfileSerializer

    def get_object(self):
        department = get_object_or_404(Department, id=self.kwargs["pk"])
        user = self.request.user
        if self.request.method in SAFE_METHODS:
            if not user_has_department_access(user, department):
                raise PermissionDenied("You do not have access to this department.")
        elif not user_can_edit_dept_profile(user, department):
            raise PermissionDenied("Only the owner or an admin can edit this profile.")
        return department.profile


class MyWatchView(RetrieveUpdateAPIView):
    """Read or update what Mylo keeps an eye on for the caller (own only).

    The row is created on first access, so a user who never finished the watch
    step still gets sensible defaults (weekly cadence, no topics).
    """

    serializer_class = WatchPreferenceSerializer

    def get_object(self) -> WatchPreference:
        watch, _ = WatchPreference.objects.get_or_create(user=self.request.user)
        return watch


# -- Lab membership reads (workspace switcher + members list) ------------------


class MyLabsView(ListAPIView):
    """List the caller's labs, or create a new one with the caller as PI.

    ``GET`` returns the caller's memberships (workspace switcher). ``POST`` lets
    an existing user start another lab: it provisions the lab, makes them
    OWNER + PI lead, and returns the new membership in the same ``MyLab`` shape.
    """

    serializer_class = MyLabSerializer

    def get_queryset(self):
        return (
            LabMembership.objects.filter(user=self.request.user)
            .select_related("lab", "lab__department")
            .order_by("lab__name")
        )

    def post(self, request: Request) -> Response:
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response(
                {"name": ["A lab name is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = create_lab_workspace(request.user, name)
        record_audit_event(
            actor=request.user,
            action="lab.create",
            target_type="lab",
            target_id=str(result.lab.id),
            metadata={"name": name},
        )
        membership = (
            LabMembership.objects.select_related("lab", "lab__department")
            .get(user=request.user, lab=result.lab)
        )
        return Response(
            MyLabSerializer(membership).data, status=status.HTTP_201_CREATED
        )


class LabMembersView(ListAPIView):
    """A lab's member roster: any member reads; a manager adds an existing user.

    ``GET`` lists members. ``POST {username, role}`` adds an existing user directly
    (distinct from an emailed invitation) and seats them on the lab's paying scope; a
    seat-ceiling breach returns 400.
    """

    serializer_class = LabMemberSerializer

    def get_queryset(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_has_lab_access(self.request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        return (
            LabMembership.objects.filter(lab=lab)
            .select_related("user")
            .order_by("-is_lead", "user__username")
        )

    def post(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_manage_lab(request.user, lab):
            raise PermissionDenied("Only a lab owner or admin can add members.")
        username = str(request.data.get("username", "")).strip()
        target = get_object_or_404(User, username=username)
        role = str(request.data.get("role", "") or LabMembership.Role.MEMBER)
        membership = add_lab_member(lab, target, role=role, actor=request.user)
        return Response(
            LabMemberSerializer(membership).data, status=status.HTTP_201_CREATED
        )


class LabMemberDetailView(APIView):
    """A lab manager changes a member's role or removes them (deferred seat removal)."""

    def _managed_lab(self, slug: str) -> Lab:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_manage_lab(self.request.user, lab):
            raise PermissionDenied("Only a lab owner or admin can manage members.")
        return lab

    def patch(self, request: Request, slug: str, username: str) -> Response:
        lab = self._managed_lab(slug)
        target = get_object_or_404(User, username=username)
        role = str(request.data.get("role", "")).strip()
        membership = set_lab_member_role(lab, target, role, actor=request.user)
        return Response(LabMemberSerializer(membership).data)

    def delete(self, request: Request, slug: str, username: str) -> Response:
        lab = self._managed_lab(slug)
        target = get_object_or_404(User, username=username)
        owners = LabMembership.objects.filter(lab=lab, role=LabMembership.Role.OWNER)
        if owners.filter(user=target).exists() and owners.count() == 1:
            return Response(
                {"detail": "A lab must keep at least one owner."},
                status=status.HTTP_409_CONFLICT,
            )
        remove_lab_member(lab, target, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- Lab invitations -----------------------------------------------------------


class LabInvitationsView(APIView):
    """A lab manager lists the lab's invitations and invites new people.

    Only a PI (lead) or owner/admin may invite or see the invitation roster.
    Invite by email (matched to an account, else kept pending) or by username.
    """

    def _get_lab(self) -> Lab:
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_can_invite_to_lab(self.request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can manage invitations.")
        return lab

    def get(self, request: Request, slug: str) -> Response:
        lab = self._get_lab()
        invitations = lab.invitations.select_related(
            "lab", "invitee", "inviter"
        ).all()
        return Response(LabInvitationSerializer(invitations, many=True).data)

    def post(self, request: Request, slug: str) -> Response:
        lab = self._get_lab()
        invitation = invite_to_lab(
            lab=lab,
            inviter=request.user,
            identifier=str(request.data.get("identifier", "")),
            role=str(request.data.get("role", "") or LabMembership.Role.MEMBER),
        )  # raises ValidationError -> 400 on bad input / duplicate / member
        return Response(
            LabInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )


class MyInvitationsView(ListAPIView):
    """The caller's pending lab invitations — the notifications-panel feed."""

    serializer_class = MyInvitationSerializer

    def get_queryset(self):
        return (
            LabInvitation.objects.filter(
                invitee=self.request.user,
                status=LabInvitation.Status.PENDING,
            )
            .select_related("lab", "inviter")
            .order_by("-created_at")
        )


class InvitationRespondView(APIView):
    """The invitee accepts, rejects, or ignores one of their invitations."""

    def post(self, request: Request, pk) -> Response:
        invitation = get_object_or_404(LabInvitation, pk=pk)
        if invitation.invitee_id != request.user.id:
            raise PermissionDenied("This invitation is not addressed to you.")
        if invitation.status != LabInvitation.Status.PENDING:
            return Response(
                {"detail": "This invitation has already been answered."},
                status=status.HTTP_409_CONFLICT,
            )

        action = str(request.data.get("action", "")).strip().lower()
        if action == "accept":
            accept_invitation(invitation, request.user)
        elif action == "reject":
            decline_invitation(invitation, request.user, ignore=False)
        elif action == "ignore":
            decline_invitation(invitation, request.user, ignore=True)
        else:
            return Response(
                {"action": ["Must be one of: accept, reject, ignore."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"id": str(invitation.id), "status": invitation.status})


class LabInvitationCancelView(APIView):
    """A lab manager withdraws a pending invitation they sent."""

    def post(self, request: Request, slug: str, pk) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_invite_to_lab(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can manage invitations.")
        invitation = get_object_or_404(LabInvitation, pk=pk, lab=lab)
        cancel_invitation(invitation, actor=request.user)  # 400 if not pending
        return Response({"id": str(invitation.id), "status": invitation.status})


# -- Department members & labs -------------------------------------------------


class DeptMembersView(APIView):
    """Effective dept roster (any member reads); a manager adds a direct member."""

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        return Response(department_members_payload(department))

    def post(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can add members.")
        username = str(request.data.get("username", "")).strip()
        target = get_object_or_404(User, username=username)
        role = str(request.data.get("role", "") or DeptMembership.Role.MEMBER)
        add_dept_member(department, target, role=role, actor=request.user)
        return Response(
            department_members_payload(department), status=status.HTTP_201_CREATED
        )


class DeptMemberDetailView(APIView):
    """A department manager removes a direct member (deferred seat removal)."""

    def delete(self, request: Request, pk, username: str) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can remove members.")
        target = get_object_or_404(User, username=username)
        if department.owner_id == target.id:
            return Response(
                {"detail": "The department owner cannot be removed."},
                status=status.HTTP_409_CONFLICT,
            )
        remove_dept_member(department, target, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeptLabsView(APIView):
    """Labs under a department (any member reads); a manager attaches or creates one."""

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        return Response(department_labs_payload(department))

    def post(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can add labs.")
        slug = str(request.data.get("slug", "")).strip()
        name = str(request.data.get("name", "")).strip()
        if slug:
            lab = get_object_or_404(Lab, slug=slug)
            attach_existing_lab_to_department(department, lab, actor=request.user)
        elif name:
            create_lab_in_department(department, name, request.user, actor=request.user)
        else:
            return Response(
                {"detail": ["Provide a lab name to create, or a slug to attach."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            department_labs_payload(department), status=status.HTTP_201_CREATED
        )


class DeptLabDetailView(APIView):
    """A department manager detaches a lab, or toggles its inclusion in the plan."""

    def patch(self, request: Request, pk, slug: str) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can change a lab's plan.")
        lab = get_object_or_404(Lab, slug=slug)
        if "included_in_plan" not in request.data:
            return Response(
                {"included_in_plan": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        set_lab_department_inclusion(
            department, lab, bool(request.data.get("included_in_plan")), actor=request.user
        )
        return Response(department_labs_payload(department))

    def delete(self, request: Request, pk, slug: str) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can detach labs.")
        lab = get_object_or_404(Lab, slug=slug)
        detach_lab_from_department(department, lab, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- Author import + intake session (brief Phase G) ---------------------------


class ImportAuthorView(APIView):
    """Build an interest-profile draft from an external author id (no save)."""

    def post(self, request: Request) -> Response:
        identifier = str(request.data.get("identifier", "")).strip()
        source = str(request.data.get("source", "")).strip()
        if not identifier or not source:
            return Response(
                {"non_field_errors": ["'identifier' and 'source' are required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            draft = import_author(identifier, source)
        except ResolutionError as exc:
            return Response(
                {"non_field_errors": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
            )
        except AuthorImportError as exc:
            return Response(
                {"non_field_errors": [str(exc)]},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "draft": dataclasses.asdict(draft),
                "interests": draft.to_interests(),
            }
        )


class IntakeSessionView(APIView):
    """Drive one step of the bounded intake loop (stateless across requests).

    The client round-trips the accumulating ``interests``; the agent re-derives
    which fields are still thin each call, so no server-side session is stored.
    """

    def post(self, request: Request) -> Response:
        interests = request.data.get("interests") or {}
        free_text = str(request.data.get("free_text", ""))
        answer = request.data.get("answer")

        agent = IntakeAgent()
        state = agent.start(free_text=free_text, seed_interests=interests)
        if answer is not None and not state.done:
            state = agent.answer(state, str(answer))

        return Response(
            {
                "interests": state.interests,
                "question": agent.question(state),
                "summary": agent.summary(state),
                "done": state.done,
            }
        )


class ConfirmIntakeView(APIView):
    """Validate gathered interests against the contract and save the own profile."""

    def post(self, request: Request) -> Response:
        interests = request.data.get("interests") or {}
        validated = validate_interests(interests)  # 400 on contract violation
        profile = request.user.profile
        profile.interests = validated
        # Scope the write to interests + the columns the pre_save embed hook
        # re-derives, so a concurrent basics PATCH (onboarding fires both at
        # once) can't clobber interests and this can't clobber the basics.
        profile.save(
            update_fields=["interests", "embedding_text", "embedding", "updated_at"]
        )
        return Response(ProfileSerializer(profile).data)


class ProposeClustersView(APIView):
    """Propose (or re-sort) interest clusters for the "Organize your interests" step.

    Three modes on one POST:
      - **Instruct** ``{instruction, clusters?, areas?, keywords?, statement?,
        watch_topics?}`` → build theme→sub-topic clusters from a free-text
        description, refining the caller's current clusters (ids preserved for a
        persisting theme) — the "Build clusters with Mylo" box. May **invent**
        concrete sub-topics, so it returns a widened ``areas`` union too.
      - **Propose** ``{areas, keywords?, statement?}`` → group the areas into named
        clusters (LLM, geometric fallback) — the intake / "organize" affordance.
      - **Sort** ``{clusters, unsorted}`` → route the ``unsorted`` new areas into the
        existing clusters (ids preserved) — the profile-edit "sort these" affordance.

    Always returns ``{clusters: [{id, label, areas}], areas: [...],
    watch_topics: [...], source}`` where ``areas`` is the union the clusters
    partition (unchanged for propose/sort, widened for instruct) and
    ``watch_topics`` is the per-cluster seed the caller prefills for what Mylo
    watches. Pure per-user; no lab scope.
    """

    def post(self, request: Request) -> Response:
        from apps.billing.entitlements import (
            cluster_cap,
            cluster_topic_cap,
            topic_cap,
        )
        from apps.content.clustering import seed_watch_topics

        from .intake.clusters import (
            compose_clusters,
            propose_clusters,
            sort_into_clusters,
        )

        data = request.data or {}
        existing = data.get("clusters") or []
        unsorted = data.get("unsorted") or []
        instruction = str(data.get("instruction") or "").strip()
        if instruction:
            clusters, source = compose_clusters(
                instruction=instruction,
                areas=data.get("areas") or [],
                keywords=data.get("keywords") or [],
                statement=str(data.get("statement") or ""),
                existing_clusters=existing,
                watch_topics=data.get("watch_topics") or [],
                max_clusters=cluster_cap(request.user),
                max_areas_per_cluster=cluster_topic_cap(request.user),
            )
        elif existing and unsorted:
            clusters = sort_into_clusters(existing, unsorted)
            source = "sorted"
        else:
            clusters, source = propose_clusters(
                data.get("areas") or [],
                keywords=data.get("keywords") or [],
                statement=str(data.get("statement") or ""),
            )
        areas = [area for cluster in clusters for area in cluster["areas"]]
        # Seed only as many watch topics as the caller's tier can actually save,
        # so a proposal never prefills more than the watch step will accept.
        watch_topics = seed_watch_topics(
            {"areas": areas, "clusters": clusters}, cap=topic_cap(request.user)
        )
        return Response(
            {
                "clusters": clusters,
                "areas": areas,
                "watch_topics": watch_topics,
                "source": source,
            }
        )


# Sources the onboarding import box accepts. Exactly one site may be used per
# synthesize call (a single ``source`` field); a résumé is additive (brief D4).
SYNTHESIZE_SOURCES = {"openalex", "semantic", "scholar", "orcid"}


class SynthesizeView(APIView):
    """Build one interest draft from an optional author id and/or a résumé upload.

    Accepts ``multipart/form-data`` with optional ``source`` + ``identifier`` (at
    most one site) and an optional ``resume`` file; at least one source is
    required. Imports the site, parses the résumé, merges them, and drafts a
    natural-language statement — then returns ``{draft, interests}`` without
    saving (``confirm`` performs the save). Résumé bytes are parsed and discarded.
    """

    def post(self, request: Request) -> Response:
        source = str(request.data.get("source", "")).strip().lower()
        identifier = str(request.data.get("identifier", "")).strip()
        upload = request.FILES.get("resume")

        has_site = bool(source or identifier)
        if has_site and (not source or not identifier):
            return Response(
                {
                    "non_field_errors": [
                        "Provide both 'source' and 'identifier' to import from a site."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if source and source not in SYNTHESIZE_SOURCES:
            return Response(
                {"source": [f"unknown source {source!r}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not has_site and upload is None:
            return Response(
                {
                    "non_field_errors": [
                        "Provide an author id (source + identifier) and/or a "
                        "résumé file."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        site_draft = None
        resume_text = ""
        provenance: dict[str, str] = {}

        if has_site:
            try:
                site_draft = import_author(identifier, source)
            except ResolutionError as exc:
                return Response(
                    {"non_field_errors": [str(exc)]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except AuthorImportError as exc:
                return Response(
                    {"non_field_errors": [str(exc)]},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        if upload is not None:
            try:
                resume_text = extract_text(
                    upload.read(),
                    content_type=getattr(upload, "content_type", "") or "",
                    filename=getattr(upload, "name", "") or "",
                )
            except AuthorImportError as exc:
                # A bad upload is the caller's error, not an upstream failure.
                return Response(
                    {"resume": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )
            provenance["resume"] = "uploaded"

        # The LLM reads the gathered text and fills every field in one call; the
        # structured draft is the deterministic fallback when no model is up.
        draft, interests = synthesize_interests(
            site_draft=site_draft,
            resume_text=resume_text,
            provenance=provenance,
        )
        return Response(
            {"draft": dataclasses.asdict(draft), "interests": interests}
        )


def _as_str_list(value) -> list[str]:
    """Normalize a field to a list of non-empty strings.

    Handles a real list, a JSON-encoded array string, or a plain string with
    newline/comma-separated items (how the multipart form sends areas + links).
    """
    if isinstance(value, (list, tuple)):
        items = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            items = parsed
        else:
            items = [part for chunk in text.splitlines() for part in chunk.split(",")]
    else:
        return []
    return [s for s in (str(item).strip() for item in items) if s]


class LabIntakeSynthesizeView(APIView):
    """Draft a lab's ``{statement, areas, keywords}`` from the PI's own words.

    Accepts ``multipart/form-data`` (or JSON): the lab ``description``, any
    ``areas`` already typed, uploaded source ``files`` (résumés, papers — parsed
    to text and discarded), and pasted source ``links`` (Google Scholar /
    Semantic Scholar / OpenAlex / ORCID profiles, imported best-effort). The LLM
    reads it all and fills the fields; a deterministic fallback keeps the flow
    working with no model. Nothing is saved — the client reviews, then PATCHes.
    """

    def post(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can edit this profile.")

        description = str(request.data.get("description", "")).strip()
        areas_hint = _as_str_list(request.data.get("areas"))
        links = _as_str_list(request.data.get("links"))
        uploads = request.FILES.getlist("files")

        # Assemble source material: pasted-link imports + extracted file text.
        source_chunks: list[str] = []
        if links:
            link_text = source_text_from_links(links)
            if link_text:
                source_chunks.append(link_text)
        for upload in uploads:
            try:
                text = extract_text(
                    upload.read(),
                    content_type=getattr(upload, "content_type", "") or "",
                    filename=getattr(upload, "name", "") or "",
                )
            except AuthorImportError:
                continue  # skip an unreadable file rather than fail the draft
            if text.strip():
                source_chunks.append(text)
        source_text = "\n\n".join(source_chunks).strip()

        if not description and not source_text and not areas_hint:
            return Response(
                {
                    "non_field_errors": [
                        "Describe the lab or add focus areas / source material "
                        "to synthesize a profile."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = synthesize_lab_interests(
            description=description,
            areas_hint=areas_hint,
            source_text=source_text,
        )
        return Response(result)
