"""What the files tool gives the Mylo agent: four read functions and the
``file:`` reference kind. Declared with ``tools._framework.agentspec`` only;
this tool never imports the agent, and the agent does not depend on it."""

from __future__ import annotations

import math
import re
from collections import Counter

from tools._framework.agentspec import (
    AgentFunction,
    FunctionError,
    RefInfo,
    RefKind,
    Result,
)

from . import access, service
from .models import StoredFile

ALL = ("personal", "lab", "department", "project")
H = "tools.files.agent"
FEATURE = "entitlement:agent_files"


def _info(row: StoredFile) -> RefInfo:
    pages = f", {row.pages} pages" if row.pages else ""
    return RefInfo(
        kind="file",
        key=str(row.pk),
        title=row.filename,
        card=f"{row.kind} file{pages}, {row.status}",
        output=access.output_width(row),
        read_with=(
            "files_read(file='{ref}', page=1) or files_search(file='{ref}', query=...)"
        ),
        untrusted=True,
    )


def resolve_file(caller, key):
    row = StoredFile.objects.filter(pk=str(key)).first()
    if row is None or not access.can_see(caller.user, row):
        return None
    return _info(row)


def search_files(caller, q, limit):
    rows = access.visible_queryset(caller.user, q=str(q or ""))
    return [_info(r) for r in rows[:limit]]


def _row(caller, ref) -> StoredFile:
    key = str(ref).split(":", 1)[1] if ":" in str(ref) else str(ref)
    row = StoredFile.objects.filter(pk=key).first()
    if row is None or not access.can_see(caller.user, row):
        raise FunctionError("not_visible", "That file is not available.")
    return row


def _scope_owner(caller):
    scope = caller.scope
    if scope.kind == "project":
        return "project", scope.obj
    if scope.kind == "lab":
        return "lab", scope.obj
    if scope.kind == "department":
        return "department", scope.obj
    return "user", caller.user


def files_list(caller):
    from tools._framework.agentspec import width_rank

    kind, owner = _scope_owner(caller)
    rows = access.visible_queryset(caller.user, kind=kind, owner=owner)
    if kind == "user":  # a personal thread also sees what the person uploaded anywhere
        rows += [
            r
            for r in access.visible_queryset(caller.user)
            if r.uploaded_by_id == caller.user.pk and r not in rows
        ]
    rows = [
        r
        for r in rows
        if width_rank(access.output_width(r)) >= width_rank(caller.audience.width)
    ]
    if not rows:
        return Result(content="No stored files here.")
    infos = [_info(r) for r in rows[:30]]
    lines = [f"- {{ref:{i.ref}}} {i.title} — {i.card}" for i in infos]
    return Result(content="Stored files:\n" + "\n".join(lines), refs=infos)


def files_info(caller, file):
    row = _row(caller, file)
    info = _info(row)
    lines = [
        f"{{ref:{info.ref}}} {row.filename}",
        f"Type: {row.kind}",
        f"Size: {row.size} bytes",
        f"Pages: {row.pages or '—'}",
        f"Status: {row.status}",
        f"Belongs to: {row.owner_kind}",
        f"Uploaded: {row.created_at:%Y-%m-%d}",
    ]
    if row.extract_error:
        lines.append(f"Note: {row.extract_error}")
    return Result(content="\n".join(lines), refs=[info])


def _text(row) -> list[str]:
    if row.status != StoredFile.Status.READY:
        raise FunctionError(
            "not_ready",
            f"This file is {row.status}.",
            "Try again in a moment."
            if row.status in ("stored", "extracting")
            else row.extract_error,
        )
    return (service.text_of(row) or "").splitlines()


def _page_of(line_no: int, pages: list[int]) -> int:
    page = 1
    for i, start in enumerate(pages, 1):
        if start <= line_no:
            page = i
    return page


def files_read(caller, file, page=None, offset=0, limit=120):
    row = _row(caller, file)
    lines = _text(row)
    pages = service.pages_of(row)
    limit = max(1, min(int(limit or 120), 400))
    if page:
        p = max(1, min(int(page), len(pages) or 1))
        start = (pages[p - 1] - 1) if pages else 0
        end = (pages[p] - 1) if p < len(pages) else len(lines)
        window = range(start, min(end, start + limit))
    else:
        start = max(0, int(offset or 0))
        window = range(start, min(len(lines), start + limit))
    info = _info(row)
    body = "\n".join(f"{n + 1}: {lines[n]}" for n in window)
    tail = (
        f"\n[lines {window.start + 1}-{window.stop} of {len(lines)}]" if window else ""
    )
    page_note = f" (page {page})" if page else ""
    return Result(
        content=f"{{ref:{info.ref}}}{page_note}\n{body}{tail}",
        refs=[info],
        untrusted=True,
    )


_WORD = re.compile(r"[a-z0-9]+")


def files_search(caller, file, query, limit=5):
    """BM25 over 12-line passages; returns passages with page and line."""
    row = _row(caller, file)
    lines = _text(row)
    pages = service.pages_of(row)
    size = 12
    chunks = [(i, lines[i : i + size]) for i in range(0, len(lines), size // 2)]
    docs = [Counter(_WORD.findall(" ".join(c).lower())) for _, c in chunks]
    q = [w for w in _WORD.findall(str(query).lower()) if len(w) > 2]
    if not q or not docs:
        raise FunctionError("bad_query", "Say what to look for.")
    n = len(docs)
    avg = sum(sum(d.values()) for d in docs) / n or 1
    df = {w: sum(1 for d in docs if w in d) for w in q}
    scored = []
    for (start, chunk), d in zip(chunks, docs, strict=True):
        length = sum(d.values()) or 1
        score = 0.0
        for w in q:
            if not d[w]:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            score += idf * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * length / avg))
        if score > 0:
            scored.append((score, start, chunk))
    scored.sort(key=lambda s: -s[0])
    info = _info(row)
    if not scored:
        return Result(
            content=f"Nothing in {{ref:{info.ref}}} matches “{query}”.", refs=[info]
        )
    out = []
    for _, start, chunk in scored[: max(1, min(int(limit or 5), 10))]:
        hit = next(
            (k for k, t in enumerate(chunk) if any(w in t.lower() for w in q)), 0
        )
        page = _page_of(start + hit + 1, pages) if row.kind == "pdf" else None
        where = f"p.{page}, " if page else ""
        out.append(
            f"[{where}lines {start + 1}-{start + len(chunk)}]\n"
            + "\n".join(f"{start + k + 1}: {t}" for k, t in enumerate(chunk))
        )
    return Result(
        content=f"Passages from {{ref:{info.ref}}}:\n\n" + "\n\n".join(out),
        refs=[info],
        untrusted=True,
    )


def _ref(description):
    return {"type": "string", "description": description, "x-ref": "file"}


def _fn(name, activity, summary, description, params=None, required=()):
    return AgentFunction(
        name=name,
        activity=activity,
        summary=summary,
        description=description,
        parameters={
            "type": "object",
            "properties": params or {},
            "required": list(required),
        },
        handler=f"{H}:{name}",
        risk="read",
        output="lab",
        scopes=ALL,
        min_role={},
        feature=FEATURE,
    )


FUNCTIONS = (
    _fn(
        "files_list",
        "Looking at the stored files",
        "Files stored in this conversation's space.",
        "List the files stored for this conversation's scope (a project's files in a "
        "project thread; your own uploads in a personal one).",
    ),
    _fn(
        "files_info",
        "Looking at {file}",
        "One stored file: type, pages, status.",
        "Name, type, size, pages and extraction status of one stored file.",
        {"file": _ref("#n or file:<uuid>")},
        ("file",),
    ),
    _fn(
        "files_read",
        "Reading {file}",
        "Read a stored file by page or line range, line-numbered.",
        "Read part of a stored file's text, line-numbered so you can cite #n:line or "
        "#n p.N. Pass page for a PDF page, or offset/limit for lines.",
        {
            "file": _ref("#n or file:<uuid>"),
            "page": {"type": "integer"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"},
        },
        ("file",),
    ),
    _fn(
        "files_search",
        "Searching {file} for “{query}”",
        "Find passages in a stored file.",
        "Keyword search inside one stored file. Returns the best passages with page "
        "and line numbers to cite.",
        {
            "file": _ref("#n or file:<uuid>"),
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ("file", "query"),
    ),
)

REFS = (RefKind("file", f"{H}:resolve_file", f"{H}:search_files", "A stored file."),)
