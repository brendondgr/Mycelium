"""Sectioned daily-report writer for the Mylo Report.

The single-shot briefing synthesizer (one prompt over per-category counts) is
replaced here by a fan-out of five prompts — one per research surface, plus one
that writes the opening paragraph over their output:

- Four **per-category section prompts** — Paper, Grant, Fellowship, Conference —
  each receive the researcher's profile and *only their* area's found items (title,
  match, deadline, and the per-item tailored rationale already written and persisted
  on the :class:`~apps.content.models.RelevanceScore`) and write a grounded markdown
  section body explaining, item by item, why it fits *this* researcher and how it
  maps onto their interests and projects.
- A **fifth prompt** reads the day's counts and the four section bodies and writes
  the opening paragraph — how many of each kind surfaced and what stood out — which
  then *leads* the assembled report.

The fan-out is one pass: the prompts are independent, their results are
concatenated once, and nothing plans, calls a tool, loops, or reflects.

The assembled body is GitHub-flavored markdown: the summary paragraph, then a
``## Heading`` + body for each non-empty area. Everything is **grounded** (each
prompt sees only real items) and every stage has a **deterministic markdown
fallback**, so a missing or flaky model degrades to a still-useful, honest report
rather than nothing — the same contract as :mod:`apps.content.suggest` /
:mod:`apps.content.opportunity_llm`.

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

#: How many items per area the section prompt writes up (a little more than the
#: bottom-right UI showcase, which stays at 3).
REPORT_ITEMS_PER_SECTION = 6

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
    "editor of a daily report. You are given the day's per-category counts and the "
    "already-written detail sections. Write ONLY the opening paragraph of the report "
    "(2-4 sentences, plain prose, no markdown heading and no lists): say how many "
    "new items of each kind surfaced today, name a couple of the standouts by title, "
    "and set up the detail that follows. LEAD with what is NEW; the running totals "
    "are background. Be warm, calm, and specific. Ground every statement ONLY in the "
    "counts and sections you are given; never invent a title, number, or deadline."
)


# --------------------------------------------------------------------------- #
# Public orchestration
# --------------------------------------------------------------------------- #


def empty_report_body() -> str:
    """The honest note for a day with no matched items (no model call needed)."""
    return (
        "No new research matched your profile today. Mylo will keep scanning your "
        "watched topics and surface fresh papers and opportunities here as they "
        "appear."
    )


def generate_report_body(
    profile_text: str,
    categories: list[str],
    counts: dict[str, int],
    new_counts: dict[str, int],
    items_by_category: dict[str, list[dict]],
    *,
    complete: CompleteFn | None = None,
) -> tuple[str, bool]:
    """Assemble the full markdown report body. Returns ``(body, used_llm)``.

    Runs one section prompt per watched category that actually has items, then the
    summary prompt over those section bodies. ``used_llm`` is ``True`` when the
    model wrote any part (so the caller records ``origin=llm``); it is ``False``
    only when every stage fell back deterministically (writer offline).
    """
    by_cluster = group_by_cluster(items_by_category, categories)
    if by_cluster is not None:
        return _cluster_first_body(
            profile_text,
            categories,
            counts,
            new_counts,
            items_by_category,
            by_cluster,
            complete=complete,
        )

    used_llm = False
    sections: list[tuple[str, str]] = []  # (label, body markdown)
    for category in categories:
        items = items_by_category.get(category) or []
        if not items:
            continue
        body, from_llm = write_section(
            category, profile_text, items, complete=complete
        )
        used_llm = used_llm or from_llm
        if body:
            sections.append((SECTION_LABELS.get(category, category.title()), body))

    summary, summary_from_llm = write_summary(
        counts, new_counts, categories, items_by_category, sections, complete=complete
    )
    used_llm = used_llm or summary_from_llm

    blocks: list[str] = [summary] if summary else []
    for label, body in sections:
        blocks.append(f"## {label}\n\n{body}")
    return "\n\n".join(b for b in blocks if b).strip(), used_llm


def group_by_cluster(
    items_by_category: dict[str, list[dict]], categories: list[str]
) -> dict[str, dict[str, list[dict]]] | None:
    """Pivot ``{category: items}`` into ``{cluster_label: {category: items}}``.

    Returns ``None`` when the report should stay category-first: fewer than two
    themes carry items, or some items have no attribution at all. That second
    condition is the one that matters — a half-attributed report would put some
    grants under a theme and silently strand the rest, which reads as a bug to
    whoever is looking at it. Better the whole report keeps its old shape than
    that it becomes quietly incomplete.
    """
    grouped: dict[str, dict[str, list[dict]]] = {}
    order: list[str] = []
    for category in categories:
        for item in items_by_category.get(category) or []:
            label = str(item.get("cluster_label") or "")
            if not label:
                return None  # unattributed item — do not half-organise the report
            if label not in grouped:
                grouped[label] = {}
                order.append(label)
            grouped[label].setdefault(category, []).append(item)
    if len(order) < 2:
        return None
    return {label: grouped[label] for label in order}


def _cluster_first_body(
    profile_text: str,
    categories: list[str],
    counts: dict[str, int],
    new_counts: dict[str, int],
    items_by_category: dict[str, list[dict]],
    by_cluster: dict[str, dict[str, list[dict]]],
    *,
    complete: CompleteFn | None,
) -> tuple[str, bool]:
    """One ``## <Theme>`` section per research cluster, categories inside it.

    A researcher does not think in *paper / grant / conference* — they think in the
    themes they work on and want to know what each one brought today. With every
    content type now carrying cluster attribution, the report can finally be
    organised the way the work is.

    Each category's section prompt still writes its own prose; it is simply handed
    one theme's slice at a time. That costs one model call per populated
    (theme, category) pair instead of per category — more calls, but each with a
    tighter, more coherent set of items to write about, and every one of them keeps
    its deterministic fallback.
    """
    used_llm = False
    section_bodies: list[tuple[str, str]] = []
    blocks: list[str] = []

    for label, per_category in by_cluster.items():
        lines = [f"## {label}", ""]
        tally = [
            f"{len(items)} {SECTION_NOUN.get(cat, cat)}{'' if len(items) == 1 else 's'}"
            for cat, items in per_category.items()
            if items
        ]
        if tally:
            lines.append(f"_{_join_english(tally)} today._")
            lines.append("")
        for category in categories:
            items = per_category.get(category) or []
            if not items:
                continue
            body, from_llm = write_section(
                category, profile_text, items, complete=complete
            )
            used_llm = used_llm or from_llm
            if not body:
                continue
            heading = SECTION_LABELS.get(category, category.title())
            lines.append(f"**{heading}**")
            lines.append("")
            lines.append(body)
            lines.append("")
            section_bodies.append((f"{label} · {heading}", body))
        blocks.append("\n".join(lines).rstrip())

    summary, summary_from_llm = write_summary(
        counts,
        new_counts,
        categories,
        items_by_category,
        section_bodies,
        complete=complete,
    )
    used_llm = used_llm or summary_from_llm
    return "\n\n".join(b for b in ([summary] + blocks) if b).strip(), used_llm


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
        f"Today's new {label} matches — reference ONLY these, by title:",
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
    if item.get("is_new"):
        tail.append("new")
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
    counts: dict[str, int],
    new_counts: dict[str, int],
    categories: list[str],
    items_by_category: dict[str, list[dict]],
    sections: list[tuple[str, str]],
    *,
    complete: CompleteFn | None = None,
) -> tuple[str, bool]:
    """The editor's opening paragraph over the sections. ``(text, from_llm)``."""
    ask = complete if complete is not None else _settings_complete(_SUMMARY_MAX_TOKENS)
    prompt = _summary_prompt(counts, new_counts, categories, sections)
    try:
        raw = ask(_SUMMARY_SYSTEM_PROMPT, prompt)
    except Exception as exc:  # noqa: BLE001 — any LLM failure => deterministic lead
        logger.warning("LLM summary writer unavailable (%s); using fallback.", exc)
        raw = None
    text = _strip_headings(_clean_block(raw))
    if text:
        return text, True
    return _summary_fallback(counts, new_counts, categories, items_by_category), False


def _summary_prompt(
    counts: dict[str, int],
    new_counts: dict[str, int],
    categories: list[str],
    sections: list[tuple[str, str]],
) -> str:
    lines = ["Today's counts for this researcher:"]
    for category in categories:
        total = counts.get(category, 0)
        new = new_counts.get(category, 0)
        lines.append(
            f"- {SECTION_LABELS.get(category, category)}: {new} new, "
            f"{total} matched in total."
        )
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
    counts: dict[str, int],
    new_counts: dict[str, int],
    categories: list[str],
    items_by_category: dict[str, list[dict]],
) -> str:
    """A deterministic opening paragraph when the model is unavailable."""
    total = sum(counts.get(c, 0) for c in categories)
    if total == 0:
        return empty_report_body()

    def _noun(category: str, n: int) -> str:
        noun = SECTION_NOUN.get(category, category)
        return noun if n == 1 else f"{noun}s"

    parts: list[str] = []
    for category in categories:
        count = counts.get(category, 0)
        if not count:
            continue
        new = new_counts.get(category, 0)
        if new:
            parts.append(f"{new} new {_noun(category, new)} ({count} matched in total)")
        else:
            parts.append(f"{count} {_noun(category, count)}")
    lead = "Today Mylo surfaced " + _join_english(parts) + " for you."

    highlights: list[str] = []
    for category in categories:
        items = items_by_category.get(category) or []
        if not items:
            continue
        top = items[0]
        match = top.get("match_percent")
        match_str = f" ({match}% match)" if isinstance(match, int) else ""
        noun = SECTION_NOUN.get(category, category)
        highlights.append(f'the {noun} "{top.get("title")}"{match_str}')
    if highlights:
        lead += " Standouts include " + _join_english(highlights[:3]) + "."
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
