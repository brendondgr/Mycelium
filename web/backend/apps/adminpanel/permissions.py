"""The platform-admin gate for the admin dashboard API.

Every admin endpoint requires an authenticated user who is either staff or a
superuser. This is the *hard* authorization boundary — the frontend nav gate is
only a rendering hint and never the security control (architecture: Django owns
auth/permissions).
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsStaffOrSuperuser(BasePermission):
    """Allow only authenticated staff or superusers."""

    message = "Administrator access is required."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser)
        )
