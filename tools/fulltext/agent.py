"""What the fulltext tool gives the Mylo agent: whether a paper's full text is
stored or within reach, and reading or searching a stored one.

Declared with ``tools._framework.agentspec`` only; this module never imports
the agent tool, so either can be disabled without the other. Nothing here
fetches a paper: that uses the operator's publisher quota and is a ``write``
for a later pass.

Paper text is untrusted (it came from outside), and it is line-numbered so an
answer can cite ``#n:120`` or ``#n §Methods``. A paper read under the
instance's subscription (``licensed``) is shown no wider than a lab; an open
paper may be shown anywhere the item may.
"""

from __future__ import annotations

import re
import uuid

from tools._framework.agentspec import (
    AgentFunction,
    FunctionError,
    RefInfo,
    RefKind,
    Result,
    width_rank,
)

ALL = ("personal", "lab", "department", "project")
H = "tools.fulltext.agent"
#: Lines shown per read.
WINDOW = 160
#: Characters per line before it is cut (very long paragraphs).
LINE_CHARS = 1200
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def _f(name, summary, description, handler, *, params, required=(), output):
    return AgentFunction(
        name=name,
        summary=summary,
        description=description,
        parameters={"type": "object", "properties": params, "required": list(required)},
        handler=f"{H}:{handler}",
        risk="read",
        output=output,
        scopes=ALL,
        min_role={},
    )


def _ref(kind: str, description: str) -> dict:
    return {"type": "string", "description": description, "x-ref": kind}


_ITEM = _ref("item", "The paper: #n or item:<uuid>.")
_DOC = _ref("doc", "A stored full text: #n or doc:<id> (instead of item).")

FUNCTIONS = (
    _f(
        "fulltext_availability",
        "Is a paper's full text stored, or within legal reach?",
        "Whether Mycelium already holds the full text of a paper, or could get a legal "
        "copy (open access, or the instance's publisher keys). Nothing is fetched.",
        "fulltext_availability",
        params={"item": _ITEM},
        required=("item",),
        output="instance",
    ),
    _f(
        "fulltext_read_paper",
        "Read a stored paper's full text, by line or section.",
        "Read the stored full text of a paper, line-numbered, from a line offset or "
        "from a named section (e.g. 'Methods'). Without either, shows the section list "
        f"and the first {WINDOW} lines. Cite as #n:line or #n §Section.",
        "fulltext_read_paper",
        params={
            "item": _ITEM,
            "document": _DOC,
            "offset": {"type": "integer"},
            "section": {"type": "string"},
        },
        output="lab",
    ),
    _f(
        "fulltext_search_paper",
        "Find where a stored paper says something.",
        "Search the stored full text of one paper for words; returns matching lines "
        "with their line numbers and sections, to read further with "
        "fulltext_read_paper.",
        "fulltext_search_paper",
        params={"item": _ITEM, "document": _DOC, "query": {"type": "string"}},
        required=("query",),
        output="lab",
    ),
)

REFS = (RefKind("doc", f"{H}:resolve_doc", None, "A paper's stored full text."),)


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #


def _doc_info(doc) -> RefInfo:
    title = doc.title or doc.doi or doc.pmcid or doc.arxiv_id or doc.id
    return RefInfo(
        kind="doc",
        key=doc.id,
        title=f"[full text] {str(title)[:180]}",
        card=f"{doc.source} · {doc.chars} chars"
        + (" · subscription" if doc.licensed else ""),
        output="lab" if doc.licensed else "instance",
        read_with="fulltext_read_paper(document='{ref}')",
        untrusted=True,
    )


def resolve_doc(caller, key):
    from . import read

    doc = read.document_by_id(uuid.UUID(str(key)))
    return _doc_info(doc) if doc else None


def _key(token) -> str:
    return str(token).split(":", 1)[1] if ":" in str(token) else str(token)


def _item(token):
    from tools.retrieval.read import ContentItem

    row = ContentItem.objects.filter(pk=_key(token)).first()
    if row is None:
        raise FunctionError("not_found", "That item is no longer in the corpus.")
    return row


def _doc(caller, item=None, document=None):
    """The stored document asked for, cleared for this audience."""
    from . import read

    if document:
        doc = read.document_by_id(uuid.UUID(_key(document)))
    elif item:
        doc = read.document(_item(item))
    else:
        raise FunctionError("need_paper", "Which paper?", "Pass item='#n'.")
    if doc is None:
        raise FunctionError(
            "not_stored",
            "Mycelium does not hold this paper's full text.",
            "Check fulltext_availability; work from the abstract "
            "(corpus_item) meanwhile.",
        )
    info = _doc_info(doc)
    if width_rank(info.output) < width_rank(caller.audience.width):
        raise FunctionError(
            "audience",
            "This paper was read under the instance's "
            "subscription and can't be quoted to everyone here.",
            "Ask me in a DM.",
        )
    return doc, info


def _lines(doc) -> list[str]:
    try:
        return doc.markdown_path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError) as exc:
        raise FunctionError(
            "not_stored",
            "The stored file for this paper is missing.",
            "Tell the person; the operator can re-fetch it.",
        ) from exc


def _sections(lines: list[str]) -> list[tuple[int, int, str]]:
    """``(line number, level, title)`` for every markdown heading (1-based)."""
    out = []
    for n, line in enumerate(lines, 1):
        m = _HEADING.match(line)
        if m:
            out.append((n, len(m.group(1)), m.group(2).strip("# ").strip()))
    return out


def _section_at(sections, n: int) -> str:
    title = ""
    for start, _, name in sections:
        if start > n:
            break
        title = name
    return title


def _numbered(lines, start: int, stop: int) -> str:
    out = []
    for n in range(start, min(stop, len(lines)) + 1):
        text = lines[n - 1]
        if len(text) > LINE_CHARS:
            text = text[:LINE_CHARS] + " …"
        out.append(f"{n:>5}| {text}")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def fulltext_availability(caller, item):
    from . import read

    row = _item(item)
    found = read.availability(row)
    state = found.get("availability", "unknown")
    lines = [f"Full text: {state}"]
    if found.get("explanation"):
        lines.append(str(found["explanation"]))
    refs = []
    if state == "stored" and found.get("document"):
        doc = read.document_by_id(uuid.UUID(str(found["document"])))
        if doc is not None:
            info = _doc_info(doc)
            refs.append(info)
            lines.append(
                f"Read it with fulltext_read_paper(document='{{ref:{info.ref}}}')."
            )
    elif state not in ("stored", "invalid_identifier", "not_found", "unavailable"):
        lines.append(
            "It is not stored yet; Mylo can't fetch papers in this release. The "
            "person can request it in the app."
        )
    return Result(content="\n".join(lines), refs=refs)


def fulltext_read_paper(caller, item=None, document=None, offset=None, section=None):
    doc, info = _doc(caller, item, document)
    lines = _lines(doc)
    sections = _sections(lines)
    total = len(lines)
    head = f"{{ref:{info.ref}}} {doc.title or 'paper'} — {total} lines"
    if section:
        want = str(section).casefold().strip()
        match = next((s for s in sections if s[2].casefold() == want), None) or next(
            (s for s in sections if want in s[2].casefold()), None
        )
        if match is None:
            names = "; ".join(s[2] for s in sections[:40]) or "(no headings)"
            raise FunctionError(
                "no_section", f"No section called “{section}”.", f"Sections: {names}"
            )
        start, level, name = match
        end = next(
            (s[0] - 1 for s in sections if s[0] > start and s[1] <= level), total
        )
        end = min(end, start + WINDOW - 1)
        body = _numbered(lines, start, end)
        more = (
            f"\nMore of §{name}: fulltext_read_paper(document='{{ref:{info.ref}}}', "
            f"offset={end + 1})"
            if end < total
            else ""
        )
        return Result(
            content=f"{head}\n§{name}, lines {start}–{end}:\n{body}{more}",
            refs=[info],
            untrusted=True,
        )
    start = max(1, int(offset or 1))
    if start > total:
        raise FunctionError(
            "past_end", f"The paper has {total} lines.", "Use a smaller offset."
        )
    end = min(total, start + WINDOW - 1)
    toc = ""
    if not offset and sections:
        toc = "Sections: " + "; ".join(
            f"{name} (line {n})" for n, _, name in sections[:40]
        )
        toc += "\n"
    body = _numbered(lines, start, end)
    more = (
        f"\nNext: fulltext_read_paper(document='{{ref:{info.ref}}}', offset={end + 1})"
        if end < total
        else ""
    )
    return Result(
        content=f"{head}\n{toc}Lines {start}–{end}:\n{body}{more}",
        refs=[info],
        untrusted=True,
    )


def fulltext_search_paper(caller, query, item=None, document=None):
    doc, info = _doc(caller, item, document)
    words = [w for w in re.findall(r"\w+", str(query).casefold()) if len(w) > 1]
    if not words:
        raise FunctionError("bad_query", "Give some words to look for.")
    lines = _lines(doc)
    sections = _sections(lines)
    phrase = " ".join(words)
    scored = []
    for n, line in enumerate(lines, 1):
        low = line.casefold()
        hits = sum(1 for w in words if w in low)
        if hits:
            scored.append((-(hits + (2 if phrase in low else 0)), n))
    if not scored:
        return Result(
            content=f"{{ref:{info.ref}}}: nothing matches “{query}”.",
            refs=[info],
            untrusted=True,
        )
    best = sorted(scored)[:20]
    out = [
        f"{{ref:{info.ref}}}: {len(scored)} lines match “{query}”; the best "
        f"{len(best)}, in reading order:"
    ]
    for _, n in sorted(best, key=lambda pair: pair[1]):
        text = lines[n - 1]
        if len(text) > 400:
            text = text[:400] + " …"
        where = _section_at(sections, n)
        out.append(f"{n:>5}| {text}" + (f"   (§{where})" if where else ""))
    out.append(
        f"Read around a line with fulltext_read_paper(document='{{ref:{info.ref}}}', "
        "offset=<line>)."
    )
    return Result(content="\n".join(out), refs=[info], untrusted=True)
