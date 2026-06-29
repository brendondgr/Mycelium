"""Small display helpers for rendering a ``User`` in API responses.

Kept in ``core`` so both ``accounts`` (lab members) and ``research`` (project
members) can build the same name/initials without importing each other.
"""

from django.contrib.auth.models import User


def display_name(user: User) -> str:
    """Human label for a user: full name when set, else the username."""
    full = user.get_full_name().strip()
    return full or user.username


def initials(user: User) -> str:
    """One or two uppercase initials for an avatar.

    Uses the first letters of the first and last name when present, otherwise
    the first two characters of the username.
    """
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first or last:
        letters = (first[:1] + last[:1]) or first[:2]
        return letters.upper()
    return user.username[:2].upper()
