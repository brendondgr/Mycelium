"""Résumé / CV ingestion: an uploaded PDF or text file -> AuthorProfileDraft.

Parse-and-discard (brief decision D2): the upload is read into memory, reduced to
an interest draft, and never persisted. The draft uses the importer's shared
:class:`AuthorProfileDraft` shape, so a résumé merges cleanly with a site import
downstream and feeds the same statement + contract path.

LLM-optional (D3): when a model is configured, it extracts structured interests
from the résumé text; otherwise a deterministic section/keyword heuristic does.
Either way the upload never blocks on a running model — the heuristic keeps the
flow alive offline and in CI.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Callable
from typing import Any

from .aggregate import aggregate
from .drafts import AuthorProfileDraft
from .errors import AuthorImportError

__all__ = [
    "MAX_RESUME_BYTES",
    "CompleteFn",
    "draft_from_resume",
    "extract_text",
    "parse_resume",
]

CompleteFn = Callable[[str], str | None]

MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB — résumés are small; cap abuse early.
_MIN_TEXT_CHARS = 20
_PDF_MAGIC = b"%PDF-"
_TEXT_EXTENSIONS = (".txt", ".text", ".md", ".markdown", ".rst")

_SYSTEM_PROMPT = (
    "You extract a researcher's interest profile from their résumé/CV. "
    "Return ONLY a JSON object with these keys: display_name (string), "
    "institution (string), areas (list of research areas/fields), keywords "
    "(list of specific topics), methods (list of techniques/methodologies), "
    "skills (list of tools, languages, and technical skills). Use only what the "
    "text supports; use empty strings/lists when unsure. No prose, no markdown."
)


# -- text extraction ----------------------------------------------------------


def extract_text(
    data: bytes,
    *,
    content_type: str = "",
    filename: str = "",
) -> str:
    """Return readable text from an uploaded PDF or text résumé.

    Raises :class:`AuthorImportError` (surfaced as a 4xx by the view) for an
    empty/oversize file, an unsupported type, or a file with no readable text.
    """

    if not data:
        raise AuthorImportError("the uploaded file is empty")
    if len(data) > MAX_RESUME_BYTES:
        raise AuthorImportError("the uploaded file is too large (5 MB maximum)")

    name = (filename or "").strip().lower()
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    looks_pdf = (
        data[: len(_PDF_MAGIC)] == _PDF_MAGIC
        or ctype == "application/pdf"
        or name.endswith(".pdf")
    )

    if looks_pdf:
        text = _extract_pdf_text(data)
    elif ctype.startswith("text/") or name.endswith(_TEXT_EXTENSIONS) or not ctype:
        text = _decode_text(data)
    else:
        raise AuthorImportError(
            f"unsupported file type {content_type!r}; upload a PDF or text résumé"
        )

    text = text.strip()
    if len(text) < _MIN_TEXT_CHARS:
        raise AuthorImportError("could not read any text from the file")
    return text


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # lazy: importing this module needs no pypdf

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # An empty password unlocks many "owner-protected" PDFs.
            try:
                reader.decrypt("")
            except Exception as exc:
                raise AuthorImportError(
                    "the PDF is encrypted; upload an unprotected copy"
                ) from exc
        pages = [page.extract_text() or "" for page in reader.pages]
    except AuthorImportError:
        raise
    except Exception as exc:
        raise AuthorImportError("could not read the PDF file") from exc
    return "\n".join(pages)


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="ignore")


# -- résumé -> draft ----------------------------------------------------------


def parse_resume(
    data: bytes,
    *,
    content_type: str = "",
    filename: str = "",
    complete: CompleteFn | None = None,
) -> AuthorProfileDraft:
    """Extract text from an upload and reduce it to an aggregated draft."""

    text = extract_text(data, content_type=content_type, filename=filename)
    return draft_from_resume(text, complete=complete)


def draft_from_resume(
    text: str,
    *,
    complete: CompleteFn | None = None,
) -> AuthorProfileDraft:
    """Turn résumé text into an aggregated :class:`AuthorProfileDraft`.

    Tries the LLM seam first; falls back to a deterministic section/keyword
    heuristic when the model is unavailable, unconfigured, errors, or returns
    something that is not parseable JSON.
    """

    ask = complete if complete is not None else _settings_complete
    fields: dict[str, Any] | None = None
    try:
        fields = _parse_llm_payload(ask(_build_prompt(text)))
    except Exception:
        fields = None
    if fields is None:
        fields = _heuristic_fields(text)

    draft = AuthorProfileDraft(
        display_name=str(fields.get("display_name", "")),
        institution=str(fields.get("institution", "")),
        areas=list(fields.get("areas", [])),
        keywords=list(fields.get("keywords", [])),
        methods=list(fields.get("methods", [])),
        skills=list(fields.get("skills", [])),
    )
    return aggregate(draft)


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client()
    response = client.complete(
        [
            LLMMessage("system", _SYSTEM_PROMPT),
            LLMMessage("user", prompt),
        ],
        reasoning="low",
        max_tokens=500,
    )
    return response.content


def _build_prompt(text: str) -> str:
    # Cap the text so a long CV cannot blow the context window.
    excerpt = text[:8000]
    return f"Résumé / CV text:\n\n{excerpt}"


# -- LLM JSON parsing ---------------------------------------------------------


def _parse_llm_payload(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "display_name": _as_str(data.get("display_name") or data.get("name")),
        "institution": _as_str(data.get("institution") or data.get("affiliation")),
        "areas": _as_list(data.get("areas")),
        "keywords": _as_list(data.get("keywords")),
        "methods": _as_list(data.get("methods")),
        "skills": _as_list(data.get("skills")),
    }


def _as_str(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


# -- deterministic heuristic --------------------------------------------------

_SECTION_PATTERNS: dict[str, str] = {
    # Order matters: the most specific headers are matched first.
    "areas": (
        r"research interests|areas? of (?:research|interest|expertise|specialization)"
        r"|research areas?|fields? of (?:research|study)"
    ),
    "methods": r"methods?|techniques|methodolog(?:y|ies)|approaches",
    "skills": (
        r"technical skills|core competencies|competencies|skills"
        r"|programming languages|languages|tools|technologies"
    ),
    "keywords": r"keywords|topics|expertise",
}

_INSTITUTION_HINTS = (
    "university",
    "institute",
    "college",
    "laborator",
    "department of",
    "school of",
)


def _heuristic_fields(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    found: dict[str, list[str]] = {
        "areas": [],
        "keywords": [],
        "methods": [],
        "skills": [],
    }
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        header, inline = _match_header(stripped)
        if header is not None:
            current = header
            if inline:
                found[header].extend(_split_terms(inline))
            continue
        if not stripped:
            current = None  # a blank line closes the current section block
            continue
        if current is not None:
            found[current].extend(_split_terms(stripped))

    return {
        "display_name": _guess_name(lines),
        "institution": _guess_institution(lines),
        **found,
    }


def _match_header(line: str) -> tuple[str | None, str]:
    """If ``line`` opens a known section, return (field, inline-content).

    Only the *label* before the first ``:``/dash is tested, so a header with a
    long inline list ("Research Interests: a, b, c, …") still registers while a
    long prose sentence does not.
    """

    if not line:
        return None, ""
    delimited = re.match(r"^\s*([A-Za-z][\w &/-]{0,40}?)\s*[:\-–—]\s*(.*)$", line)
    if delimited:
        field = _header_field(delimited.group(1))
        return (field, delimited.group(2).strip()) if field else (None, "")
    # A bare header line with no delimiter or inline content (e.g. "SKILLS").
    if len(line) <= 40:
        field = _header_field(line)
        if field:
            return field, ""
    return None, ""


def _header_field(label: str) -> str | None:
    cleaned = label.strip().rstrip(":").strip()
    for field, pattern in _SECTION_PATTERNS.items():
        if re.fullmatch(rf"(?:{pattern})", cleaned, re.IGNORECASE):
            return field
    return None


def _split_terms(text: str) -> list[str]:
    text = re.sub(r"^[\s•·\-\*]+", "", text)
    parts = re.split(r"[,;/|•·]|\s+and\s+|\s+&\s+", text)
    terms: list[str] = []
    for part in parts:
        term = part.strip(" .\t•-*")
        if 2 <= len(term) <= 60 and not term.isdigit():
            terms.append(term)
    return terms


def _guess_name(lines: list[str]) -> str:
    for line in lines[:8]:
        candidate = line.strip()
        if not candidate or "@" in candidate or any(c.isdigit() for c in candidate):
            continue
        lowered = candidate.lower()
        if any(word in lowered for word in ("curriculum", "vitae", "resume", "résumé")):
            continue
        words = candidate.split()
        if 1 <= len(words) <= 5 and all(word[:1].isalpha() for word in words):
            return candidate
    return ""


def _guess_institution(lines: list[str]) -> str:
    for line in lines:
        lowered = line.lower()
        if any(hint in lowered for hint in _INSTITUTION_HINTS):
            return line.strip()[:120]
    return ""
