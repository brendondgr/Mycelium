"""Compose the Mylo Report body: theme → what is new → what is standing.

The document used to be organised **part → category → items**, with the research
theme buried at the fourth heading level as a pill and the written briefing
sitting apart from the listings it described, repeating them item for item. A
reader got the same content twice and learned to skip the prose half.

It is organised by **theme** now, and the prose sits next to what it describes:

``<lead paragraph>``
    Mylo's one paragraph over the whole day (:mod:`apps.content.narrative`,
    Prompt D). Paid only; a free report opens on the cover table instead.
``## <theme>``
    One section per research theme **that has news**. A theme with a standing
    slate but nothing new is one line in the quiet list at the end; a theme with
    no matches at all appears nowhere. Neither is padded.
``<Mylo's read on this theme>``
    Two to four sentences (Prompt C) on what this strand's news amounts to.
``### <category>``
    What entered this theme's slate today, grouped by category.
``N. **[Title](url)** — **NEW** · Read · deadline YYYY-MM-DD``
    One entrant, followed on the next line by the **first beat** of its reason.
    The remaining beats and the mandatory caveat live on the web entry, where a
    reader who wants depth has asked for it. There is no percentage anywhere: the
    number implied a measurement nobody made, so position within a theme plus a
    four-point verdict (:mod:`apps.content.verdicts`) carries the judgement.
``### Currently in your list``
    The theme's standing slate as compact reference rows — position, title,
    source, deadline. No reasons, no verdicts, no prose. It serves the reader who
    skipped three days without letting settled items dominate a document whose
    job is to report change.

Projects stay flat and entrant-only (open decision OD3): they rarely declare
themes of their own, and inheriting the parent's would attribute a project's
matches to a strand the project never declared. They are still written
deterministically from the persisted write-ups — a reader on six projects would
otherwise cost six times the model budget for prose restating rationale they are
scanning rather than reading.

Everything is **grounded** (nothing here invents an item) and every stage has a
deterministic fallback, so a missing or flaky model degrades to a still-useful,
honest report — the same contract as :mod:`apps.content.suggest` and
:mod:`apps.content.opportunity_llm`.

The body is GitHub-flavored markdown in a fixed, narrow grammar that both
renderers — the PDF's flowable builder and the app's ``MarkdownProse`` — parse
exactly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from . import narrative
from .verdicts import VERDICT_LABELS

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


def hidden_projects_note(count: int) -> str:
    """The one line a shared surface owes a reader it is holding projects back from.

    A lab report lists only projects opted into ``share_in_lab_reports``. A reader
    who knows the lab runs six projects and sees one should be told the difference
    is a sharing setting, not a quiet day — and told it without naming what is
    hidden, which would defeat the point.
    """
    if count <= 0:
        return ""
    noun = "project" if count == 1 else "projects"
    return f"_{count} private {noun} not shown._"


def generate_report_body(
    profile_text: str,
    categories: list[str],
    personal,
    project_parts: list | None = None,
    *,
    complete: CompleteFn | None = None,
    narrative: dict | None = None,
    hidden_projects: int = 0,
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
    payload = narrative or {}
    apply_narrative(personal, payload)
    used_llm = payload.get("lead_origin") == "llm" or any(
        entry.get("origin") == "llm" for entry in (payload.get("themes") or [])
    )
    blocks: list[str] = theme_blocks(personal, categories)
    if not blocks and getattr(personal, "items", None):
        # No theme sections, but the part holds items: rows written before the
        # per-cluster run existed carry no slate keys yet. One nightly run rewrites
        # them, and until it does the reader gets the flat listing rather than a
        # document that reports nothing on a day that had news.
        flat, _written = _flat_block(
            getattr(personal, "label", "") or PERSONAL_HEADING, categories, personal
        )
        if flat:
            blocks.append(flat)
    quiet = quiet_line(personal)
    if quiet:
        blocks.append(quiet)

    for part in project_parts or []:
        block, _part_written = _project_block(categories, part)
        if block:
            blocks.append(block)

    note = hidden_projects_note(hidden_projects)
    if note:
        blocks.append(note)

    lead = (payload.get("lead") or "").strip()
    if not blocks and not lead:
        return "", used_llm
    return "\n\n".join(b for b in ([lead] + blocks) if b).strip(), used_llm


def write_narrative(
    profile_text: str,
    personal,
    clusters: Sequence,
    *,
    complete: CompleteFn | None = None,
    entitled: bool = False,
) -> dict:
    """Mylo's prose for one run, as structure rather than markdown.

    Returns ``{"lead", "lead_origin", "themes": [{cluster_id, label, read,
    origin}]}`` — stored once on the :class:`~apps.content.models.DailyBriefing`
    and read back by the PDF, the app, and the Discord message, so the three can
    never carry different wordings of the same day and a re-render never re-bills
    the model for prose that already exists.

    Unentitled targets get ``{}``: the deterministic report is the baseline
    product, and its opening is the cover table, which is honest.
    """
    if not entitled:
        return {}
    themes: list[dict] = []
    reads: list[tuple[str, str]] = []
    interests_by_id = {
        getattr(c, "id", ""): list(getattr(c, "areas", []) or []) for c in clusters
    }
    for section in getattr(personal, "live_themes", []):
        entrants = [
            {
                "title": item.get("title", ""),
                "verdict": item.get("verdict") or "",
                "lead": item.get("lead", ""),
                "caveat": item.get("caveat", ""),
            }
            for items in section.entrants.values()
            for item in items
        ]
        read, origin = narrative.write_theme_read(
            profile_text,
            section.label,
            interests_by_id.get(section.cluster_id, []),
            entrants,
            complete=complete,
        )
        if not read:
            continue
        section.read = read
        section.read_origin = origin
        themes.append(
            {
                "cluster_id": section.cluster_id,
                "label": section.label,
                "read": read,
                "origin": origin,
            }
        )
        reads.append((section.label, read))

    lead, lead_origin = narrative.write_lead(
        profile_text, reads, complete=complete
    )
    return {
        "lead": lead,
        "lead_origin": lead_origin,
        "themes": themes,
        "version": narrative.NARRATIVE_VERSION,
    }


def apply_narrative(personal, payload: dict | None) -> None:
    """Copy stored prose back onto freshly-gathered theme sections.

    The report is compiled twice a day at most, and never by the stage that wrote
    the prose. Reading it back rather than regenerating is the same rule the
    write-ups follow: a model call happens once per artefact.
    """
    reads = {
        entry.get("cluster_id"): entry
        for entry in ((payload or {}).get("themes") or [])
        if isinstance(entry, dict)
    }
    for section in getattr(personal, "themes", []):
        entry = reads.get(section.cluster_id)
        if entry:
            section.read = entry.get("read", "")
            section.read_origin = entry.get("origin", "")


def theme_blocks(part, categories: list[str]) -> list[str]:
    """One markdown block per theme with news — the report's body.

    ``## <theme>`` then Mylo's read, then ``### <Category>`` listings of what
    entered, then the standing reference block. A theme with no news produces
    nothing here; it appears once in the quiet line at the end, and a theme with
    no matches at all appears nowhere, which is the honest rendering of "nothing
    was found for this".
    """
    blocks: list[str] = []
    for section in getattr(part, "live_themes", []):
        lines = [f"## {section.label}", ""]
        if section.read:
            lines.append(section.read)
            lines.append("")
        for category in categories:
            entrants = section.entrants.get(category) or []
            if not entrants:
                continue
            lines.append(f"### {SECTION_LABELS.get(category, category.title())}")
            lines.append("")
            for index, item in enumerate(entrants, start=1):
                lines.append(_numbered_item(index, item))
                lines.append("")
        standing = [
            item
            for category in categories
            for item in (section.standing.get(category) or [])
        ]
        if standing:
            lines.append("### Currently in your list")
            lines.append("")
            lines.append(
                "Unchanged since you last looked — listed for reference, with no "
                "new commentary."
            )
            lines.append("")
            for item in standing:
                lines.append(_standing_row(item))
            lines.append("")
        blocks.append("\n".join(lines).rstrip())
    return blocks


def _standing_row(item: dict) -> str:
    """One compact reference row: position, linked title, source, deadline.

    No reason, no verdict, no prose. The block serves the reader who skipped
    three days; letting settled items carry commentary is how a document whose
    job is to report change ends up dominated by things that did not.
    """
    title = item.get("title") or "(untitled)"
    url = item.get("url")
    linked = f"[{title}]({url})" if url else title
    bits = [f"{item.get('position') or '–'}."]
    bits.append(linked)
    if item.get("source_name"):
        bits.append(f"({item['source_name']})")
    if item.get("deadline_date"):
        bits.append(f"— deadline {item['deadline_date']}")
    return "- " + " ".join(bits)


def quiet_line(part) -> str:
    """The one line that carries every theme holding a slate but nothing new."""
    quiet = getattr(part, "quiet", []) or []
    if not quiet:
        return ""
    named = ", ".join(f"{label} ({count} standing)" for label, count in quiet)
    return f"**Quiet today:** {named}."


def _flat_block(
    heading: str, categories: list[str], part
) -> tuple[str, list[tuple[str, str]]]:
    """``## <heading>`` with a deterministic ``###`` section per category.

    The flat shape, kept for the two surfaces that are deliberately not organised
    by theme: a project (which declares no themes of its own) and the transitional
    case of a part whose rows predate per-cluster slates.
    """
    items_by_category = getattr(part, "items", {}) or {}
    written: list[tuple[str, str]] = []
    lines: list[str] = []
    for category in categories:
        items = items_by_category.get(category) or []
        if not items:
            continue
        label = SECTION_LABELS.get(category, category.title())
        body = _section_fallback(category, items)
        lines.append(f"### {label}")
        lines.append("")
        lines.append(body)
        lines.append("")
        written.append((f"{heading} · {label}", body))
    if not lines:
        return "", []
    return "\n".join([f"## {heading}", "", *lines]).rstrip(), written


def _project_block(categories: list[str], part) -> tuple[str, list[tuple[str, str]]]:
    """``## Project · <name>`` — the flat shape, entrants only.

    Projects stay flat (open decision OD3): they rarely declare research themes of
    their own, and inheriting the parent's would attribute a project's matches to
    a strand the project never declared. Structurally it is still the same
    ``###`` category headings and the same numbered items as a theme section, so a
    reader does not have to learn the document twice.

    A project with nothing new today gets no section at all — it still holds its
    row in the summary table, which is where "nothing today" belongs. Padding the
    body with empty headings is exactly the crowding this report is ending.
    """
    label = getattr(part, "label", "") or "Project"
    return _flat_block(f"{PROJECT_HEADING_PREFIX}{label}", categories, part)


# --------------------------------------------------------------------------- #
# Per-category section prompts
# --------------------------------------------------------------------------- #


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


def _cluster_heading(cluster_label: str) -> str:
    """The ``####`` heading that opens one focus-cluster group.

    The theme's own name and nothing else. "In your … focus" was a sentence, and a
    sentence set in heading position reads as body text no matter how it is styled;
    the renderers give the bare label the weight of a heading instead.
    """
    return f"#### {cluster_label}"


def _numbered_item(index: int, item: dict) -> str:
    """One ranked item in the report's two-line item grammar.

    Line one is the rank, the linked title, and the two facts a reader scans a
    ranked list for — whether it is new, and how well it matches. Line two is the
    rationale the matcher already wrote. Both renderers key off this shape, so it is
    also exactly what the section prompt is told to produce.
    """
    title = item.get("title") or "(untitled)"
    url = item.get("url")
    linked = f"[{title}]({url})" if url else title
    meta: list[str] = []
    if item.get("is_entrant"):
        meta.append("**NEW**")
    verdict = item.get("verdict")
    if verdict in VERDICT_LABELS:
        meta.append(VERDICT_LABELS[verdict])
    for label in item.get("bridge_labels") or []:
        meta.append(f"also in {label}")
    if item.get("deadline_date"):
        meta.append(f"deadline {item['deadline_date']}")
    line = f"{index}. **{linked}**"
    if meta:
        line += " — " + " · ".join(meta)
    # The lead beat only, matching the printed report: the remaining beats and the
    # caveat live on the web entry, where a reader who wants depth has asked for it.
    reason = item.get("lead") or item.get("reason") or item.get("headline")
    if reason:
        line += f"\n{reason}"
    return line


def _section_fallback(category: str, items: list[dict]) -> str:
    """A deterministic markdown section body when the model is unavailable.

    Grouped by focus cluster when the items carry >= 2 distinct clusters (papers),
    so the fallback mirrors the grouped write-up the model would have produced —
    same ``####`` headings, same numbering, same item grammar. This is also what
    every project section is built from, which is why the two read alike.
    """
    groups = _cluster_groups(items)
    grouped = len(groups) > 1
    blocks: list[str] = []
    index = 1
    for cluster_label, group in groups:
        if grouped and cluster_label:
            blocks.append(_cluster_heading(cluster_label))
        for item in group:
            blocks.append(_numbered_item(index, item))
            index += 1
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Summary prompt (the opening paragraph)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


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
