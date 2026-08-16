"""Turn the nightly analytics JSON into a Discord run summary.

The reading half of the split that :mod:`apps.content.run_analytics` writes. The
daily run's stages execute inside the backend container, where the database and
the PDF renderer live; the run *summary* is posted from the host, by the same
bare-stdlib runner that already reports a failed stage. So the container writes
``data/logs/mylo-run-analytics.json`` under the shared bind mount and this module
reads it back — no Django, no database, no third-party import.

The formatting problem is that Discord has no charts. What it does have is a
monospace code block, and a bar drawn from block characters inside one is a real
chart: proportional, sortable, readable on a phone, and immune to the image
proxying and dark-mode inversion that a rendered PNG would fight. So every
"graph" here is text, every table is column-aligned text, and both are clamped to
the 1024-character embed-field ceiling with an explicit "+N more" line rather
than a silent cut.

The one presentation rule that matters: **a zero is a number, not a gap.** A
night that found no grants says ``0``, because "the grants source went quiet" and
"we forgot to measure grants" must not look the same.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

#: The checkout root on *this* host — the same tree the backend container sees
#: bind-mounted at ``/app``. Every artifact the container leaves for the host
#: runner is re-anchored here, because the two halves address the same bytes
#: under different roots.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where the backend command leaves the metrics. Mirrors
#: ``settings.RUN_ANALYTICS_JSON_PATH``; the repo root is one level up from here.
ANALYTICS_PATH = REPO_ROOT / "data" / "logs" / "mylo-run-analytics.json"

#: Mirrors ``settings.RUN_ANALYTICS_PDF_DIR`` — the last-resort place to look for
#: a report whose payload named neither a relative nor a reachable path.
ANALYTICS_PDF_DIR = REPO_ROOT / "data" / "analytics"

#: Discord's embed field ceiling. Every block is clamped to it.
FIELD_MAX = 1024

#: Bar width in characters. Wide enough to be proportional, narrow enough that a
#: long label plus a bar plus a count still fits a phone screen.
_BAR_WIDTH = 18
_BAR_FULL = "█"
_BAR_EMPTY = "·"

_CATEGORY_ORDER = ("papers", "grants", "fellowships", "conferences")
_CATEGORY_LABELS = {
    "papers": "Papers",
    "grants": "Grants",
    "fellowships": "Fellowships",
    "conferences": "Conferences",
}
_TARGET_ORDER = ("user", "lab", "project", "department")
_TARGET_LABELS = {
    "user": "People",
    "lab": "Labs",
    "project": "Projects",
    "department": "Departments",
}


def read_analytics(path: str | Path | None = None) -> dict | None:
    """Load the metrics file, or ``None`` if it is missing or unreadable.

    Missing is a normal outcome, not an error: the analytics stage is non-fatal,
    so a run whose measurement failed still posts its plain completion notice.
    """
    target = Path(path) if path else ANALYTICS_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Mylo analytics not available at %s: %s", target, exc)
        return None
    if not isinstance(payload, dict):
        log.warning("Mylo analytics at %s was not an object", target)
        return None
    return payload


def resolve_pdf(payload: dict | None) -> Path | None:
    """The analytics PDF as a path *this host* can open, or ``None``.

    The metrics file is written inside the backend container, so its ``pdf_path``
    is a container path (``/app/data/analytics/…``) that does not exist out here.
    Handing that straight to the reporter is not a loud failure — the attachment
    reader logs a warning and posts the summary without the file — so the run
    quietly loses the PDF it just rendered.

    Preference order: ``pdf_relpath`` re-anchored on this checkout (the portable
    key), then ``pdf_path`` as written (correct when the writer and the runner
    share a filesystem, and the only key older payloads carry), then the default
    report directory by filename.
    """
    if not isinstance(payload, dict):
        return None

    candidates: list[Path] = []
    relative = str(payload.get("pdf_relpath") or "").strip()
    if relative:
        candidates.append(REPO_ROOT / relative)
    raw = str(payload.get("pdf_path") or "").strip()
    if raw:
        candidates.append(Path(raw))
        if not Path(raw).is_absolute():
            candidates.append(REPO_ROOT / raw)
    name = str(payload.get("pdf_filename") or "").strip()
    if name:
        candidates.append(ANALYTICS_PDF_DIR / name)

    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:  # an unreadable mount is a miss, not a crash
            continue

    if candidates:
        log.warning(
            "Mylo analytics PDF not readable on this host; tried %s",
            ", ".join(str(c) for c in candidates),
        )
    return None


# --- primitives ------------------------------------------------------------- #
def _n(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def bar(value: int, peak: int, width: int = _BAR_WIDTH) -> str:
    """A proportional block bar. A non-zero value always shows at least one block.

    Rounding a small-but-real count down to an empty bar is the one failure mode
    that would make the chart lie, so it is floored at one block instead.
    """
    if peak <= 0 or value <= 0:
        return _BAR_EMPTY * width
    filled = max(1, round(width * value / peak))
    filled = min(width, filled)
    return _BAR_FULL * filled + _BAR_EMPTY * (width - filled)


def bar_chart(rows: list[tuple[str, int]]) -> str:
    """Render ``[(label, value)]`` as an aligned bar chart. Returns bare text."""
    if not rows:
        return "no data"
    peak = max(value for _, value in rows)
    label_width = max(len(label) for label, _ in rows)
    count_width = max(len(_n(value)) for _, value in rows)
    return "\n".join(
        f"{label:<{label_width}}  {bar(value, peak)}  {_n(value):>{count_width}}"
        for label, value in rows
    )


def table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a column-aligned plain-text table. Returns bare text."""
    columns = [headers] + rows
    widths = [
        max(len(str(row[index])) for row in columns) for index in range(len(headers))
    ]

    def line(cells: list[str]) -> str:
        # First column left-aligned (names), the rest right-aligned (numbers).
        parts = [f"{str(cells[0]):<{widths[0]}}"]
        parts += [
            f"{str(cells[index]):>{widths[index]}}" for index in range(1, len(headers))
        ]
        return "  ".join(parts)

    body = [line(headers), "  ".join("─" * width for width in widths)]
    body += [line(row) for row in rows]
    return "\n".join(body)


def code_block(text: str, *, limit: int = FIELD_MAX) -> str:
    """Wrap ``text`` in a fenced block, dropping whole lines to stay under ``limit``.

    Truncation is announced. A block that silently loses its last three
    components reads as a complete list, which is exactly the kind of quiet lie
    an operations report cannot afford.
    """
    fence_cost = len("```\n\n```")
    lines = text.splitlines() or [""]
    budget = limit - fence_cost
    kept: list[str] = []
    used = 0
    for index, line in enumerate(lines):
        remaining = len(lines) - index
        notice = f"… +{remaining} more" if remaining > 1 else ""
        needed = len(line) + 1
        if used + needed > budget - (len(notice) + 1 if notice else 0):
            if notice:
                kept.append(notice)
            break
        kept.append(line)
        used += needed
    return "```\n" + "\n".join(kept) + "\n```"


# --- blocks ----------------------------------------------------------------- #
def discovery_chart(payload: dict) -> str:
    """The night's new content as a bar chart, one row per category."""
    discovery = payload.get("discovery") or {}
    rows = [
        (_CATEGORY_LABELS[category], _int(discovery.get(category)))
        for category in _CATEGORY_ORDER
    ]
    return code_block(bar_chart(rows))


def coverage_block(payload: dict) -> str:
    """Who the run was for."""
    coverage = payload.get("coverage") or {}
    return code_block(
        table(
            ["Ran for", "Count"],
            [
                ["People", _n(coverage.get("users"))],
                ["Labs", _n(coverage.get("labs"))],
                ["Projects", _n(coverage.get("projects"))],
                ["Departments", _n(coverage.get("departments"))],
            ],
        )
    )


def discovery_block(payload: dict) -> str:
    """New items found, by category, with the day's total."""
    discovery = payload.get("discovery") or {}
    rows = [
        [_CATEGORY_LABELS[category], _n(discovery.get(category))]
        for category in _CATEGORY_ORDER
    ]
    rows.append(["Total", _n(discovery.get("total"))])
    return code_block(table(["Found", "New"], rows))


def delivery_block(payload: dict) -> str:
    """Reports written and how far they got. Pending is stated, never implied."""
    delivery = payload.get("delivery") or {}
    return code_block(
        table(
            ["Reports", "Count"],
            [
                ["Generated", _n(delivery.get("briefings_generated"))],
                ["Queued", _n(delivery.get("reports_queued"))],
                ["Delivered", _n(delivery.get("reports_delivered"))],
                ["Pending", _n(delivery.get("reports_pending"))],
                ["Failed", _n(delivery.get("reports_failed"))],
                ["Lab digests", _n(delivery.get("digests_queued"))],
            ],
        )
    )


def recommendations_block(payload: dict) -> str:
    """What Mylo put in front of someone, by category and by target."""
    recs = payload.get("recommendations") or {}
    by_category = recs.get("by_category") or {}
    by_target = recs.get("by_target") or {}
    rows = [
        [
            _CATEGORY_LABELS[category],
            _n(by_category.get(category)),
        ]
        for category in _CATEGORY_ORDER
    ]
    category_table = table(["Recommended", "Count"], rows)
    target_rows = [
        (_TARGET_LABELS[key], _int(by_target.get(key))) for key in _TARGET_ORDER
    ]
    return code_block(
        f"{category_table}\n\nTotal: {_n(recs.get('total'))}"
        f"\n\n{bar_chart(target_rows)}"
    )


def llm_block(payload: dict) -> str:
    """Per-component calls, failures, and token spend, heaviest first."""
    llm = payload.get("llm") or {}
    components = llm.get("components") or []
    rows = []
    for component in components:
        prompt = _int(component.get("prompt_tokens"))
        completion = _int(component.get("completion_tokens"))
        rows.append(
            [
                str(component.get("component", "?"))[:22],
                _n(component.get("calls")),
                _n(component.get("failures")),
                _n(prompt),
                _n(completion),
            ]
        )
    if not rows:
        return code_block("No language-model calls were recorded.")
    rows.append(
        [
            "TOTAL",
            _n(llm.get("calls")),
            _n(llm.get("failures")),
            _n(llm.get("prompt_tokens")),
            _n(llm.get("completion_tokens")),
        ]
    )
    rendered = table(["Component", "Calls", "Fail", "In tok", "Out tok"], rows)
    # Input and output are tracked separately because they price differently;
    # the combined figure is what anyone actually quotes, so state both.
    total = _int(llm.get("total_tokens")) or (
        _int(llm.get("prompt_tokens")) + _int(llm.get("completion_tokens"))
    )
    return code_block(f"{rendered}\n\nTokens used: {_n(total)}")


def trend_block(payload: dict) -> str:
    """The last few days of recommendations, so one night has context."""
    trend = payload.get("trend") or []
    if not trend:
        return ""
    rows = [
        (str(point.get("day", "?"))[5:], _int(point.get("recommendations")))
        for point in trend
    ]
    return code_block(bar_chart(rows))


def summary_fields(payload: dict) -> dict[str, object]:
    """The embed fields for the run summary, in reading order.

    Coverage / found / delivered sit inline as three narrow columns — the
    at-a-glance row — and the wider tables stack full-width beneath them.
    """
    fields: dict[str, object] = {
        "Coverage": (coverage_block(payload), True),
        "Discovery": (discovery_block(payload), True),
        "Report delivery": (delivery_block(payload), True),
        "Recommendations written": recommendations_block(payload),
        "Language model": llm_block(payload),
    }
    trend = trend_block(payload)
    if trend:
        fields["Recommendations, last 7 days"] = trend
    return fields


def summary_body(payload: dict, *, scrape_ran: bool = True) -> str:
    """The embed description: the headline sentence over the discovery chart."""
    headline = str(payload.get("headline") or "The daily run finished.")
    lines = [
        "**scrape → search → match → remind → prune → briefing → report**",
        "",
        headline,
    ]
    if not scrape_ran:
        lines.append(
            "_The opportunity scrape was skipped — see the earlier alert; the "
            "match stages ran against the existing corpus._"
        )
    lines.append("")
    lines.append(f"**New items found today**\n{discovery_chart(payload)}")
    return "\n".join(lines)


def attention_line(payload: dict) -> str:
    """A one-line warning when the numbers say something needs a look, else ``""``.

    Deliberately narrow. A summary that flags something every night trains people
    to skim past the night it matters.
    """
    llm = payload.get("llm") or {}
    delivery = payload.get("delivery") or {}
    notes: list[str] = []

    calls = _int(llm.get("calls"))
    failures = _int(llm.get("failures"))
    if failures and calls:
        notes.append(f"{_n(failures)} LLM call(s) failed ({failures / calls:.0%})")
    if _int(delivery.get("reports_failed")):
        notes.append(f"{_n(delivery.get('reports_failed'))} report(s) undeliverable")
    discovery_total = _int((payload.get("discovery") or {}).get("total"))
    if discovery_total == 0:
        notes.append("no new items entered the store")
    return " · ".join(notes)
