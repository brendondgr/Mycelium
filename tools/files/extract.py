"""Text out of a stored file. No new dependencies: pypdf (as the résumé
reader uses) for PDF, the standard library for docx, plain decoding for text.

Returns ``(text, page_offsets)`` where ``page_offsets[i]`` is the line number
(1-based) where page ``i + 1`` starts, so answers can cite ``p.14``.
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class NoText(Exception):
    """The file has no text to read (a scanned PDF)."""


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def pdf(data: bytes, *, max_pages: int = 0) -> tuple[str, list[int]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    lines: list[str] = []
    offsets: list[int] = []
    pages = reader.pages
    count = len(pages) if not max_pages else min(len(pages), max_pages)
    for i in range(count):
        offsets.append(len(lines) + 1)
        text = pages[i].extract_text() or ""
        lines.extend(text.splitlines() or [""])
        if i < count - 1:
            lines.append("")
    body = "\n".join(lines).strip()
    if len(body.replace("\n", "").strip()) < 20:
        raise NoText("this PDF has no text to read; OCR is not available")
    return "\n".join(lines), offsets


def docx(data: bytes) -> tuple[str, list[int]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    out: list[str] = []
    body = root.find(f"{W}body")
    for block in list(body) if body is not None else []:
        if block.tag == f"{W}p":
            out.append("".join(t.text or "" for t in block.iter(f"{W}t")))
        elif block.tag == f"{W}tbl":
            for row in block.iter(f"{W}tr"):
                cells = [
                    "".join(t.text or "" for t in cell.iter(f"{W}t"))
                    for cell in row.iter(f"{W}tc")
                ]
                out.append("| " + " | ".join(cells) + " |")
            out.append("")
    text = "\n".join(out).strip()
    if not text:
        raise NoText("this document has no text")
    return text, [1]


def extract(kind: str, data: bytes, *, max_pages: int = 0) -> tuple[str, list[int]]:
    if kind == "pdf":
        return pdf(data, max_pages=max_pages)
    if kind == "docx":
        return docx(data)
    text = decode(data)
    if not text.strip():
        raise NoText("this file is empty")
    return text, [1]
