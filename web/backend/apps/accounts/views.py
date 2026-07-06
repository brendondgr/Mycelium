import dataclasses
import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
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
    claim_pending_invitations,
    decline_invitation,
    invite_to_lab,
    record_audit_event,
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


class LabWatchView(RetrieveUpdateAPIView):
    """Lab members read what Milo watches for the lab; the lead / owner / admin edit it.

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
    """Read or update what Milo keeps an eye on for the caller (own only).

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
    """Members of a lab the caller can access (any member may read the roster)."""

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
        profile.save()
        return Response(ProfileSerializer(profile).data)


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
