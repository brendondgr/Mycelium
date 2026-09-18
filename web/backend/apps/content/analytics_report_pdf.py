"""Render a :class:`~apps.content.run_analytics.RunAnalytics` into a PDF.

The internal sibling of :mod:`apps.content.daily_report_pdf`. Same page
furniture, same Mycelium light palette (cream page, forest headings, restrained
gold for the signals that need attention), so the operations report reads as part
of the same product rather than a debug dump — but the audience is the team, not
a researcher, and the content is entirely operational.

Structure:

1. a cover with the run date, the headline sentence, and an at-a-glance table,
2. **Coverage** — who the run was for,
3. **Discovery** — what entered the store, with a bar chart by category,
4. **Recommendations** — what Mylo put in front of someone, by category and target,
5. **Language model** — calls, failures, and token spend per component,
6. **Delivery** — briefings written and how far their messages got,
7. **Last 7 days** — the same run read against its neighbours.

Charts are drawn with ``reportlab.graphics``, which ships with reportlab, so this
adds no dependency and renders anywhere the backend runs. Every chart is paired
with the table it visualizes: a reader who cannot resolve the colours still has
the numbers (``docs/styles.md`` — never rely on colour alone).

:func:`render_analytics_pdf` returns the PDF as ``bytes``.
"""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.content.run_analytics import (
    CATEGORIES,
    CATEGORY_LABELS,
    TARGET_LABELS,
    RunAnalytics,
)

# --- Palette (docs/styles.md, light theme) --------------------------------- #
BG = HexColor("#F8F4EC")
SURFACE = HexColor("#FFFDF8")
SURFACE_ALT = HexColor("#EFE7D7")
PRIMARY = HexColor("#5E7A3E")
PRIMARY_HOVER = HexColor("#4D6733")
SECONDARY = HexColor("#8DA66F")
ACCENT = HexColor("#C9A35A")
ACCENT_SOFT = HexColor("#E7D8B8")
TEXT = HexColor("#2E3627")
TEXT_SECONDARY = HexColor("#5F6853")
TEXT_MUTED = HexColor("#7F8775")
BORDER = HexColor("#D9D0BE")
DIVIDER = HexColor("#E8E0D1")
ALERT = HexColor("#B04A32")

_SERIF_BOLD = "Times-Bold"
_SANS = "Helvetica"
_SANS_BOLD = "Helvetica-Bold"

_MARGIN = 0.9 * inch
#: Usable width between the margins, for tables and charts.
_CONTENT_WIDTH = LETTER[0] - 2 * _MARGIN

#: Bar fills, in the order series are added. Green first, gold for the series
#: that should draw the eye (opportunities, failures).
_SERIES_COLORS = [PRIMARY, SECONDARY, ACCENT, HexColor("#A88B5C")]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}
    styles["Cover"] = ParagraphStyle(
        "Cover", parent=base["Title"], fontName=_SERIF_BOLD, fontSize=28,
        leading=32, textColor=PRIMARY_HOVER, spaceAfter=6, alignment=TA_LEFT,
    )
    styles["CoverSub"] = ParagraphStyle(
        "CoverSub", fontName=_SANS, fontSize=12, leading=16,
        textColor=TEXT_SECONDARY, spaceAfter=2,
    )
    styles["H1"] = ParagraphStyle(
        "H1", fontName=_SERIF_BOLD, fontSize=18, leading=22, textColor=PRIMARY_HOVER,
        spaceBefore=6, spaceAfter=8,
    )
    styles["Body"] = ParagraphStyle(
        "Body", fontName=_SANS, fontSize=10, leading=15, textColor=TEXT, spaceAfter=6,
    )
    styles["Muted"] = ParagraphStyle(
        "Muted", fontName=_SANS, fontSize=9.5, leading=14, textColor=TEXT_MUTED,
        spaceAfter=6,
    )
    styles["Note"] = ParagraphStyle(
        "Note", fontName=_SANS, fontSize=8.5, leading=12, textColor=TEXT_MUTED,
        spaceBefore=2, spaceAfter=8,
    )
    styles["Alert"] = ParagraphStyle(
        "Alert", fontName=_SANS_BOLD, fontSize=10, leading=14, textColor=ALERT,
        spaceAfter=6,
    )
    styles["ChartTitle"] = ParagraphStyle(
        "ChartTitle", fontName=_SANS_BOLD, fontSize=10, leading=13,
        textColor=TEXT_SECONDARY, spaceBefore=6, spaceAfter=2,
    )
    return styles


def _n(value: int | float) -> str:
    """Thousands-separated, so six-figure token counts stay readable."""
    return f"{int(value):,}"


# --- Tables ----------------------------------------------------------------- #
def _table(
    rows: list[list[str]], widths: list[float], *, highlight_last=False
) -> Table:
    """A header-row table in the report's house style."""
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), SURFACE),
        ("FONTNAME", (0, 0), (-1, 0), _SANS_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), _SANS),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, SURFACE_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    if highlight_last and len(rows) > 2:
        style += [
            ("BACKGROUND", (0, -1), (-1, -1), ACCENT_SOFT),
            ("FONTNAME", (0, -1), (-1, -1), _SANS_BOLD),
        ]
    table.setStyle(TableStyle(style))
    return table


def _metric_rows(pairs: list[tuple[str, int]]) -> list[list[str]]:
    return [["Metric", "Count"]] + [[label, _n(value)] for label, value in pairs]


def _captioned(caption: str, drawing, styles) -> KeepTogether:
    """A chart and its caption, bound together.

    Without this the caption drifts to the foot of one page and its chart opens
    the next, which is how a report starts labelling the wrong picture.
    """
    return KeepTogether([Paragraph(caption, styles["ChartTitle"]), drawing])


# --- Charts ----------------------------------------------------------------- #
def _bar_chart(
    labels: list[str],
    series: list[tuple[str, list[int]]],
    *,
    height: float = 165,
) -> Drawing:
    """A grouped vertical bar chart sized to the content width."""
    drawing = Drawing(_CONTENT_WIDTH, height)
    chart = VerticalBarChart()
    chart.x = 34
    chart.y = 34
    chart.width = _CONTENT_WIDTH - 60
    chart.height = height - 58
    chart.data = [values for _, values in series] or [[0] * len(labels)]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = _SANS
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fillColor = TEXT_SECONDARY
    chart.categoryAxis.labels.dy = -4
    chart.categoryAxis.strokeColor = BORDER
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = _SANS
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fillColor = TEXT_MUTED
    chart.valueAxis.strokeColor = BORDER
    chart.valueAxis.gridStrokeColor = DIVIDER
    chart.valueAxis.visibleGrid = 1
    # An all-zero night would otherwise render an axis with no range at all.
    if not any(any(values) for _, values in series):
        chart.valueAxis.valueMax = 1
    chart.barSpacing = 1
    chart.groupSpacing = 12
    chart.bars.strokeColor = None
    for index in range(len(chart.data)):
        chart.bars[index].fillColor = _SERIES_COLORS[index % len(_SERIES_COLORS)]
    drawing.add(chart)

    if len(series) > 1:
        legend = Legend()
        legend.x = 34
        legend.y = height - 8
        legend.alignment = "right"
        legend.fontName = _SANS
        legend.fontSize = 8
        legend.fillColor = TEXT_SECONDARY
        legend.columnMaximum = 1
        legend.deltax = 62
        legend.dxTextSpace = 4
        legend.boxAnchor = "nw"
        legend.colorNamePairs = [
            (_SERIES_COLORS[index % len(_SERIES_COLORS)], name)
            for index, (name, _) in enumerate(series)
        ]
        drawing.add(legend)
    return drawing


def _line_chart(
    labels: list[str], values: list[int], *, height: float = 150
) -> Drawing:
    """A single-series line chart for the trend section."""
    drawing = Drawing(_CONTENT_WIDTH, height)
    chart = HorizontalLineChart()
    chart.x = 40
    chart.y = 30
    chart.width = _CONTENT_WIDTH - 66
    chart.height = height - 52
    chart.data = [values or [0]]
    chart.categoryAxis.categoryNames = labels or [""]
    chart.categoryAxis.labels.fontName = _SANS
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fillColor = TEXT_SECONDARY
    chart.categoryAxis.strokeColor = BORDER
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = _SANS
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fillColor = TEXT_MUTED
    chart.valueAxis.strokeColor = BORDER
    chart.valueAxis.gridStrokeColor = DIVIDER
    chart.valueAxis.visibleGrid = 1
    if not any(values):
        chart.valueAxis.valueMax = 1
    chart.lines[0].strokeColor = PRIMARY
    chart.lines[0].strokeWidth = 2
    chart.lines.symbol = None
    drawing.add(chart)
    return drawing


# --- Page decoration -------------------------------------------------------- #
def _decorate(canvas, doc) -> None:
    """Cream page + footer rule, matching the user-facing daily report."""
    canvas.saveState()
    canvas.setFillColor(BG)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    y = 0.55 * inch
    canvas.setStrokeColor(DIVIDER)
    canvas.setLineWidth(0.5)
    canvas.line(_MARGIN, y + 10, doc.pagesize[0] - _MARGIN, y + 10)
    canvas.setFont(_SANS, 8)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(_MARGIN, y, "Mycelium · internal run analytics · confidential")
    canvas.drawRightString(doc.pagesize[0] - _MARGIN, y, f"Page {doc.page}")
    canvas.restoreState()


# --- Sections --------------------------------------------------------------- #
def _cover(data: RunAnalytics, styles) -> list:
    llm = data.llm
    story: list = [
        Spacer(1, 0.5 * inch),
        Paragraph("Mycelium Run Analytics", styles["Cover"]),
        Paragraph("Internal usage report — daily research run", styles["CoverSub"]),
        Paragraph(escape(data.generated_on.isoformat()), styles["CoverSub"]),
        Spacer(1, 0.3 * inch),
        Paragraph(escape(data.headline()), styles["Body"]),
        Spacer(1, 0.1 * inch),
        _table(
            [
                ["At a glance", "Count"],
                ["Targets covered", _n(data.coverage.total_targets)],
                ["New items discovered", _n(data.discovery.total)],
                ["Recommendations written", _n(data.recommendations.total)],
                ["Language-model calls", _n(llm.calls)],
                ["Tokens used", _n(llm.total_tokens)],
                ["Reports generated", _n(data.delivery.briefings_generated)],
                ["Reports delivered", _n(data.delivery.reports_delivered)],
            ],
            [3.4 * inch, 3.0 * inch],
        ),
    ]
    if llm.failures:
        story.append(Spacer(1, 0.12 * inch))
        story.append(
            Paragraph(
                f"{_n(llm.failures)} language-model call(s) failed "
                f"({llm.failure_rate:.1%} of the day's calls).",
                styles["Alert"],
            )
        )
    return story


def _coverage_section(data: RunAnalytics, styles) -> list:
    coverage = data.coverage
    return [
        Paragraph("Coverage", styles["H1"]),
        Paragraph(
            "Who tonight's run was for. These are the pipeline's own selectors, "
            "so a covered target that matched nothing is still counted here.",
            styles["Muted"],
        ),
        _table(
            _metric_rows(
                [
                    ("People", coverage.users),
                    ("Labs", coverage.labs),
                    ("Projects", coverage.projects),
                    ("Departments", coverage.departments),
                ]
            ),
            [3.4 * inch, 3.0 * inch],
        ),
        Paragraph(
            "Departments are not scored directly — the number is the departments "
            "whose active plan brought labs into the run.",
            styles["Note"],
        ),
        _bar_chart(
            ["People", "Labs", "Projects", "Departments"],
            [
                (
                    "Targets",
                    [
                        coverage.users,
                        coverage.labs,
                        coverage.projects,
                        coverage.departments,
                    ],
                )
            ],
        ),
    ]


def _discovery_section(data: RunAnalytics, styles) -> list:
    labels = [CATEGORY_LABELS[c] for c in CATEGORIES]
    discovered = [data.discovery.get(c) for c in CATEGORIES]
    recommended = [
        int(data.recommendations.by_category.get(c, 0)) for c in CATEGORIES
    ]
    rows = [["Category", "Discovered", "Recommended"]]
    rows += [
        [labels[i], _n(discovered[i]), _n(recommended[i])] for i in range(len(labels))
    ]
    rows.append(["Total", _n(sum(discovered)), _n(sum(recommended))])
    return [
        Paragraph("Discovery", styles["H1"]),
        Paragraph(
            "Items that entered the store for the first time today, against the "
            "matches Mylo wrote. Re-scraping a known item updates it in place, so "
            "'discovered' counts what the corpus actually gained.",
            styles["Muted"],
        ),
        _table(rows, [2.6 * inch, 1.9 * inch, 1.9 * inch], highlight_last=True),
        _captioned(
            "New items vs recommendations, by category",
            _bar_chart(
                labels,
                [("Discovered", discovered), ("Recommended", recommended)],
            ),
            styles,
        ),
    ]


def _recommendations_section(data: RunAnalytics, styles) -> list:
    recs = data.recommendations
    order = ("user", "lab", "project", "department")
    labels = [TARGET_LABELS[key] for key in order]
    values = [int(recs.by_target.get(key, 0)) for key in order]
    rows = [["Matched to", "Recommendations"]]
    rows += [[labels[i], _n(values[i])] for i in range(len(order))]
    rows.append(["Total", _n(recs.total)])

    story = [
        Paragraph("Recommendations", styles["H1"]),
        Paragraph(
            "Every relevance score Mylo wrote today, by the kind of profile it was "
            "matched against. The daily run only appends — it never rewrites or "
            "drops an earlier recommendation.",
            styles["Muted"],
        ),
        _table(rows, [3.4 * inch, 3.0 * inch], highlight_last=True),
        _captioned(
            "Recommendations by target",
            _bar_chart(labels, [("Recommendations", values)]),
            styles,
        ),
    ]
    if recs.member_suggestions:
        story.append(
            Paragraph(
                f"Cross-member fan-out also scored {_n(recs.member_suggestions)} "
                f"item(s) against individual profiles, of which "
                f"{_n(recs.member_suggestions_delivered)} passed the floor and were "
                "delivered.",
                styles["Body"],
            )
        )
    return story


def _llm_section(data: RunAnalytics, styles) -> list:
    llm = data.llm
    rows = [["Component", "Calls", "Failed", "Input tok.", "Output tok."]]
    for component in llm.components:
        rows.append(
            [
                component.component,
                _n(component.calls),
                _n(component.failures),
                _n(component.prompt_tokens),
                _n(component.completion_tokens),
            ]
        )
    rows.append(
        [
            "Total",
            _n(llm.calls),
            _n(llm.failures),
            _n(llm.prompt_tokens),
            _n(llm.completion_tokens),
        ]
    )
    widths = [2.2 * inch, 0.95 * inch, 0.95 * inch, 1.15 * inch, 1.15 * inch]

    story = [
        Paragraph("Language model", styles["H1"]),
        Paragraph(
            "What the run asked of the model, attributed to the feature that asked. "
            "A failed call is one that raised — an unreachable endpoint, a timeout, "
            "or a reply the client could not parse; those features fall back to "
            "their deterministic path rather than skipping the target.",
            styles["Muted"],
        ),
    ]
    if len(rows) == 2:
        story.append(
            Paragraph("No language-model calls were recorded today.", styles["Muted"])
        )
    else:
        story.append(_table(rows, widths, highlight_last=True))
        top = llm.components[:6]
        story.append(
            _captioned(
                "Token spend by component",
                _bar_chart(
                    [c.component for c in top],
                    [
                        ("Input", [c.prompt_tokens for c in top]),
                        ("Output", [c.completion_tokens for c in top]),
                    ],
                ),
                styles,
            )
        )
        if len(llm.components) > len(top):
            story.append(
                Paragraph(
                    f"Chart shows the {len(top)} heaviest components; the table "
                    "above is complete.",
                    styles["Note"],
                )
            )
    return story


def _delivery_section(data: RunAnalytics, styles) -> list:
    delivery = data.delivery
    rows = [
        ["Stage", "Count"],
        ["Briefings written for people", _n(delivery.briefings_users)],
        ["Briefings written for labs", _n(delivery.briefings_labs)],
        ["— of which used the deterministic fallback", _n(delivery.briefings_fallback)],
        ["Personal reports queued", _n(delivery.reports_queued)],
        ["Personal reports delivered", _n(delivery.reports_delivered)],
        ["Personal reports held for a local send hour", _n(delivery.reports_scheduled)],
        ["Personal reports still pending", _n(delivery.reports_pending)],
        ["Personal reports permanently failed", _n(delivery.reports_failed)],
        ["Lab digests queued", _n(delivery.digests_queued)],
        ["Lab digests delivered", _n(delivery.digests_delivered)],
        ["Lab digests held for a local send hour", _n(delivery.digests_scheduled)],
    ]
    telemetry = data.telemetry
    rows += [
        ["", ""],
        ["People on daily cadence", _n(telemetry.cadence_daily)],
        ["People on weekly cadence", _n(telemetry.cadence_weekly)],
        ["Labs on daily cadence", _n(telemetry.lab_cadence_daily)],
        ["Labs on weekly cadence", _n(telemetry.lab_cadence_weekly)],
        ["Opted into urgent alerts", _n(telemetry.urgent_alerts_opted_in)],
        ["Opted out of the report DM", _n(telemetry.dm_opt_outs)],
    ]
    busiest = sorted(
        (telemetry.opens_by_weekday or {}).items(), key=lambda row: -row[1]
    )
    if busiest and busiest[0][1]:
        named = ", ".join(f"{day} {count}" for day, count in busiest[:3])
        rows.append(["Engagement by weekday (busiest three)", named])
    return [
        Paragraph("Delivery", styles["H1"]),
        Paragraph(
            "Reports written, and how far each got toward a person. Discord sends "
            "are queued and drained on their own schedule, so a report counted as "
            "pending here is waiting for the next drain, not lost. A report held "
            "for a local send hour is not counted as pending: it is waiting on "
            "purpose, for the recipient's morning rather than for the queue. "
            "Whether a lab has muted its channel is not observable — Discord "
            "does not tell a bot — so it is not reported rather than reported "
            "as zero.",
            styles["Muted"],
        ),
        _table(rows, [4.2 * inch, 2.2 * inch]),
    ]


def _listening_section(data: RunAnalytics, styles) -> list:
    """How much conversation was heard, and why the rest was not kept.

    Omitted entirely when nothing is listening, rather than printed as a page
    of zeros for a feature this deployment has not turned on.
    """
    listening = data.listening
    if not listening.sources_listening and not listening.heard:
        return []
    rows = [
        ["Stage", "Count"],
        ["Servers listening", _n(listening.sources_listening)],
        ["Servers that heard anything today", _n(listening.sources_active_today)],
        ["Messages heard", _n(listening.heard)],
        ["Messages kept for tonight's reading", _n(listening.stored)],
        ["", ""],
        ["Dropped — the sender has not opted in", _n(listening.dropped_not_opted_in)],
        ["Dropped — no Mycelium account", _n(listening.dropped_unlinked)],
        ["Dropped — free plan", _n(listening.dropped_free_tier)],
        ["Dropped — an excluded channel", _n(listening.dropped_excluded_channel)],
        ["Dropped — too short to be worth keeping", _n(listening.dropped_too_short)],
        ["Dropped — another bot", _n(listening.dropped_bot)],
        [
            "Dropped at the nightly read — no longer eligible",
            _n(listening.dropped_lapsed),
        ],
    ]
    return [
        Paragraph("Listening", styles["H1"]),
        Paragraph(
            "How much of the lab's own conversation reached Mylo. The dropped "
            "rows are the useful half: a server where everything lands in \u201cthe "
            "sender has not opted in\u201d is not broken, it is one where nobody has "
            "opted in yet, which is a different conversation to have with that "
            "lab than a misconfigured exclusion. Every figure here is per server "
            "and per reason, never per person \u2014 a report on how much was heard "
            "must not become a report on who was heard.",
            styles["Muted"],
        ),
        _table(rows, [4.2 * inch, 2.2 * inch]),
    ]


def _trend_section(data: RunAnalytics, styles) -> list:
    if not data.trend:
        return []
    labels = [point.day.strftime("%b %d") for point in data.trend]
    rows = [["Day", "Discovered", "Recommended", "LLM calls", "Tokens"]]
    for point in data.trend:
        rows.append(
            [
                point.day.isoformat(),
                _n(point.discovered),
                _n(point.recommendations),
                _n(point.llm_calls),
                _n(point.total_tokens),
            ]
        )
    return [
        Paragraph(f"Last {len(data.trend)} days", styles["H1"]),
        Paragraph(
            "One night means little on its own. This is the same run read against "
            "its neighbours — a flat discovery line means the sources went quiet, "
            "a flat recommendation line with healthy discovery means the matcher "
            "is rejecting everything.",
            styles["Muted"],
        ),
        _table(
            rows,
            [1.5 * inch, 1.25 * inch, 1.35 * inch, 1.15 * inch, 1.15 * inch],
        ),
        _captioned(
            "Recommendations written per day",
            _line_chart(labels, [point.recommendations for point in data.trend]),
            styles,
        ),
        _captioned(
            "New items discovered per day",
            _line_chart(labels, [point.discovered for point in data.trend]),
            styles,
        ),
    ]


# --- Public entry point ----------------------------------------------------- #
def render_analytics_pdf(data: RunAnalytics) -> bytes:
    """Render ``data`` to a PDF and return the raw bytes."""
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"Mycelium Run Analytics — {data.generated_on}",
        author="Mycelium",
    )

    story: list = []
    story.extend(_cover(data, styles))
    story.append(PageBreak())

    sections = [
        _coverage_section(data, styles),
        _discovery_section(data, styles),
        _recommendations_section(data, styles),
        _llm_section(data, styles),
        _delivery_section(data, styles),
        _listening_section(data, styles),
        _trend_section(data, styles),
    ]
    for index, section in enumerate(sections):
        if not section:
            continue
        # Keep each heading with the paragraph under it; let the tables and charts
        # flow, so a long component table is not forced onto a page of its own.
        story.append(KeepTogether(section[:2]))
        story.extend(section[2:])
        if index < len(sections) - 1:
            story.append(Spacer(1, 0.28 * inch))

    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buffer.getvalue()
