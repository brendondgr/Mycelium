"""Admin dashboard API — the two management contexts, users and labs.

Users: list/inspect and manage a personal plan + watch quota. Labs: list/inspect and
manage the lab's subscription (tier, status, when and whether it ends, whether it is
complimentary, whether Mylo is included).

Every view is gated by :class:`~apps.adminpanel.permissions.IsStaffOrSuperuser`;
there is no other authorization surface, so a non-admin gets a 403 from all of it.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Lab

from .pagination import AdminUserPagination
from .permissions import IsStaffOrSuperuser
from .serializers import (
    AdminLabDetailSerializer,
    AdminLabRowSerializer,
    AdminLabUpdateSerializer,
    AdminUserDetailSerializer,
    AdminUserRowSerializer,
    AdminUserUpdateSerializer,
)
from .services import SeatCeilingExceeded, apply_lab_update, apply_user_update


class AdminUserListView(ListAPIView):
    """``GET /api/admin/users/`` — paginated, searchable roster of all users."""

    permission_classes = [IsStaffOrSuperuser]
    serializer_class = AdminUserRowSerializer
    pagination_class = AdminUserPagination

    def get_queryset(self):
        qs = User.objects.select_related("profile", "watch").order_by(
            "-date_joined", "id"
        )
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        return qs


class AdminUserDetailView(APIView):
    """``GET`` one user's full admin view; ``PATCH`` their plan + watch quota."""

    permission_classes = [IsStaffOrSuperuser]

    def _get_user(self, pk) -> User:
        return get_object_or_404(
            User.objects.select_related("profile", "watch"), pk=pk
        )

    def get(self, request: Request, pk) -> Response:
        user = self._get_user(pk)
        return Response(AdminUserDetailSerializer(user).data)

    def patch(self, request: Request, pk) -> Response:
        user = self._get_user(pk)
        serializer = AdminUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_user_update(
            admin=request.user, user=user, data=serializer.validated_data
        )
        user.refresh_from_db()
        return Response(AdminUserDetailSerializer(user).data)


class AdminLabListView(ListAPIView):
    """``GET /api/admin/labs/`` — paginated, searchable roster of every lab."""

    permission_classes = [IsStaffOrSuperuser]
    serializer_class = AdminLabRowSerializer
    pagination_class = AdminUserPagination

    def get_queryset(self):
        qs = Lab.objects.select_related("department").order_by("name", "id")
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(slug__icontains=q)
                | Q(department__name__icontains=q)
            )
        return qs


class AdminLabDetailView(APIView):
    """``GET`` one lab's full admin view; ``PATCH`` its subscription."""

    permission_classes = [IsStaffOrSuperuser]

    def _get_lab(self, slug) -> Lab:
        return get_object_or_404(
            Lab.objects.select_related("department", "watch"), slug=slug
        )

    def get(self, request: Request, slug) -> Response:
        return Response(AdminLabDetailSerializer(self._get_lab(slug)).data)

    def patch(self, request: Request, slug) -> Response:
        lab = self._get_lab(slug)
        serializer = AdminLabUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            apply_lab_update(
                admin=request.user, lab=lab, data=serializer.validated_data
            )
        except SeatCeilingExceeded as exc:
            # The roster is larger than the chosen tier allows — an honest 400 naming
            # the ceiling beats a 500, and nothing was written (the service is atomic).
            raise ValidationError({"detail": [str(exc)]}) from exc
        lab.refresh_from_db()
        return Response(AdminLabDetailSerializer(lab).data)
