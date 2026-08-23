"""Mylo's prose: the per-theme read, and the lead paragraph over all of them.

Prompts C and D. This is the "Mylo understands me" surface, and it is built last
because it summarises everything beneath it. Two calls, each with exactly one
job:

* **Prompt C — the per-theme read.** Two to four sentences on what one strand of
  the reader's work turned up today, written against their whole portfolio: the
  research statement, the background, the stated goals, the project descriptions.
  It sits *next to* the entrants it describes, not in a separate section that
  repeats them.
* **Prompt D — the lead.** One paragraph over the theme reads. What today amounts
  to across the profile, and where to look first.

The failure mode both prompts are written against is enumeration. The numbered
list is directly beneath the read, and restating it is exactly what the previous
briefing did — the reader got the same items twice, once as prose and once as a
list, and learned to skip the prose. So neither prompt may enumerate, recite
counts as counts, or repeat an entrant's reason verbatim. The cover table carries
the numbers; these paragraphs carry the judgement.

Both are **paid-only**. A free reader's document opens on the cover table and
nothing else, which is honest — it is quieter, not broken. And both have a
deterministic fallback that never raises, with the origin recorded so a fallback
is never mistaken for a judgement.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str, str], str | None]

#: Bump when either prompt changes — the stored artefacts are per-run, so this is
#: for the eval harness rather than for invalidation.
NARRATIVE_VERSION = "cd1"

_THEME_MAX_TOKENS = 400
_LEAD_MAX_TOKENS = 400

_THEME_SYSTEM = (
    "You are Mylo, writing to a researcher you know well about ONE strand of "
    "their work and what it turned up today.\n"
    "Write two to four sentences of continuous prose. Say what the day's news "
    "in this strand amounts to, where two of the items speak to each other, and "
    "what it means for a goal the reader has actually stated.\n"
    "Rules: do NOT enumerate or list — the numbered items are printed directly "
    "beneath you and restating them is the one thing that makes a reader skip "
    "your paragraph. Do not repeat any item's reason verbatim. Name only items "
    "you were given. If the news is thin, say the strand was quiet and why the "
    "one item still qualified. Never manufacture significance. No headings, no "
    "bullet points, no markdown."
)

_LEAD_SYSTEM = (
    "You are an editor writing the opening paragraph of a researcher's daily "
    "brief, over the per-theme reads you are given.\n"
    "Write ONE paragraph: what today amounts to across their whole profile, and "
    "where to look first.\n"
    "Rules: no headings, no lists, and do not recite counts as counts — a table "
    "above you already carries the numbers, so this paragraph carries the "
    "judgement. A quiet day gets a short paragraph, not a padded one. No "
    "markdown."
)


def write_theme_read(
    portfolio_text: str,
    theme_label: str,
    theme_interests: Sequence[str],
    entrants: Sequence[dict],
    *,
    complete: CompleteFn | None = None,
) -> tuple[str, str]:
    """Prompt C. Returns ``(prose, origin)`` — origin is ``llm`` or ``fallback``.

    ``entrants`` are this theme's new items as
    ``{title, verdict, lead, caveat}`` dicts — the write-ups the fit stage
    already produced, so the read is grounded in real judgements rather than
    inventing a second opinion about the same papers.
    """
    if not entrants:
        return "", ""
    ask = complete if complete is not None else _settings_complete(_THEME_MAX_TOKENS)
    prompt = build_theme_prompt(
        portfolio_text, theme_label, theme_interests, entrants
    )
    try:
        raw = ask(_THEME_SYSTEM, prompt)
    except Exception as exc:  # noqa: BLE001 — prose degrades, it never raises
        logger.warning("theme read unavailable for %r (%s)", theme_label, exc)
        raw = None
    prose = _clean_block(raw)
    if prose:
        return prose, "llm"
    return theme_read_fallback(theme_label, entrants), "fallback"


def build_theme_prompt(
    portfolio_text: str,
    theme_label: str,
    theme_interests: Sequence[str],
    entrants: Sequence[dict],
) -> str:
    lines = [
        f"About the reader:\n{portfolio_text or '(no profile details)'}",
        "",
        f"The strand: {theme_label}",
        f"Its interests: {', '.join(theme_interests) or '(none declared)'}",
        "",
        "What entered this strand today:",
    ]
    for entry in entrants:
        lines.append(f"- {entry.get('title', '')} [{entry.get('verdict', '')}]")
        if entry.get("lead"):
            lines.append(f"    why it matters: {entry['lead']}")
        if entry.get("caveat"):
            lines.append(f"    caveat: {entry['caveat']}")
    return "\n".join(lines)


def theme_read_fallback(theme_label: str, entrants: Sequence[dict]) -> str:
    """The deterministic read: honest about what it is, and never padded.

    It states the shape of the day rather than pretending to a judgement, because
    a sentence that reads like Mylo but was written by a template is worse than
    no sentence at all.
    """
    count = len(entrants)
    if not count:
        return ""
    worth = sum(1 for entry in entrants if entry.get("verdict") == "read")
    noun = "item" if count == 1 else "items"
    lead = f"{count} new {noun} entered your {theme_label} list today"
    if worth:
        lead += f", {worth} of them worth reading in full"
    return lead + "."


def write_lead(
    portfolio_text: str,
    theme_reads: Sequence[tuple[str, str]],
    *,
    deadline_note: str = "",
    complete: CompleteFn | None = None,
) -> tuple[str, str]:
    """Prompt D. Returns ``(paragraph, origin)``.

    ``theme_reads`` is ``[(theme label, its read)]``. With nothing to lead on,
    returns an empty string rather than a paragraph explaining that there is
    nothing — the cover table already says so, in less space.
    """
    reads = [(label, text) for label, text in theme_reads if text]
    if not reads:
        return "", ""
    ask = complete if complete is not None else _settings_complete(_LEAD_MAX_TOKENS)
    prompt = build_lead_prompt(portfolio_text, reads, deadline_note=deadline_note)
    try:
        raw = ask(_LEAD_SYSTEM, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lead paragraph unavailable (%s)", exc)
        raw = None
    prose = _clean_block(raw)
    if prose:
        return prose, "llm"
    return lead_fallback(reads), "fallback"


def build_lead_prompt(
    portfolio_text: str,
    reads: Sequence[tuple[str, str]],
    *,
    deadline_note: str = "",
) -> str:
    lines = [
        f"About the reader:\n{portfolio_text or '(no profile details)'}",
        "",
        "Today's per-strand reads:",
    ]
    for label, text in reads:
        lines.append(f"- {label}: {text}")
    if deadline_note:
        lines.append("")
        lines.append(f"Deadline pressure today: {deadline_note}")
    return "\n".join(lines)


def lead_fallback(reads: Sequence[tuple[str, str]]) -> str:
    """The deterministic lead: which strands moved, and nothing more."""
    labels = [label for label, _text in reads]
    if not labels:
        return ""
    if len(labels) == 1:
        return f"Today's news is all in your {labels[0]} work."
    named = ", ".join(labels[:-1]) + f" and {labels[-1]}"
    return f"Today brought something new to {named}."


def offline_note() -> str:
    """What the document says when Mylo's writer could not be reached at all."""
    return (
        "Mylo's writer was offline for this run, so the sections below are the "
        "deterministic listing without his commentary. The rankings, positions, "
        "and deadlines are unaffected."
    )


def _clean_block(raw: str | None) -> str:
    """Strip fences and headings; return continuous prose or an empty string."""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return " ".join(lines).strip()


def _settings_complete(max_tokens: int) -> CompleteFn:
    def ask(system: str, prompt: str) -> str | None:
        from apps.core.llm import LLMMessage, build_llm_client

        client = build_llm_client(component="narrative")
        response = client.complete(
            [LLMMessage("system", system), LLMMessage("user", prompt)],
            max_tokens=max_tokens,
        )
        return response.content

    return ask
