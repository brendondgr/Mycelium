from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import user_to_dict

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
