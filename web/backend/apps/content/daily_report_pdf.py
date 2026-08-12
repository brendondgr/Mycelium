"""Render a :class:`apps.content.daily_report.ReportData` into a PDF (reportlab).

A calm, scholarly one-file report in the Mycelium light palette (cream page, forest
green headings, restrained gold for opportunity/deadline signals — see
``docs/styles.md``). The document is:

1. a cover with the recipient, date, and the **summary table** — one row per part
   (Personal, then each project) against a column per category, each cell the count
   of what is new today,
2. a **table of contents** (real page numbers, resolved by a two-pass build) whose
   first entry points at the written report,
3. **Your Mylo Report** — the written briefing markdown, the main section,
4. **Personal** — ``Top 25 Articles`` / ``Top 25 Grants`` / ``Top 25 Fellowships`` /
   ``Top 25 Conferences``, each its own slate, and
5. one section **per project**, the same categories capped at ten.

Each list is the reader's whole top slice, every day — not just what arrived. The
``NEW`` tag marks the items that entered it on this run, which is the only part of
the page that changes when the day is quiet.

There is no "everything Mylo found" appendix. Reprinting the entire feed at the
bottom of a daily report made a long document longer without answering a question
anyone had; the feeds and search are where an exhaustive list belongs.

No system fonts or image assets are required: headings use Times (scholarly serif)
and body uses Helvetica, both bundled with reportlab, so this renders anywhere the
backend runs. :func:`render_report_pdf` returns the PDF as ``bytes``.
"""

from __future__ import annotations

import re
from io import BytesIO
from xml.sax.saxutils import escape

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
from reportlab.platypus.tableofcontents import TableOfContents

from apps.content.daily_report import (
    CATEGORY_LABELS,
    SECTION_NOUNS,
    ReportData,
    ReportItem,
    ReportPart,
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

_SERIF = "Times-Roman"
_SERIF_BOLD = "Times-Bold"
_SANS = "Helvetica"
_SANS_BOLD = "Helvetica-Bold"

_MARGIN = 0.9 * inch


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}
    styles["Cover"] = ParagraphStyle(
        "Cover", parent=base["Title"], fontName=_SERIF_BOLD, fontSize=30,
        leading=34, textColor=PRIMARY_HOVER, spaceAfter=6, alignment=TA_LEFT,
    )
    styles["CoverSub"] = ParagraphStyle(
        "CoverSub", fontName=_SANS, fontSize=12, leading=16,
        textColor=TEXT_SECONDARY, spaceAfter=2,
    )
    styles["H1"] = ParagraphStyle(
        "H1", fontName=_SERIF_BOLD, fontSize=19, leading=23, textColor=PRIMARY_HOVER,
        spaceBefore=8, spaceAfter=10,
    )
    # Same look as H1 but a distinct name, so afterFlowable does NOT list the
    # "Contents" page-title as its own table-of-contents entry.
    styles["TocTitle"] = ParagraphStyle(
        "TocTitle", parent=styles["H1"],
    )
    styles["H2"] = ParagraphStyle(
        "H2", fontName=_SERIF_BOLD, fontSize=14, leading=18, textColor=PRIMARY,
        spaceBefore=10, spaceAfter=6,
    )
    styles["ReportSub"] = ParagraphStyle(
        "ReportSub", fontName=_SANS_BOLD, fontSize=12, leading=16, textColor=PRIMARY,
        spaceBefore=8, spaceAfter=4,
    )
    # The written report's own "###" level — the per-category heading inside a
    # Personal or project part. Distinct from H2 so it never lands in the contents,
    # which lists the document's structured sections, not the prose's.
    styles["ReportSubSub"] = ParagraphStyle(
        "ReportSubSub", fontName=_SANS_BOLD, fontSize=10.5, leading=14,
        textColor=TEXT_SECONDARY, spaceBefore=6, spaceAfter=3,
    )
    styles["Body"] = ParagraphStyle(
        "Body", fontName=_SANS, fontSize=10, leading=15, textColor=TEXT,
        spaceAfter=6,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet", parent=styles["Body"], leftIndent=14, bulletIndent=2, spaceAfter=3,
    )
    styles["ItemTitle"] = ParagraphStyle(
        "ItemTitle", fontName=_SANS_BOLD, fontSize=10.5, leading=14, textColor=TEXT,
        spaceAfter=1,
    )
    styles["ItemMeta"] = ParagraphStyle(
        "ItemMeta", fontName=_SANS, fontSize=8.5, leading=12, textColor=TEXT_MUTED,
        spaceAfter=1,
    )
    styles["ItemReason"] = ParagraphStyle(
        "ItemReason", fontName=_SANS, fontSize=9.5, leading=13,
        textColor=TEXT_SECONDARY, spaceAfter=2,
    )
    styles["Muted"] = ParagraphStyle(
        "Muted", fontName=_SANS, fontSize=9.5, leading=14, textColor=TEXT_MUTED,
        spaceAfter=6,
    )
    return styles


# --- Inline markdown → reportlab mini-HTML --------------------------------- #
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _inline(text: str) -> str:
    """Escape XML, then re-apply markdown links and bold as reportlab tags."""
    out = escape(text or "")
    out = _LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" color="#4D6733">{m.group(1)}</a>', out
    )
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    return out


def _markdown_flowables(md: str, styles: dict[str, ParagraphStyle]) -> list:
    """Convert the briefing markdown into a small set of reportlab flowables."""
    flow: list = []
    para: list[str] = []

    def flush():
        if para:
            flow.append(Paragraph(_inline(" ".join(para)), styles["Body"]))
            para.clear()

    for raw in (md or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("### "):
            flush()
            flow.append(Paragraph(_inline(stripped[4:]), styles["ReportSubSub"]))
        elif stripped.startswith("## "):
            flush()
            flow.append(Paragraph(_inline(stripped[3:]), styles["ReportSub"]))
        elif stripped.startswith("# "):
            flush()
            flow.append(Paragraph(_inline(stripped[2:]), styles["ReportSub"]))
        elif stripped[:2] in ("- ", "* "):
            flush()
            flow.append(
                Paragraph(_inline(stripped[2:]), styles["Bullet"], bulletText="•")
            )
        else:
            para.append(stripped)
    flush()
    return flow


# --- Item + table rendering ------------------------------------------------ #
def _match_tag(match_percent: int | None) -> str:
    if isinstance(match_percent, int):
        return f'<font color="#5E7A3E"><b>{match_percent}% match</b></font>'
    return ""


def _item_flowable(item: ReportItem, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    """One found item as a compact, self-contained block."""
    title = _inline(item.title)
    if item.url:
        title = f'<a href="{escape(item.url)}" color="#2E3627">{title}</a>'
    tags = []
    if item.is_new:
        tags.append('<font color="#C9A35A"><b>NEW</b></font>')
    match = _match_tag(item.match_percent)
    if match:
        tags.append(match)
    tag_line = "  ·  ".join(tags)
    title_html = title + (f'  <font size="8">{tag_line}</font>' if tag_line else "")

    parts: list = [Paragraph(title_html, styles["ItemTitle"])]

    meta_bits = []
    if item.source:
        meta_bits.append(escape(item.source))
    if item.cluster_label:
        meta_bits.append(escape(item.cluster_label))
    if item.deadline_date:
        meta_bits.append(
            f'<font color="#B07C1F">Deadline {escape(item.deadline_date)}</font>'
        )
    if meta_bits:
        parts.append(Paragraph("  ·  ".join(meta_bits), styles["ItemMeta"]))

    reason = item.reason or item.headline
    if reason:
        parts.append(Paragraph(_inline(reason), styles["ItemReason"]))
    parts.append(Spacer(1, 4))
    return KeepTogether(parts)


def _summary_table(data: ReportData, styles: dict[str, ParagraphStyle]) -> Table:
    """The report's opening table: a row per part, a column per category.

    Every cell is a count of what is **new today and above the relevance floor** —
    the same set the sections below list — so the table is a map of the document
    rather than a second, larger set of numbers to reconcile against it.
    """
    label_style = ParagraphStyle(
        "SummaryLabel", fontName=_SANS, fontSize=9.5, leading=12, textColor=TEXT
    )
    header = ["", *[CATEGORY_LABELS.get(c, c.title()) for c in data.categories]]
    rows: list[list] = [header]
    for part in data.parts:
        rows.append(
            [
                Paragraph(escape(part.label), label_style),
                *[str(part.counts.get(c, 0)) for c in data.categories],
            ]
        )
    # The label column takes what the category columns leave; the categories are
    # single digits in the ordinary case, so they need very little.
    span = 6.7 * inch
    columns = max(len(data.categories), 1)
    category_width = min(1.15 * inch, (span - 1.6 * inch) / columns)
    table = Table(
        rows,
        colWidths=[span - category_width * len(data.categories)]
        + [category_width] * len(data.categories),
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFDF8")),
        ("FONTNAME", (0, 0), (-1, 0), _SANS_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), _SANS),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, SURFACE_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]
    # The Personal row is the reader's own; setting it apart keeps a long project
    # list from reading as though the first row were just another project.
    if data.parts and data.parts[0].kind == "personal":
        style.append(("FONTNAME", (0, 1), (-1, 1), _SANS_BOLD))
    table.setStyle(TableStyle(style))
    return table


# --- Page decoration ------------------------------------------------------- #
def _decorate(canvas, doc) -> None:
    """Paint the cream background + a footer wordmark and page number."""
    canvas.saveState()
    canvas.setFillColor(BG)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    # Footer rule + text.
    y = 0.55 * inch
    canvas.setStrokeColor(DIVIDER)
    canvas.setLineWidth(0.5)
    canvas.line(_MARGIN, y + 10, doc.pagesize[0] - _MARGIN, y + 10)
    canvas.setFont(_SANS, 8)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(_MARGIN, y, "Mycelium · Mylo daily research report")
    canvas.drawRightString(doc.pagesize[0] - _MARGIN, y, f"Page {doc.page}")
    canvas.restoreState()


class _ReportDoc(SimpleDocTemplate):
    """SimpleDocTemplate that feeds H1/H2 headings into the table of contents."""

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name == "H1":
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))
        elif name == "H2":
            self.notify("TOCEntry", (1, flowable.getPlainText(), self.page))


def _toc(styles: dict[str, ParagraphStyle]) -> TableOfContents:
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC0", fontName=_SANS_BOLD, fontSize=11, leading=18, textColor=TEXT,
        ),
        ParagraphStyle(
            "TOC1", fontName=_SANS, fontSize=10, leading=15, leftIndent=16,
            textColor=TEXT_SECONDARY,
        ),
    ]
    return toc


# --- Public entry point ---------------------------------------------------- #
def render_report_pdf(data: ReportData) -> bytes:
    """Render ``data`` to a PDF and return the raw bytes."""
    styles = _styles()
    buffer = BytesIO()
    doc = _ReportDoc(
        buffer,
        pagesize=LETTER,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"Mylo Daily Research Report — {data.generated_on}",
        author="Mycelium",
    )

    story: list = []

    # 1. Cover.
    story.append(Spacer(1, 0.6 * inch))
    story.append(Paragraph("Mylo Daily Research Report", styles["Cover"]))
    story.append(
        Paragraph(f"Prepared for {escape(data.display_name)}", styles["CoverSub"])
    )
    story.append(Paragraph(escape(data.generated_on), styles["CoverSub"]))
    story.append(Spacer(1, 0.35 * inch))
    story.append(Paragraph(escape(data.summary_line()), styles["Muted"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(_summary_table(data, styles))
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            "New today, for you and for each project you are on. Items that did not "
            "clear the relevance bar are left on your feeds and in search.",
            styles["ItemMeta"],
        )
    )
    story.append(PageBreak())

    # 2. Table of contents.
    story.append(Paragraph("Contents", styles["TocTitle"]))
    story.append(_toc(styles))
    story.append(PageBreak())

    # 3. The written report (main section).
    story.append(Paragraph("Your Mylo Report", styles["H1"]))
    body = _markdown_flowables(data.briefing_markdown, styles)
    if body:
        story.extend(body)
    else:
        story.append(
            Paragraph(
                "Mylo has no written summary for today. The matched items are listed "
                "below.",
                styles["Muted"],
            )
        )
    story.append(PageBreak())

    # 4. The reader's own part, then one section per project. A project with
    #    nothing today is skipped here — its zero row is already in the table, and a
    #    page of empty headings is the crowding this report is meant to end.
    for index, part in enumerate(data.parts):
        if part.kind == "project" and not part.total:
            continue
        if index:
            story.append(PageBreak())
        _extend_part(story, part, data.categories, styles)

    doc.multiBuild(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buffer.getvalue()


def _extend_part(
    story: list,
    part: ReportPart,
    categories: list[str],
    styles: dict[str, ParagraphStyle],
) -> None:
    """One part: its title, then a capped ``Top N <Category>`` section per area."""
    story.append(Paragraph(escape(part.label), styles["H1"]))
    if part.kind == "project":
        story.append(Paragraph("Project", styles["Muted"]))
    if not part.shown:
        story.append(
            Paragraph("Nothing has reached this top list yet.", styles["Muted"])
        )
        return
    for category in categories:
        items = part.items.get(category) or []
        if not items:
            continue
        noun = SECTION_NOUNS.get(category, CATEGORY_LABELS.get(category, category))
        story.append(Paragraph(f"Top {part.cap} {noun}", styles["H2"]))
        found = part.slate_sizes.get(category, len(items))
        if found > len(items):
            story.append(
                Paragraph(
                    f"Showing {len(items)} of {found} — the rest are on your "
                    f"{noun.lower()} page.",
                    styles["Muted"],
                )
            )
        for item in items:
            story.append(_item_flowable(item, styles))
