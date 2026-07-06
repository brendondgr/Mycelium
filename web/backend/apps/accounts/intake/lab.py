"""LLM-assisted synthesis of a research lab's collective interest profile.

The user-facing lab onboarding lets a PI describe the lab in their own words and,
optionally, paste source material — representative paper titles/abstracts, other
members' profiles, or portfolio blurbs. This module turns that free text into the
lab's ``{statement, areas, keywords}``, reusing the same extraction engine as
personal onboarding (:func:`extract_profile_fields`) but with a lab-oriented
system prompt (third-person "the lab", not first-person "I").

LLM-optional: when no model is configured the deterministic fallback echoes the
declared focus areas and a trimmed statement from the description, so onboarding
never hard-depends on a running model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from urllib.parse import parse_qs, urlparse

from .extract import extract_profile_fields

logger = logging.getLogger(__name__)

__all__ = ["synthesize_lab_interests", "source_text_from_links"]

CompleteFn = Callable[[str], str | None]

_MAX_STATEMENT_CHARS = 700

_LAB_SYSTEM_PROMPT = (
    "You build a research LAB's collective interest profile from the supplied "
    "text (the lab's own description and, optionally, representative papers, "
    "member profiles, or portfolios). Return ONLY one JSON object with exactly "
    "these keys:\n"
    '  "statement": a 2-4 sentence summary of the lab\'s shared research '
    "purpose, written in the third person about the lab (\"The lab studies...\"),\n"
    '  "areas": list of the lab\'s research areas or fields,\n'
    '  "keywords": list of specific topics or keywords,\n'
    '  "skills": list of methods, tools, or techniques the lab uses.\n'
    "Ground every value in the supplied text — do not invent topics, "
    "affiliations, or accomplishments. Use an empty string or empty list when "
    "the text does not support a field. Output only the JSON object: no prose, "
    "no explanation, no markdown code fences."
)


def synthesize_lab_interests(
    *,
    description: str = "",
    areas_hint: Sequence[str] | None = None,
    source_text: str = "",
    complete: CompleteFn | None = None,
) -> dict[str, object]:
    """Return ``{statement, areas, keywords}`` for a lab from free text.

    ``description`` is the PI's own words about the lab; ``areas_hint`` are any
    focus areas already typed in the form; ``source_text`` is optional pasted
    source material (paper titles/abstracts, member profiles, portfolios). The
    LLM reads all of it at once; the deterministic fallback keeps the flow
    working offline.
    """

    hint = _clean_list(areas_hint)
    corpus = _build_corpus(description, hint, source_text)

    fields = extract_profile_fields(
        corpus,
        complete=complete if complete is not None else _lab_complete,
        fallback=lambda: _fallback(description, hint),
    )

    # Areas the PI explicitly typed always survive, even if the model dropped
    # them; the model's additions extend (not replace) that declared focus.
    areas = _merge_unique(hint, fields.get("areas") or [])
    return {
        "statement": _as_str(fields.get("statement")),
        "areas": areas,
        "keywords": _clean_list(fields.get("keywords")),
    }


def _lab_complete(prompt: str) -> str | None:
    """Default seam: extract via the configured endpoint with a lab prompt.

    Returns ``None`` (so :func:`extract_profile_fields` falls back) when no model
    is configured, the SDK is absent, or the call fails for any reason.
    """

    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client()
    response = client.complete(
        [
            LLMMessage("system", _LAB_SYSTEM_PROMPT),
            LLMMessage("user", prompt),
        ]
    )
    return response.content


def _build_corpus(description: str, areas_hint: list[str], source_text: str) -> str:
    lines: list[str] = []
    desc = (description or "").strip()
    if desc:
        lines.append("Lab description:")
        lines.append(desc)
    if areas_hint:
        lines.append("Declared focus areas: " + ", ".join(areas_hint))
    source = (source_text or "").strip()
    if source:
        lines.append("Source material (papers, member profiles, portfolios):")
        lines.append(source)
    return "\n\n".join(lines).strip()


def _fallback(description: str, areas_hint: list[str]) -> dict[str, object]:
    """Deterministic profile when no model is available."""

    statement = _truncate(" ".join((description or "").split()), _MAX_STATEMENT_CHARS)
    if not statement and areas_hint:
        statement = "The lab's research focuses on " + _humanize(areas_hint) + "."
    return {
        "statement": statement,
        "areas": list(areas_hint),
        "keywords": [],
        "skills": [],
    }


def _merge_unique(first: list[str], second: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in [*first, *second]:
        text = " ".join(str(item).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return _merge_unique([str(item) for item in value], [])


def _as_str(value: object) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""


def _humanize(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _truncate(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].rstrip(",.;: ")
    return f"{clipped}…"


# -- Source links --------------------------------------------------------------


def _detect_author(url: str) -> tuple[str, str] | None:
    """Map an academic-profile URL to a ``(source, identifier)`` pair for import.

    Recognizes Google Scholar (``?user=``), Semantic Scholar / OpenAlex (last
    path segment), and ORCID. Returns ``None`` for anything else.
    """
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    tail = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if "scholar.google" in host:
        uid = (parse_qs(parsed.query).get("user") or [""])[0]
        return ("scholar", uid) if uid else None
    if "semanticscholar.org" in host:
        return ("semantic", tail) if tail else None
    if "openalex.org" in host:
        return ("openalex", tail) if tail else None
    if "orcid.org" in host:
        return ("orcid", tail) if tail else None
    return None


def source_text_from_links(
    links: Iterable[str],
    *,
    import_fn: Callable[[str, str], object] | None = None,
    max_links: int = 5,
) -> str:
    """Best-effort corpus text from pasted academic-profile links.

    Each recognized link (Scholar / Semantic Scholar / OpenAlex / ORCID) is
    imported for its representative work titles, areas, and keywords. Anything
    that can't be recognized or imported is kept as a plain-URL hint so the model
    still sees it. Never raises — bad links are skipped, so drafting is robust.
    """
    if import_fn is None:
        from .importer import import_author as import_fn  # local: avoid cycle

    chunks: list[str] = []
    for raw in list(links)[:max_links]:
        url = (raw or "").strip()
        if not url:
            continue
        detected = _detect_author(url)
        if detected is None:
            chunks.append(url)
            continue
        source, ident = detected
        try:
            draft = import_fn(ident, source)
        except Exception:
            logger.info("Could not import source link %r; keeping as a hint.", url)
            chunks.append(url)
            continue
        chunks.append(_draft_to_text(draft) or url)
    return "\n\n".join(chunk for chunk in chunks if chunk)


def _draft_to_text(draft: object) -> str:
    parts: list[str] = []
    name = getattr(draft, "display_name", "")
    if name:
        parts.append(f"Researcher: {name}")
    evidence = getattr(draft, "evidence", None) or []
    titles = [
        str(item.get("title", "")).strip()
        for item in evidence
        if isinstance(item, dict) and str(item.get("title", "")).strip()
    ][:8]
    if titles:
        parts.append("Representative works:")
        parts.extend(f"- {title}" for title in titles)
    areas = getattr(draft, "areas", None) or []
    if areas:
        parts.append("Areas: " + ", ".join(areas[:12]))
    keywords = getattr(draft, "keywords", None) or []
    if keywords:
        parts.append("Keywords: " + ", ".join(keywords[:15]))
    return "\n".join(parts)
