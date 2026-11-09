"""Bytes on disk, and what is safe to accept.

* No path component ever comes from anything a person typed: the folder is
  ``<owner kind>/<owner id>/<file uuid>`` and the name is ``original.<ext>``
  with the extension taken from the sniffed type.
* The type is decided by the bytes, never the name.
* A ``docx`` is a zip: its entry count and total uncompressed size are capped
  before anything is read (zip bombs).
"""

from __future__ import annotations

import io
import json
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path

from django.conf import settings

from tools._framework.discovery import REPO_ROOT

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
#: docx limits, checked from the zip's directory before anything is inflated.
DOCX_MAX_ENTRIES = 2000
DOCX_MAX_UNCOMPRESSED = 200 * 1024 * 1024


class Refused(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


def root() -> Path:
    configured = getattr(settings, "FILES_DATA_DIR", "") or ""
    return Path(configured).resolve() if configured else REPO_ROOT / "data" / "files"


def folder(owner_kind: str, owner_id: str, file_id: str) -> Path:
    if owner_kind not in ("user", "lab", "department", "project"):
        raise ValueError(owner_kind)
    if not re.fullmatch(r"[0-9a-fA-F-]{1,64}", str(owner_id)):
        raise ValueError("owner id")
    if not re.fullmatch(r"[0-9a-f-]{36}", str(file_id)):
        raise ValueError("file id")
    path = (root() / owner_kind / str(owner_id) / str(file_id)).resolve()
    if root().resolve() not in path.parents:
        raise ValueError("path escapes the store")
    return path


def clean_filename(name: str) -> str:
    """For display only: the last path part, printable, at most 200 chars."""
    name = (
        unicodedata.normalize("NFKC", str(name or "")).replace("\\", "/").split("/")[-1]
    )
    name = "".join(ch for ch in name if ch.isprintable()).strip().lstrip(".")
    return (name or "file")[:200]


def _looks_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data[:65536].decode("utf-8")
        return True
    except UnicodeDecodeError:
        sample = data[:8192]
        printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
        return bool(sample) and printable / len(sample) > 0.95


def sniff(data: bytes, filename: str) -> str:
    """The file's kind from its bytes. The name only chooses between text
    kinds (``.md``/``.csv``/``.txt``), which look the same as bytes."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            raise Refused("bad_type", "This file is a damaged archive.") from None
        if "word/document.xml" in names:
            return "docx"
        raise Refused(
            "bad_type", "Only Word documents (.docx) are accepted among archives."
        )
    if _looks_text(data):
        lower = filename.lower()
        if lower.endswith((".md", ".markdown")):
            return "md"
        if lower.endswith(".csv"):
            return "csv"
        return "txt"
    raise Refused("bad_type", "This kind of file can't be stored.")


def check_docx(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        if len(infos) > DOCX_MAX_ENTRIES:
            raise Refused(
                "too_complex", "This document has too many parts to read safely."
            )
        total = sum(i.file_size for i in infos)
        if total > DOCX_MAX_UNCOMPRESSED:
            raise Refused(
                "too_large_unpacked", "This document unpacks too large to read safely."
            )


def write_original(path: Path, kind: str, data: bytes) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    target = path / f"original.{kind}"
    target.write_bytes(data)
    return target


def original(path: Path, kind: str) -> Path:
    return path / f"original.{kind}"


def write_text(path: Path, text: str, pages: list[int]) -> None:
    (path / "text.md").write_text(text, encoding="utf-8")
    (path / "pages.json").write_text(json.dumps(pages), encoding="utf-8")


def read_text(path: Path) -> str | None:
    target = path / "text.md"
    return target.read_text(encoding="utf-8") if target.exists() else None


def read_pages(path: Path) -> list[int]:
    target = path / "pages.json"
    try:
        return json.loads(target.read_text()) if target.exists() else []
    except ValueError:
        return []


def write_meta(path: Path, meta: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "meta.json").write_text(
        json.dumps(meta, indent=1, default=str), encoding="utf-8"
    )


def remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
