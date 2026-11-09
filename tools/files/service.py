"""The files write door: store an upload, extract its text, delete it.

Keeping a file is always an explicit act (an upload, or an attachment to a
chat message the person sends). The résumé, project-state and lab-profile
readers still read and discard; they never store anything here.
"""

from __future__ import annotations

import hashlib
import time

from django.db import transaction
from django.utils import timezone

from . import access, extract, storage
from .models import OWNER_KINDS, StoredFile
from .storage import Refused

#: Smaller files are read during the upload request; larger ones in the worker.
INLINE_EXTRACT_BYTES = 2 * 1024 * 1024


def _settings():
    from django.conf import settings

    return {
        "max_bytes": int(getattr(settings, "FILES_MAX_BYTES", 25 * 1024 * 1024)),
        "types": list(
            getattr(settings, "FILES_TYPES", ["pdf", "txt", "md", "csv", "docx"])
        ),
        "max_total_mb": int(getattr(settings, "FILES_MAX_TOTAL_MB", 0) or 0),
        "max_pages": int(getattr(settings, "FILES_MAX_PAGES", 0) or 0),
        "purge_after_days": int(getattr(settings, "FILES_PURGE_AFTER_DAYS", 0) or 0),
    }


def _read(uploaded) -> bytes:
    if isinstance(uploaded, (bytes, bytearray)):
        return bytes(uploaded)
    chunks = []
    for chunk in (
        uploaded.chunks() if hasattr(uploaded, "chunks") else [uploaded.read()]
    ):
        chunks.append(chunk)
    return b"".join(chunks)


def store_upload(
    user,
    uploaded,
    *,
    owner_kind: str,
    owner_id,
    origin: str = "upload",
    thread_id=None,
    filename: str | None = None,
) -> StoredFile:
    """Check, store and (if small) read one upload. Raises ``Refused``."""
    from apps.accounts.services import record_audit_event

    cfg = _settings()
    owner = access.get_owner(owner_kind, owner_id)
    if owner_kind not in OWNER_KINDS or not access.can_add(user, owner_kind, owner):
        raise Refused("not_allowed", "You can't add files there.")
    size = getattr(uploaded, "size", None)
    if size is not None and size > cfg["max_bytes"]:
        raise Refused(
            "too_large", f"Files can be at most {cfg['max_bytes'] // 1048576} MB."
        )
    data = _read(uploaded)
    if len(data) > cfg["max_bytes"]:
        raise Refused(
            "too_large", f"Files can be at most {cfg['max_bytes'] // 1048576} MB."
        )
    if not data:
        raise Refused("empty", "This file is empty.")
    name = storage.clean_filename(filename or getattr(uploaded, "name", "") or "file")
    kind = storage.sniff(data, name)
    if kind not in cfg["types"]:
        raise Refused("bad_type", f"{kind} files are not accepted on this instance.")
    if kind == "docx":
        storage.check_docx(data)
    digest = hashlib.sha256(data).hexdigest()
    field = OWNER_KINDS[owner_kind]
    existing = StoredFile.objects.filter(
        **{field: owner}, sha256=digest, deleted_at__isnull=True
    ).first()
    if existing is not None:
        return existing
    if cfg["max_total_mb"]:
        used = sum(
            StoredFile.objects.filter(
                **{field: owner}, deleted_at__isnull=True
            ).values_list("size", flat=True)
        )
        if used + len(data) > cfg["max_total_mb"] * 1048576:
            raise Refused(
                "quota", f"This space holds at most {cfg['max_total_mb']} MB of files."
            )
    with transaction.atomic():
        row = StoredFile.objects.create(
            **{field: owner},
            uploaded_by=user,
            filename=name,
            kind=kind,
            content_type=storage.CONTENT_TYPES[kind],
            size=len(data),
            sha256=digest,
            origin=origin,
            thread_id=thread_id,
        )
        path = storage.folder(owner_kind, row.owner_id, str(row.pk))
        storage.write_original(path, kind, data)
        storage.write_meta(path, _meta(row))
    record_audit_event(
        actor=user,
        action="files.upload",
        target_type="stored_file",
        target_id=str(row.pk),
        metadata={"owner": f"{owner_kind}:{row.owner_id}", "size": len(data)},
    )
    if len(data) <= INLINE_EXTRACT_BYTES:
        run_extract(row)
    else:
        from . import tasks

        transaction.on_commit(lambda: tasks.extract.delay(str(row.pk)))
    return row


def _meta(row: StoredFile) -> dict:
    return {
        "id": str(row.pk),
        "owner": f"{row.owner_kind}:{row.owner_id}",
        "filename": row.filename,
        "kind": row.kind,
        "size": row.size,
        "sha256": row.sha256,
        "uploaded_by": row.uploaded_by_id,
        "created_at": row.created_at,
        "status": row.status,
    }


def run_extract(row: StoredFile) -> StoredFile:
    StoredFile.objects.filter(pk=row.pk).update(status=StoredFile.Status.EXTRACTING)
    path = storage.folder(row.owner_kind, row.owner_id, str(row.pk))
    try:
        data = storage.original(path, row.kind).read_bytes()
        text, pages = extract.extract(
            row.kind, data, max_pages=_settings()["max_pages"]
        )
    except extract.NoText as exc:
        row.status, row.extract_error = StoredFile.Status.NO_TEXT, f"no_text: {exc}"
    except Exception as exc:  # a broken file is a status, not a crash
        row.status, row.extract_error = StoredFile.Status.FAILED, f"failed: {exc}"[:300]
    else:
        storage.write_text(path, text, pages)
        row.status, row.extract_error = StoredFile.Status.READY, ""
        row.pages, row.chars = len(pages) if row.kind == "pdf" else 0, len(text)
    row.save(update_fields=["status", "extract_error", "pages", "chars"])
    storage.write_meta(path, _meta(row))
    return row


def wait_for_text(file_id, *, timeout: float = 30.0) -> str | None:
    """The file's text once extracted; ``None`` if still being read after
    ``timeout`` seconds, or if it has no text."""
    deadline = time.monotonic() + timeout
    while True:
        row = StoredFile.objects.filter(pk=file_id).first()
        if row is None:
            return None
        if row.status == StoredFile.Status.READY:
            return text_of(row)
        if row.status in (StoredFile.Status.NO_TEXT, StoredFile.Status.FAILED):
            return None
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def text_of(row: StoredFile) -> str | None:
    return storage.read_text(storage.folder(row.owner_kind, row.owner_id, str(row.pk)))


def pages_of(row: StoredFile) -> list[int]:
    return storage.read_pages(storage.folder(row.owner_kind, row.owner_id, str(row.pk)))


def delete(user, row: StoredFile) -> None:
    """Soft delete; the purge sweep removes the bytes."""
    from apps.accounts.services import record_audit_event

    if not access.can_delete(user, row):
        raise Refused("not_allowed", "You can't delete this file.")
    row.deleted_at = timezone.now()
    row.save(update_fields=["deleted_at"])
    record_audit_event(
        actor=user,
        action="files.delete",
        target_type="stored_file",
        target_id=str(row.pk),
        metadata={},
    )
    if _settings()["purge_after_days"] == 0:
        purge(row)


def purge(row: StoredFile) -> None:
    storage.remove(storage.folder(row.owner_kind, row.owner_id, str(row.pk)))
    StoredFile.objects.filter(pk=row.pk).update(purged_at=timezone.now())


def purge_deleted(now=None) -> int:
    from datetime import timedelta

    now = now or timezone.now()
    days = _settings()["purge_after_days"]
    rows = StoredFile.objects.filter(
        deleted_at__isnull=False,
        purged_at__isnull=True,
        deleted_at__lte=now - timedelta(days=days),
    )
    count = 0
    for row in rows:
        purge(row)
        count += 1
    return count
