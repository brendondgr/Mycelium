"""Sectioned daily-report writer for the Mylo Report.

The report is organised the way the reader's work is: a **Personal** part over
their own matches, then one part per **project** they are on. Each part is broken
down by category, so a reader looking for funding reads one Grants section rather
than sifting grants out of a mixed list.

- The Personal part is a fan-out of prompts — one per research surface (Paper,
  Grant, Fellowship, Conference), each receiving the researcher's profile and *only*
  their area's found items (title, match, deadline, and the per-item tailored
  rationale already written and persisted on the
  :class:`~apps.content.models.RelevanceScore`), writing a grounded markdown section
  explaining, item by item, why it fits *this* researcher — plus one prompt that
  reads the day's counts and those sections and writes the opening paragraph.
- **Project parts are written deterministically** from the same persisted
  rationales. A reader on six projects would otherwise cost six times the model
  budget for prose that restates rationale the matcher already wrote and that the
  reader is scanning, not reading. Holding the cost flat is what lets every project
  be in the report instead of only the top few.

The fan-out is one pass: the prompts are independent, their results are
concatenated once, and nothing plans, calls a tool, loops, or reflects.

The assembled body is GitHub-flavored markdown: the summary paragraph, then
``## Personal`` and one ``## Project · <name>`` per project, each with a ``###``
heading per non-empty category. Within a section the items are still grouped by
the reader's focus themes, which is the level where a theme actually helps.
Everything is **grounded** (each prompt sees only real items) and every stage has a
**deterministic markdown fallback**, so a missing or flaky model degrades to a
still-useful, honest report rather than nothing — the same contract as
:mod:`apps.content.suggest` / :mod:`apps.content.opportunity_llm`.

The report body is markdown; the frontend renders it (see the Daily section).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

#: The model seam: (system_prompt, user_prompt) -> raw completion text or None.
#: Injected in tests; the default routes through the configured LLM client.
CompleteFn = Callable[[str, str], str | None]

#: Stable display order + labels for the four research surfaces.
SECTION_ORDER = ["papers", "grants", "fellowships", "conferences"]
SECTION_LABELS = {
    "papers": "Papers",
    "grants": "Grants",
    "fellowships": "Fellowships",
    "conferences": "Conferences",
}
SECTION_NOUN = {
    "papers": "paper",
    "grants": "grant",
    "fellowships": "fellowship",
    "conferences": "conference",
}

#: How many items per area the Personal section prompt writes up (a little more
#: than the bottom-right UI showcase, which stays at 3).
REPORT_ITEMS_PER_SECTION = 6

#: How many items per area a project's section lists. Higher than the Personal
#: prompt's slice because these are written deterministically — there is no token
#: budget to spend, and a project is a narrow enough surface that ten items still
#: read as a short list.
PROJECT_ITEMS_PER_SECTION = 10

#: The heading the reader's own part carries, and the prefix a project's part does.
PERSONAL_HEADING = "Personal"
PROJECT_HEADING_PREFIX = "Project · "

#: Generous token budgets — a multi-item markdown section needs headroom beyond the
#: 1024 client default, or the model is cut off mid-write (finish_reason=length).
_SECTION_MAX_TOKENS = 1200
_SUMMARY_MAX_TOKENS = 500

_MARKDOWN_RULES = (
    "Write GitHub-flavored markdown. For each item, start a new paragraph with the "
    "title in bold — link it as [Title](url) when a URL is given, otherwise just "
    "**Title** — followed by its match percent and any near-term deadline on the "
    "same line, then 1-3 sentences of tailored explanation. Do NOT add a section "
    "heading (the report adds it). Do not use tables or code fences. Ground every "
    "sentence ONLY in the items and profile provided; never invent a title, number, "
    "or deadline."
)

#: Appended to every section prompt for an institutional (lab) report. The
#: recommendation is already made — the prompt's job is to pass it on in a natural
#: sentence, not to re-derive who anyone is or to name someone it wasn't given.
_MEMBER_RULES = (
    " Some items list who in the lab they are best suited to. When an item does, "
    "say so plainly in its paragraph (e.g. \"Best suited to Ana Reyes\"), using "
    "ONLY the names given for that item, spelled exactly as given. Never guess, "
    "add, or drop a name, and never say anything about a person beyond what the "
    "item's own note supports. Items with no names listed simply get none."
)

_SECTION_SYSTEM_PROMPT = {
    "papers": (
        "You are Mylo's papers specialist for a lab-intelligence platform. Given a "
        "researcher's profile and the new papers matched for them today, write a "
        "short section that, for each notable paper, explains concretely WHY it is "
        "relevant to THIS researcher's work and HOW they could use it — for a "
        "current project, a proposal angle, a method, or a claim to check. Be warm, "
        "calm, and specific; a research partner, not a hype machine. " + _MARKDOWN_RULES
    ),
    "grants": (
        "You are Mylo's funding specialist. Given a researcher's profile and the new "
        "grant opportunities matched for them today, write a short section that, for "
        "each notable grant, explains why it fits their research scope and career "
        "stage and how they could position a proposal around it, flagging any "
        "near-term deadline. Be specific and honest about fit. " + _MARKDOWN_RULES
    ),
    "fellowships": (
        "You are Mylo's fellowships specialist. Do NOT re-litigate eligibility or "
        "lead with it: for an individual it was already checked before the "
        "fellowship reached this list, and for a lab it does not apply at all — a "
        "lab has no citizenship or career stage, so its fellowships are matched on "
        "research fit. Given the profile and the fellowships matched today, write a "
        "short section that, for each notable one, explains how it fits the "
        "research topics, methods, and trajectory and what it would let them "
        "pursue, flagging any near-term deadline. " + _MARKDOWN_RULES
    ),
    "conferences": (
        "You are Mylo's conferences specialist. Given a researcher's profile and the "
        "new conferences / calls for papers matched for them today, write a short "
        "section that, for each notable venue, explains why their work belongs in "
        "its scope and tracks and what they could submit, flagging any near-term "
        "submission deadline. " + _MARKDOWN_RULES
    ),
}

_SUMMARY_SYSTEM_PROMPT = (
    "You are Mylo, the research scout for a lab-intelligence platform, acting as the "
    "editor of a daily report. You are given the day's counts — for the reader "
    "personally and for each project they are on — and the already-written detail "
    "sections. Write ONLY the opening paragraph of the report (2-4 sentences, plain "
    "prose, no markdown heading and no lists): say how many new items of each kind "
    "surfaced today, name which projects picked something up and a couple of the "
    "standouts by title, and set up the detail that follows. Everything you are "
    "given is new today and already filtered for relevance, so do not hedge about "
    "whether it matters. Be warm, calm, and specific. Ground every statement ONLY in "
    "the counts and sections you are given; never invent a title, number, deadline, "
    "or project name."
)


# --------------------------------------------------------------------------- #
# Public orchestration
# --------------------------------------------------------------------------- #


def empty_report_body() -> str:
    """The honest note for a target with no report yet (no model call needed).

    Reached when nothing has entered the reader's top list *and* there is no earlier
    report to carry forward — a new account, or a profile that has not matched
    anything yet. On any later quiet day the previous report stands instead, because
    "the same as yesterday" is more useful than a fresh paragraph saying so.

    "Nothing yet" is a real answer. The alternative — dropping the bar until
    *something* fills the page — is how a daily report trains its reader to stop
    opening it.
    """
    return (
        "Nothing has reached your top list yet, for you or your projects. Mylo will "
        "keep scanning your watched topics and surface papers and opportunities here "
        "as they earn a place — and your feeds and search still hold everything "
        "matched so far."
    )


def generate_report_body(
    profile_text: str,
    categories: list[str],
    personal,
    project_parts: list | None = None,
    *,
    complete: CompleteFn | None = None,
) -> tuple[str, bool]:
    """Assemble the full markdown report body. Returns ``(body, used_llm)``.

    ``personal`` and each entry of ``project_parts`` are
    :class:`apps.content.briefing.ScopePart`\\ s — a label plus that part's found
    items per category. The Personal part runs one section prompt per category that
    has items; each project part is rendered deterministically. The summary prompt
    then writes the opening paragraph over all of it.

    ``used_llm`` is ``True`` when the model wrote any part (so the caller records
    ``origin=llm``); it is ``False`` only when every stage fell back
    deterministically (writer offline).
    """
    used_llm = False
    written: list[tuple[str, str]] = []  # (label shown to the summary prompt, body)
    blocks: list[str] = []

    personal_block, personal_written, from_llm = _personal_block(
        profile_text, categories, personal, complete=complete
    )
    used_llm = used_llm or from_llm
    if personal_block:
        blocks.append(personal_block)
        written.extend(personal_written)

    for part in project_parts or []:
        block, part_written = _project_block(categories, part)
        if block:
            blocks.append(block)
            written.extend(part_written)

    summary, summary_from_llm = write_summary(
        getattr(personal, "counts", {}) or {},
        categories,
        project_parts or [],
        written,
        complete=complete,
    )
    used_llm = used_llm or summary_from_llm
    return "\n\n".join(b for b in ([summary] + blocks) if b).strip(), used_llm


def _personal_block(
    profile_text: str,
    categories: list[str],
    personal,
    *,
    complete: CompleteFn | None,
) -> tuple[str, list[tuple[str, str]], bool]:
    """``## Personal`` with a ``###`` prose section per category that has items."""
    items_by_category = getattr(personal, "items", {}) or {}
    used_llm = False
    written: list[tuple[str, str]] = []
    lines: list[str] = []
    for category in categories:
        items = items_by_category.get(category) or []
        if not items:
            continue
        body, from_llm = write_section(
            category, profile_text, items, complete=complete
        )
        used_llm = used_llm or from_llm
        if not body:
            continue
        label = SECTION_LABELS.get(category, category.title())
        lines.append(f"### {label}")
        lines.append("")
        lines.append(body)
        lines.append("")
        written.append((f"{PERSONAL_HEADING} · {label}", body))
    if not lines:
        return "", [], used_llm
    return (
        "\n".join([f"## {PERSONAL_HEADING}", "", *lines]).rstrip(),
        written,
        used_llm,
    )


def _project_block(categories: list[str], part) -> tuple[str, list[tuple[str, str]]]:
    """``## Project · <name>`` with a deterministic ``###`` section per category.

    A project with nothing new today gets no section at all — it still holds its row
    in the summary table, which is where "nothing today" belongs. Padding the body
    with empty headings is exactly the crowding this report is meant to end.
    """
    items_by_category = getattr(part, "items", {}) or {}
    label = getattr(part, "label", "") or "Project"
    written: list[tuple[str, str]] = []
    lines: list[str] = []
    tally: list[str] = []
    for category in categories:
        items = items_by_category.get(category) or []
        if not items:
            continue
        new_count = (getattr(part, "counts", {}) or {}).get(category, 0)
        noun = SECTION_NOUN.get(category, category)
        phrase = f"{len(items)} {noun}{'' if len(items) == 1 else 's'}"
        if new_count:
            phrase += f" ({new_count} new)"
        tally.append(phrase)
        heading = SECTION_LABELS.get(category, category.title())
        body = _section_fallback(category, items)
        lines.append(f"### {heading}")
        lines.append("")
        lines.append(body)
        lines.append("")
        written.append((f"{label} · {heading}", body))
    if not lines:
        return "", []
    head = [f"## {PROJECT_HEADING_PREFIX}{label}", ""]
    if tally:
        # Plain text, not `_italics_`: neither renderer of this markdown (the app's
        # MarkdownProse, the PDF's flowable builder) handles emphasis, so the
        # underscores reached the reader verbatim.
        head.append(f"{_join_english(tally)}.")
        head.append("")
    return "\n".join([*head, *lines]).rstrip(), written


# --------------------------------------------------------------------------- #
# Per-category section prompts
# --------------------------------------------------------------------------- #


def write_section(
    category: str,
    profile_text: str,
    items: list[dict],
    *,
    complete: CompleteFn | None = None,
) -> tuple[str, bool]:
    """One area specialist's markdown section body. Returns ``(body, from_llm)``."""
    if not items:
        return "", False
    system = _SECTION_SYSTEM_PROMPT.get(category)
    if system is None:
        return _section_fallback(category, items), False
    # A lab report's items carry who they suit; a personal report's never do, so
    # the rule is added only where it applies and the personal prompt is unchanged.
    if any(item.get("for_members") for item in items):
        system += _MEMBER_RULES

    ask = complete if complete is not None else _settings_complete(_SECTION_MAX_TOKENS)
    prompt = _section_prompt(category, profile_text, items)
    try:
        raw = ask(system, prompt)
    except Exception as exc:  # noqa: BLE001 — any LLM failure => deterministic body
        logger.warning(
            "LLM %s-section writer unavailable (%s); using fallback.", category, exc
        )
        raw = None
    body = _strip_headings(_clean_block(raw))
    if body:
        return body, True
    return _section_fallback(category, items), False


def _cluster_groups(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group items by their attributed cluster, order-preserving.

    Returns ``[(cluster_label, items)]``. When fewer than two distinct clusters
    carry a label (opportunities, or a single/no-cluster profile) it returns one
    unlabelled group, so grouping is a no-op there.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in items:
        label = str(item.get("cluster_label") or "")
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(item)
    labelled = [label for label in order if label]
    if len(labelled) < 2:
        return [("", items)]
    return [(label, groups[label]) for label in order if groups[label]]


def _section_prompt(category: str, profile_text: str, items: list[dict]) -> str:
    label = SECTION_LABELS.get(category, category.title())
    groups = _cluster_groups(items)
    grouped = len(groups) > 1
    lines = [
        f"Researcher profile:\n{profile_text or '(no profile details)'}",
        "",
        f"The reader's top {label} today — reference ONLY these, by title. "
        "Items marked NEW have just entered this list; lead with those and give "
        "them the most space, then place them among the rest:",
    ]
    index = 1
    for cluster_label, group in groups:
        if grouped and cluster_label:
            lines.append(f"\nFor the researcher's {cluster_label} focus:")
        for item in group:
            lines.append(_item_brief(index, item))
            index += 1
    lines.append("")
    if grouped:
        lines.append(
            f"Write the {label} section body now, organised BY the focus clusters "
            "above — a short lead-in per cluster (e.g. \"In your Medical AI Agents "
            "focus: …\"), then its papers. Keep the cluster names verbatim."
        )
    else:
        lines.append(f"Write the {label} section body now.")
    return "\n".join(lines)


def _item_brief(index: int, item: dict) -> str:
    title = item.get("title") or "(untitled)"
    head = f'[{index}] "{title}"'
    tail: list[str] = []
    match = item.get("match_percent")
    if isinstance(match, int):
        tail.append(f"{match}% match")
    if item.get("is_entrant"):
        tail.append("NEW to your top list")
    if item.get("deadline_date"):
        tail.append(f"deadline {item['deadline_date']}")
    if tail:
        head += " — " + " · ".join(tail)
    url = item.get("url")
    if url:
        head += f"\n    URL: {url}"
    reason = item.get("reason") or item.get("headline")
    if reason:
        head += f"\n    Prior note: {reason}"
    for_members = item.get("for_members") or []
    if for_members:
        head += f"\n    Best suited to: {', '.join(for_members)}"
    return head


def _section_fallback(category: str, items: list[dict]) -> str:
    """A deterministic markdown section body when the model is unavailable.

    Grouped by focus cluster when the items carry >= 2 distinct clusters (papers),
    so the fallback mirrors the grouped write-up the model would have produced.
    """
    groups = _cluster_groups(items)
    grouped = len(groups) > 1
    blocks: list[str] = []
    for cluster_label, group in groups:
        if grouped and cluster_label:
            blocks.append(f"**In your {cluster_label} focus:**")
        for item in group:
            title = item.get("title") or "(untitled)"
            url = item.get("url")
            heading = f"[{title}]({url})" if url else title
            meta: list[str] = []
            match = item.get("match_percent")
            if isinstance(match, int):
                meta.append(f"{match}% match")
            if item.get("deadline_date"):
                meta.append(f"deadline {item['deadline_date']}")
            line = f"**{heading}**"
            if meta:
                line += " — " + " · ".join(meta)
            reason = item.get("reason") or item.get("headline")
            if reason:
                line += f"\n\n{reason}"
            for_members = item.get("for_members") or []
            if for_members:
                line += f"\n\nBest suited to: {_join_english(for_members)}."
            blocks.append(line)
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Summary prompt (the opening paragraph)
# --------------------------------------------------------------------------- #


def write_summary(
    personal_counts: dict[str, int],
    categories: list[str],
    project_parts: list,
    sections: list[tuple[str, str]],
    *,
    complete: CompleteFn | None = None,
) -> tuple[str, bool]:
    """The editor's opening paragraph over the sections. ``(text, from_llm)``."""
    ask = complete if complete is not None else _settings_complete(_SUMMARY_MAX_TOKENS)
    prompt = _summary_prompt(personal_counts, categories, project_parts, sections)
    try:
        raw = ask(_SUMMARY_SYSTEM_PROMPT, prompt)
    except Exception as exc:  # noqa: BLE001 — any LLM failure => deterministic lead
        logger.warning("LLM summary writer unavailable (%s); using fallback.", exc)
        raw = None
    text = _strip_headings(_clean_block(raw))
    if text:
        return text, True
    return _summary_fallback(personal_counts, categories, project_parts), False


def _summary_prompt(
    personal_counts: dict[str, int],
    categories: list[str],
    project_parts: list,
    sections: list[tuple[str, str]],
) -> str:
    lines = ["What is new for this researcher today:"]
    for category in categories:
        lines.append(
            f"- {SECTION_LABELS.get(category, category)}: "
            f"{personal_counts.get(category, 0)} new."
        )
    active = [p for p in project_parts if getattr(p, "total", 0)]
    if active:
        lines.append("")
        lines.append("On their projects:")
        for part in active:
            counts = getattr(part, "counts", {}) or {}
            tally = ", ".join(
                f"{counts.get(c, 0)} {SECTION_LABELS.get(c, c).lower()}"
                for c in categories
                if counts.get(c, 0)
            )
            lines.append(f"- {getattr(part, 'label', 'Project')}: {tally}.")
    lines.append("")
    if sections:
        lines.append("The detail sections that will follow your paragraph:")
        for label, body in sections:
            lines.append(f"\n### {label}\n{body}")
    else:
        lines.append("No detail sections were written today.")
    lines.append("\nWrite the opening paragraph now.")
    return "\n".join(lines)


def _summary_fallback(
    personal_counts: dict[str, int],
    categories: list[str],
    project_parts: list,
) -> str:
    """A deterministic opening paragraph when the model is unavailable."""
    personal_total = sum(personal_counts.get(c, 0) for c in categories)
    active = [p for p in project_parts if getattr(p, "total", 0)]
    if not personal_total and not active:
        return empty_report_body()

    def _noun(category: str, n: int) -> str:
        noun = SECTION_NOUN.get(category, category)
        return noun if n == 1 else f"{noun}s"

    parts = [
        f"{personal_counts[category]} new {_noun(category, personal_counts[category])}"
        for category in categories
        if personal_counts.get(category)
    ]
    lead = (
        "Today Mylo surfaced " + _join_english(parts) + " for you."
        if parts
        else "Nothing new cleared the bar for you personally today."
    )
    if active:
        named = _join_english(
            [
                f"{getattr(p, 'label', 'a project')} ({p.total})"
                for p in active[:3]
            ]
        )
        more = f", and {len(active) - 3} more" if len(active) > 3 else ""
        lead += f" Your projects picked up {named}{more}."
    return lead


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _join_english(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return "nothing"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _clean_block(raw: str | None) -> str:
    """Strip whitespace and any wrapping ```/```markdown code fences."""
    if not raw:
        return ""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _strip_headings(text: str) -> str:
    """Drop any leading markdown ``#`` headings a section/summary prompt added.

    The report owns the ``## Label`` headings, so a stray one from a prompt would
    double up; the summary must be a plain paragraph. Only leading heading lines
    are removed — headings mid-body are left alone.
    """
    if not text:
        return ""
    lines = text.splitlines()
    start = 0
    while start < len(lines) and (
        not lines[start].strip() or lines[start].lstrip().startswith("#")
    ):
        start += 1
    return "\n".join(lines[start:]).strip()


def _settings_complete(max_tokens: int) -> CompleteFn:
    """Default seam: route one (system, user) exchange through the LLM client."""

    def _complete(system: str, user: str) -> str | None:
        from apps.core.llm import LLMMessage, build_llm_client

        client = build_llm_client(component="briefing")
        response = client.complete(
            [LLMMessage("system", system), LLMMessage("user", user)],
            max_tokens=max_tokens,
        )
        if response.finish_reason == "length" and not (response.content or "").strip():
            logger.warning(
                "LLM report response truncated (finish_reason=length) before any "
                "answer; raise LLM_MAX_TOKENS so the model can finish."
            )
        return response.content

    return _complete
