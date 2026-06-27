import dataclasses

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .intake import (
    AuthorImportError,
    IntakeAgent,
    ResolutionError,
    import_author,
)
from .interests import validate_interests
from .models import Department, Lab
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
    user_to_dict,
)

INVALID_CREDENTIALS_MESSAGE = "Invalid username or password."


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
