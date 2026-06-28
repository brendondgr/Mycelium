import dataclasses

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
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.billing.services import provision_workspace

from .intake import (
    AuthorImportError,
    IntakeAgent,
    ResolutionError,
    draft_statement,
    import_author,
    merge_drafts,
    parse_resume,
)
from .interests import validate_interests
from .models import Department, Lab, WatchPreference
from .permissions import (
    user_can_edit_dept_profile,
    user_can_edit_lab_profile,
    user_has_department_access,
    user_has_lab_access,
)
from .serializers import (
    DeptProfileSerializer,
    LabProfileSerializer,
    ProfileSerializer,
    RegisterSerializer,
    WatchPreferenceSerializer,
    user_to_dict,
)
from .services import record_audit_event

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

        drafts = []
        provenance: dict[str, str] = {}

        if has_site:
            try:
                drafts.append(import_author(identifier, source))
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
                drafts.append(
                    parse_resume(
                        upload.read(),
                        content_type=getattr(upload, "content_type", "") or "",
                        filename=getattr(upload, "name", "") or "",
                    )
                )
            except AuthorImportError as exc:
                # A bad upload is the caller's error, not an upstream failure.
                return Response(
                    {"resume": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )
            provenance["resume"] = "uploaded"

        draft = merge_drafts(*drafts)
        statement = draft_statement(draft)
        interests = draft.to_interests(statement=statement)
        if provenance:
            interests.setdefault("sources", {}).update(provenance)

        return Response(
            {"draft": dataclasses.asdict(draft), "interests": interests}
        )
