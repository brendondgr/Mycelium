"""``api/tools/files/``: upload, list, read, download, delete. Backend only."""

from __future__ import annotations

from django.http import FileResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from . import access, service, storage
from .models import StoredFile
from .storage import Refused


def _json(row: StoredFile) -> dict:
    return {
        "id": str(row.pk),
        "filename": row.filename,
        "kind": row.kind,
        "size": row.size,
        "pages": row.pages,
        "chars": row.chars,
        "status": row.status,
        "extract_error": row.extract_error,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
        "origin": row.origin,
        "uploaded_by": row.uploaded_by_id,
        "created_at": row.created_at.isoformat(),
    }


def _refused(exc: Refused, status=400) -> Response:
    codes = {"not_allowed": 403, "too_large": 413, "quota": 413}
    return Response(
        {"code": exc.code, "detail": exc.detail}, status=codes.get(exc.code, status)
    )


def _visible(request, file_id) -> StoredFile | None:
    try:
        row = StoredFile.objects.filter(pk=file_id).first()
    except Exception:  # a malformed id is simply not found
        return None
    return row if row is not None and access.can_see(request.user, row) else None


_NOT_FOUND = Response({"code": "not_found", "detail": "No such file."}, status=404)


class FilesView(APIView):
    def get(self, request):
        kind = request.query_params.get("owner_kind")
        owner = (
            access.get_owner(kind, request.query_params.get("owner_id"))
            if kind
            else None
        )
        if kind and not access.can_see_owner(request.user, kind, owner):
            return Response(
                {"code": "not_found", "detail": "No such owner."}, status=404
            )
        rows = access.visible_queryset(request.user, kind=kind, owner=owner)
        return Response({"files": [_json(r) for r in rows]})

    def post(self, request):
        from apps.accounts.permissions import require_verified_email

        require_verified_email(request.user)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {"code": "no_file", "detail": "Send the file as 'file'."}, status=400
            )
        kind = request.data.get("owner_kind") or "user"
        owner_id = request.data.get("owner_id") or (
            request.user.pk if kind == "user" else ""
        )
        try:
            row = service.store_upload(
                request.user, uploaded, owner_kind=kind, owner_id=owner_id
            )
        except Refused as exc:
            return _refused(exc)
        return Response(_json(row), status=201)


class FileView(APIView):
    def get(self, request, file_id):
        row = _visible(request, file_id)
        return Response(_json(row)) if row else _NOT_FOUND

    def delete(self, request, file_id):
        row = _visible(request, file_id)
        if row is None:
            return _NOT_FOUND
        try:
            service.delete(request.user, row)
        except Refused as exc:
            return _refused(exc)
        return Response(status=204)


class FileTextView(APIView):
    def get(self, request, file_id):
        row = _visible(request, file_id)
        if row is None:
            return _NOT_FOUND
        text = service.text_of(row) if row.status == StoredFile.Status.READY else None
        if text is None:
            return Response(
                {
                    "status": row.status,
                    "detail": row.extract_error or "The text is not ready.",
                },
                status=409,
            )
        lines = text.splitlines()
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
            limit = max(1, min(int(request.query_params.get("limit", 200)), 2000))
        except ValueError:
            offset, limit = 0, 200
        window = lines[offset : offset + limit]
        return Response(
            {
                "lines": [
                    {"n": offset + i + 1, "text": t} for i, t in enumerate(window)
                ],
                "total_lines": len(lines),
                "pages": service.pages_of(row),
            }
        )


class FileDownloadView(APIView):
    def get(self, request, file_id):
        from apps.accounts.services import record_audit_event

        row = _visible(request, file_id)
        if row is None:
            return _NOT_FOUND
        path = storage.original(
            storage.folder(row.owner_kind, row.owner_id, str(row.pk)), row.kind
        )
        if not path.exists():
            return _NOT_FOUND
        if row.uploaded_by_id != request.user.pk:
            record_audit_event(
                actor=request.user,
                action="files.download",
                target_type="stored_file",
                target_id=str(row.pk),
                metadata={},
            )
        response = FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=row.filename,
            content_type=row.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
