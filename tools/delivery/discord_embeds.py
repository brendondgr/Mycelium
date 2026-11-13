"""The Discord post: what Mylo found, said before any number, then the numbers.

Both posts used to open on a tally. The personal DM led with Mylo's paragraph and
then listed a count per theme; the lab post listed only counts per theme. Neither
answered the question a reader actually opens the message with — *was that a lot
or a little, and where did it land?* — because a count with nothing behind it
cannot. "Knowledge graphs & agents — 5 papers" is the same five whether Mylo read
two thousand papers and kept five, or read forty and kept five.

So every post is now, in order:

1. **An overview**, ≤ 600 characters, in Mylo's voice — what kind of day it was.
2. **Needs attention**, when something does.
3. **The top of the day**, as links.
4. **Statistics**: overnight volume, how selective the match was, what entered a
   top list, alerts, then the splits by category, project and theme, then the
   deadline horizon.

Everything here is rendering. Not one number is computed in this module: they all
arrive on :class:`~tools.delivery.report_stats.ReportStats`, which was derived from
the same report the attached PDF renders, so the post and the document cannot
quote different totals for the same morning.

Two safety rules are inherited rather than re-implemented and must stay that way:
``allowed_mentions.parse == []`` is forced in ``discord_api.create_message``, and
:func:`~tools.delivery.reminders_discord.escape_mentions` neutralises every scraped
title interpolated here. Mylo never tags anyone.

:func:`fit_embed` is the last thing every producer calls. Discord rejects an
oversized embed outright — the whole post fails, not the long field — so the limits
are enforced here by dropping **whole lines and whole fields**, never by cutting a
sentence in half. A post that says "…and 3 more themes" reads as an editor's
decision; one that stops mid-word reads as a delivery failure.
"""

from __future__ import annotations

from tools.delivery.reminders_discord import escape_mentions
from tools.delivery.report_stats import ReportStats

#: Mycelium green, matching every other embed Mylo sends.
BRAND_COLOR = 0x3B7A57

# Discord's documented ceilings. Enforced together, because the 6000-character
# total is what actually fails a post that passes every individual limit.
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
MAX_FIELDS = 25
TOTAL_LIMIT = 6000

#: The overview's own ceiling — well inside Discord's, because the point is that
#: it is read in the channel rather than opened.
OVERVIEW_LIMIT = 600

#: How many linked items the "top of the day" field carries.
TOP_ITEMS = 3
#: How many alert lines "Needs attention" carries before it summarises the rest.
MAX_ALERT_LINES = 3

CATEGORY_LABELS = {
    "papers": "Papers",
    "grants": "Grants",
    "fellowships": "Fellowships",
    "conferences": "Conferences",
}


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def trim_to_sentence(text: str, limit: int = OVERVIEW_LIMIT) -> str:
    """Cut ``text`` to ``limit`` characters **at a sentence boundary**.

    A paragraph that stops mid-clause reads as a bug in the product rather than a
    length limit, and the overview is the first thing anyone reads. Falls back to a
    word boundary with an ellipsis only when there is no sentence end to cut at —
    a single very long sentence — which is rarer than it is worth mangling for.
    """
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut > limit // 3:
        return window[: cut + 1].strip()
    return window[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def overview_text(lead: str, stats: ReportStats, *, fallback_subject: str) -> str:
    """Mylo's opening, or a deterministic stand-in when there is no prose.

    The stored ``narrative.lead`` is reused rather than regenerated: a model call
    happens once per run, and the post, the PDF and the web page must carry one
    wording of the same day. An unentitled reader has no lead at all, and a fresh
    account has none yet, so the fallback is built from what the day actually was —
    the busiest theme and how much entered — which is a smaller claim than the
    model's but a true one.
    """
    lead = trim_to_sentence(lead)
    if lead:
        return lead
    if not stats.entered:
        return (
            f"Nothing new entered {fallback_subject} top lists today. "
            "Mylo keeps watching."
        )
    top = stats.by_theme[0][0] if stats.by_theme else ""
    noun = "item" if stats.entered == 1 else "items"
    if top:
        return (
            f"{stats.entered} {noun} entered {fallback_subject} top lists today, "
            f"led by {top}."
        )
    return f"{stats.entered} {noun} entered {fallback_subject} top lists today."


def volume_line(stats: ReportStats, *, subject: str, period: str) -> str:
    """"Mylo read 2,140 new papers …" — the sentence that makes the rest legible.

    Written as one sentence rather than a table because it is a ratio, not a set
    of independent figures: read, matched, entered, raised. Omits the corpus
    totals entirely when the collector could not answer, rather than printing a
    zero that would read as "Mylo found nothing".
    """
    parts: list[str] = []
    if stats.has_volume:
        read: list[str] = []
        if stats.discovered_papers is not None:
            noun = "paper" if stats.discovered_papers == 1 else "papers"
            read.append(f"{stats.discovered_papers:,} new {noun}")
        if stats.discovered_opportunities is not None:
            noun = "update" if stats.discovered_opportunities == 1 else "updates"
            read.append(
                f"{stats.discovered_opportunities:,} opportunity {noun}"
            )
        if read:
            parts.append(f"Mylo read {' and '.join(read)}.")
    matched = f"{stats.matched} matched {subject}"
    entered = (
        f"{stats.entered} entered a top list"
        if stats.entered != 1
        else "1 entered a top list"
    )
    if stats.alerts:
        raised = (
            f"{stats.alerts} raised alerts"
            if stats.alerts != 1
            else "1 raised an alert"
        )
    else:
        raised = "none raised alerts"
    parts.append(f"{matched}, {entered}, and {raised}.")
    return " ".join(parts) or f"Nothing new {period}."


def _pairs(stats: ReportStats) -> str:
    """"Papers 6 · 128  |  Grants 0 · 44" — new, then what the feed holds."""
    cells = [
        f"{CATEGORY_LABELS.get(category, category.title())} {new} · {total}"
        for category, (new, total) in stats.by_category.items()
    ]
    return "  |  ".join(cells)


def _project_line(stats: ReportStats, *, projects_only: bool = False) -> str:
    """"Personal 3 · —  |  Synapse 3 · 2" — what entered where, and what it raised.

    ``projects_only`` drops the aggregate row. A lab post has already given the
    lab's own totals in the two fields above it, so repeating them under "Shared
    projects" would make the lab look like one of its own projects.
    """
    cells = []
    for label, new, alerts in stats.by_project:
        if projects_only and label == stats.aggregate_label:
            continue
        alert = "—" if not alerts else str(alerts)
        cells.append(f"{escape_mentions(label)} {new} · {alert}")
    return "  |  ".join(cells)


def _theme_line(stats: ReportStats) -> str:
    return " · ".join(
        f"{escape_mentions(label)} {count}" for label, count in stats.by_theme
    )


def _deadline_line(stats: ReportStats) -> str:
    if not stats.deadlines_in_window:
        return "None."
    nearest = stats.nearest_deadline or {}
    title = escape_mentions(str(nearest.get("title") or "")).strip()
    due = str(nearest.get("due_date") or "")
    if not title:
        return str(stats.deadlines_in_window)
    return f"{stats.deadlines_in_window} · nearest: {title}, {due}"


def _linked(title: str, url: str) -> str:
    """A markdown link with the title neutralised. Never a bare scraped string."""
    safe = escape_mentions(" ".join((title or "").split())) or "(untitled)"
    # A ']' inside a link label ends the label early and the rest leaks out as
    # literal punctuation, so the two bracket characters are the one thing
    # rewritten rather than escaped — Discord does not honour backslash escapes
    # inside a link label.
    safe = safe.replace("[", "(").replace("]", ")")
    return f"[{safe}]({url})" if url else safe


def _top_items(data, limit: int = TOP_ITEMS) -> list[str]:
    """The day's entrants as linked lines, best first, across every part.

    Entrants only: the post reports what changed, and the attached document holds
    the standing lists it changed in.
    """
    lines: list[str] = []
    for part in data.parts:
        for category in data.categories:
            for item in part.items.get(category, []):
                if not item.is_new:
                    continue
                bits = [_linked(item.title, item.url), escape_mentions(part.label)]
                if item.verdict:
                    bits.append(item.verdict.title())
                if item.deadline_date:
                    bits.append(f"due {item.deadline_date}")
                lines.append(" · ".join(bits))
    return lines[:limit]


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def attention_lines(alerts) -> str:
    """"Synapse · overlap risk — [title](url)", one line per alert.

    ``alerts`` is a sequence of ``(project label, trigger label, title, url)``.
    Capped at :data:`MAX_ALERT_LINES` and summarised past that: the field exists so
    a reader knows *whether* to open the report today, and a list long enough to
    scroll has already failed at that.
    """
    rows = list(alerts or [])
    lines = [
        f"{escape_mentions(project)} · {escape_mentions(trigger)} — "
        f"{_linked(title, url)}"
        for project, trigger, title, url in rows[:MAX_ALERT_LINES]
    ]
    extra = len(rows) - len(lines)
    if extra > 0:
        lines.append(f"…and {extra} more in the report")
    return "\n".join(lines)


def _field(name: str, value: str) -> dict | None:
    """One embed field, or ``None`` when it would be empty.

    A field with a dash in it is worse than no field: it spends a reader's
    attention to tell them nothing.
    """
    value = (value or "").strip()
    return {"name": name, "value": value, "inline": False} if value else None


def personal_report_embed(
    data, stats: ReportStats, kind: str = "daily", *, alerts=None, changes=None
) -> dict:
    """The DM a person receives, daily or weekly (plan A.3)."""
    label = "weekly" if kind == "weekly" else "daily"
    period = "this week" if kind == "weekly" else "overnight"
    embed = {
        "title": f"Your {label} research report · {data.generated_on}",
        "description": overview_text(data.lead, stats, fallback_subject="your"),
        "color": BRAND_COLOR,
        "fields": [],
    }
    fields = [
        _field(f"Needs attention ({stats.alerts})", attention_lines(alerts)),
        # Ambient Plan 09: one line per change that took effect since yesterday.
        _field("Changed today", _drop_lines("\n".join(changes or []), 900)),
        _field(
            f"Top of {'the week' if kind == 'weekly' else 'today'}",
            "\n".join(_top_items(data, TOP_ITEMS if kind == "daily" else 5)),
        ),
        _field(
            f"Found {period}",
            volume_line(stats, subject="you or your projects", period=period),
        ),
        _field("By category (new · in your feeds)", _pairs(stats)),
        _field("By project (new · alerts)", _project_line(stats)),
        _field("By theme (new)", _theme_line(stats)),
        _field(
            f"Deadlines within {stats.deadline_window_days} days",
            _deadline_line(stats),
        ),
    ]
    embed["fields"] = [one for one in fields if one]
    embed["footer"] = {"text": "Full report attached."}
    return fit_embed(embed)


def lab_post_embed(
    data, stats: ReportStats, kind: str = "daily", *, alerts=None, changes=None
) -> dict:
    """The post a lab's channel receives, daily or weekly (plan A.4).

    Same shape as the DM with lab wording, plus the line that says the post is
    partial: a lab surface lists only projects shared into it, and a reader who
    knows the lab runs six projects should be told the difference is a setting.
    """
    label = "weekly" if kind == "weekly" else "daily"
    period = "this week" if kind == "weekly" else "overnight"
    embed = {
        "title": (
            f"{escape_mentions(data.display_name)} · Mylo {label} · "
            f"{data.generated_on}"
        ),
        "description": overview_text(data.lead, stats, fallback_subject="the lab's"),
        "color": BRAND_COLOR,
        "fields": [],
    }
    # Never "N private projects not shown": that count told the server private
    # projects exist. It stays on the managers' web view (decision 11).
    shared = _project_line(stats, projects_only=True)
    fields = [
        _field(f"Needs attention ({stats.alerts})", attention_lines(alerts)),
        # Ambient Plan 09: a stated-state change accepted today, and by whom.
        _field("Changed today", _drop_lines("\n".join(changes or []), 900)),
        _field(
            f"Top of {'the week' if kind == 'weekly' else 'today'}",
            "\n".join(_top_items(data, TOP_ITEMS if kind == "daily" else 5)),
        ),
        _field(f"Found {period}", volume_line(stats, subject="the lab", period=period)),
        _field("By category (new · in lab feeds)", _pairs(stats)),
        _field("By theme (new)", _theme_line(stats)),
        _field("Shared projects (new · alerts)", shared),
        _field(
            f"Deadlines within {stats.deadline_window_days} days",
            _deadline_line(stats),
        ),
    ]
    embed["fields"] = [one for one in fields if one]
    embed["footer"] = {"text": "Full report attached below · Mylo never tags anyone"}
    return fit_embed(embed)


# --------------------------------------------------------------------------- #
# Fitting
# --------------------------------------------------------------------------- #
def _drop_lines(value: str, limit: int) -> str:
    """Trim a field value to ``limit`` by dropping whole lines from the end.

    A field is a list; cutting it mid-entry produces a half-title with a dangling
    bracket. Dropping entries and saying how many were dropped keeps the field
    readable and honest. A single line too long for the limit is the one case
    where there is nothing to drop, and it is trimmed at a word boundary.
    """
    if len(value) <= limit:
        return value
    lines = value.split("\n")
    if len(lines) == 1:
        return value[: limit - 1].rsplit(" ", 1)[0] + "…"
    kept: list[str] = []
    for line in lines:
        more = len(lines) - len(kept) - 1
        tail = f"\n…and {more} more" if more > 0 else ""
        candidate = "\n".join([*kept, line]) + tail
        if len(candidate) > limit:
            break
        kept.append(line)
    dropped = len(lines) - len(kept)
    if not kept:
        return _drop_lines(lines[0], limit)
    return "\n".join(kept) + (f"\n…and {dropped} more" if dropped else "")


def embed_size(embed: dict) -> int:
    """Every character Discord counts toward the 6000-character total."""
    total = len(embed.get("title") or "") + len(embed.get("description") or "")
    total += len((embed.get("footer") or {}).get("text") or "")
    total += len((embed.get("author") or {}).get("name") or "")
    for one in embed.get("fields") or []:
        total += len(one.get("name") or "") + len(one.get("value") or "")
    return total


def fit_embed(embed: dict) -> dict:
    """Bring one embed inside every Discord limit, dropping whole lines only.

    Called last by every producer here, and safe to call twice. Discord rejects an
    oversized embed outright, so the alternative to trimming is not a long post —
    it is no post, with a dead-lettered outbox row and a reader who hears nothing
    and is told nothing.

    Fields are dropped from the **end** when the total is still over, because the
    order in this module is the order of usefulness: the overview and what needs
    attention first, the finer splits last.
    """
    embed = dict(embed)
    embed["title"] = (embed.get("title") or "")[:TITLE_LIMIT]
    embed["description"] = _drop_lines(
        embed.get("description") or "", DESCRIPTION_LIMIT
    )

    fields = []
    for one in (embed.get("fields") or [])[:MAX_FIELDS]:
        fields.append(
            {
                "name": (one.get("name") or "")[:FIELD_NAME_LIMIT],
                "value": _drop_lines(one.get("value") or "", FIELD_VALUE_LIMIT),
                "inline": bool(one.get("inline")),
            }
        )
    embed["fields"] = fields

    while embed["fields"] and embed_size(embed) > TOTAL_LIMIT:
        embed["fields"] = embed["fields"][:-1]
    if embed_size(embed) > TOTAL_LIMIT:
        room = TOTAL_LIMIT - (embed_size(embed) - len(embed["description"]))
        embed["description"] = _drop_lines(embed["description"], max(room, 0))
    return embed
