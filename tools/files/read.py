"""The files read door. Return plain values, not querysets."""

from __future__ import annotations

from . import access
from .models import StoredFile


def visible_files(user, *, kind=None, owner=None) -> list[StoredFile]:
    return access.visible_queryset(user, kind=kind, owner=owner)


def can_see(user, file_id) -> bool:
    row = StoredFile.objects.filter(pk=file_id).first()
    return bool(row) and access.can_see(user, row)
