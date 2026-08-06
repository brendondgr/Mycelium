"""Natural-language research statement synthesis from an author draft.

The importer aggregates *signal* (areas, keywords, a few representative
work titles); this module turns that signal into the first-person research
*statement* a researcher would write about their own focus — the prose the
onboarding review step pre-fills and the user then edits.

LLM-optional, exactly like the rest of intake (the :class:`IntakeAgent` extractor
seam): when an OpenAI-compatible endpoint is configured (``LLM_MODEL`` set), the
statement is drafted by the model through :mod:`apps.core.llm`; otherwise a
deterministic template builds a serviceable statement from the draft's top
signal. Either path returns a non-empty string for any draft that carries areas,
so onboarding never hard-depends on a running model.
"""

from __future__ import annotations

from collections.abc import Callable

from .drafts import AuthorProfileDraft

__all__ = ["CompleteFn", "draft_statement"]

# A pluggable "ask the model" seam: prompt in, drafted prose (or ``None``) out.
# ``None`` (or a raised exception, or blank text) means "fall back to template".
CompleteFn = Callable[[str], str | None]

_DEFAULT_MAX_CHARS = 700

_SYSTEM_PROMPT = (
    "You write concise, first-person research statements for a scholar's profile. "
    "Given a researcher's areas, keywords, and a few representative work "
    "titles, write 2-4 plain sentences summarizing what they research and how. "
    "Write in the first person ('I research...'). Ground every claim in the "
    "provided signal — do not invent topics, affiliations, or accomplishments. "
    "Use a calm scholarly tone; no hype, no headings, no bullet points."
)


def draft_statement(
    draft: AuthorProfileDraft,
    *,
    complete: CompleteFn | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """Return a natural-language research statement for ``draft``.

    Tries the LLM seam first (``complete``; defaults to the configured endpoint),
    and falls back to a deterministic template when the model is unavailable,
    unconfigured, errors, or returns blank text. Returns ``""`` when the draft
    carries no usable signal (no areas or keywords).
    """

    if not (draft.areas or draft.keywords):
        return ""

    ask = complete if complete is not None else _settings_complete
    drafted: str | None = None
    try:
        drafted = ask(_build_prompt(draft))
    except Exception:
        # Any failure (no model configured, no SDK, network, bad response) must
        # not break onboarding — fall through to the deterministic template.
        drafted = None

    text = (drafted or "").strip()
    if text:
        return _truncate(text, max_chars)
    return _fallback_statement(draft, max_chars)


def _settings_complete(prompt: str) -> str | None:
    """Default seam: draft via the configured OpenAI-compatible endpoint.

    Returns ``None`` (so the caller falls back) when no model is configured, the
    ``openai`` SDK is absent, or the call fails for any reason.
    """

    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="intake.statement")
    response = client.complete(
        [
            LLMMessage("system", _SYSTEM_PROMPT),
            LLMMessage("user", prompt),
        ],
        reasoning="low",
        max_tokens=320,
    )
    return response.content


def _build_prompt(draft: AuthorProfileDraft) -> str:
    lines: list[str] = []
    if draft.display_name:
        lines.append(f"Researcher: {draft.display_name}")
    if draft.institution:
        lines.append(f"Institution: {draft.institution}")
    if draft.areas:
        lines.append("Research areas: " + ", ".join(draft.areas[:12]))
    if draft.keywords:
        lines.append("Keywords: " + ", ".join(draft.keywords[:15]))
    titles = [
        str(item.get("title", "")).strip()
        for item in draft.evidence
        if str(item.get("title", "")).strip()
    ][:6]
    if titles:
        lines.append("Representative works:")
        lines.extend(f"- {title}" for title in titles)
    return "\n".join(lines)


def _fallback_statement(draft: AuthorProfileDraft, max_chars: int) -> str:
    """A deterministic statement woven from the draft's strongest signal."""

    parts: list[str] = []
    areas = _humanize(draft.areas[:3])
    if areas:
        parts.append(f"My research focuses on {areas}.")
    keywords = _humanize(draft.keywords[:5])
    if keywords:
        lead = "Recurring themes in my work include" if parts else "My work explores"
        parts.append(f"{lead} {keywords}.")
    return _truncate(" ".join(parts), max_chars)


def _humanize(items: list[str]) -> str:
    """Join a short list into readable prose: 'a', 'a and b', 'a, b, and c'."""

    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _truncate(text: str, max_chars: int) -> str:
    """Trim to ``max_chars`` on a word boundary, adding an ellipsis if cut."""

    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].rstrip(",.;: ")
    return f"{clipped}…"
