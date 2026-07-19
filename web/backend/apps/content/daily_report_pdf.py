"""Render a :class:`apps.content.daily_report.ReportData` into a PDF (reportlab).

A calm, scholarly one-file report in the Mycelium light palette (cream page, forest
green headings, restrained gold for opportunity/deadline signals — see
``docs/styles.md``). The document is:

1. a cover with the recipient, date, and a "what Mylo found" summary table,
2. a **table of contents** (real page numbers, resolved by a two-pass build) whose
   first entry points at the written report,
3. **Your Mylo Report** — the written briefing markdown, the main section,
4. **Top 25 Articles**,
5. **Top 25 Grants, Fellowships & Conferences**, and
6. **Everything Mylo Found** — the full per-category appendix at the bottom.

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

from apps.content.daily_report import CATEGORY_LABELS, ReportData, ReportItem

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
    styles["AppendixRow"] = ParagraphStyle(
        "AppendixRow", fontName=_SANS, fontSize=9, leading=12.5, textColor=TEXT,
        spaceAfter=1,
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
        if stripped.startswith("## "):
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
    header = ["Category", "Found", "New today"]
    rows = [header]
    for category in data.categories:
        rows.append(
            [
                CATEGORY_LABELS.get(category, category.title()),
                str(data.counts.get(category, 0)),
                str(data.new_counts.get(category, 0)),
            ]
        )
    table = Table(rows, colWidths=[3.2 * inch, 1.6 * inch, 1.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFDF8")),
                ("FONTNAME", (0, 0), (-1, 0), _SANS_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), _SANS),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, SURFACE_ALT]),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
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

    # 4. Top articles.
    story.append(Paragraph("Top 25 Articles", styles["H1"]))
    _extend_items(story, data.top_papers, styles, empty="No new articles today.")
    story.append(PageBreak())

    # 5. Top opportunities.
    story.append(Paragraph("Top 25 Grants, Fellowships & Conferences", styles["H1"]))
    _extend_items(
        story,
        data.top_opportunities,
        styles,
        empty="No matching grants, fellowships, or conferences today.",
    )
    story.append(PageBreak())

    # 6. Full appendix.
    story.append(Paragraph("Everything Mylo Found", styles["H1"]))
    story.append(
        Paragraph(
            "The complete list of items Mylo surfaced for you today, by category.",
            styles["Muted"],
        )
    )
    any_appendix = False
    for category in data.categories:
        items = data.all_items.get(category, [])
        if not items:
            continue
        any_appendix = True
        label = CATEGORY_LABELS.get(category, category.title())
        story.append(Paragraph(f"{label} ({len(items)})", styles["H2"]))
        for idx, item in enumerate(items, start=1):
            story.append(_appendix_row(idx, item, styles))
    if not any_appendix:
        story.append(Paragraph("Nothing to list today.", styles["Muted"]))

    doc.multiBuild(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buffer.getvalue()


def _extend_items(
    story: list,
    items: list[ReportItem],
    styles: dict[str, ParagraphStyle],
    *,
    empty: str,
) -> None:
    if not items:
        story.append(Paragraph(empty, styles["Muted"]))
        return
    for item in items:
        story.append(_item_flowable(item, styles))


def _appendix_row(
    idx: int, item: ReportItem, styles: dict[str, ParagraphStyle]
) -> Paragraph:
    title = _inline(item.title)
    if item.url:
        title = f'<a href="{escape(item.url)}" color="#4D6733">{title}</a>'
    tail = []
    if isinstance(item.match_percent, int):
        tail.append(f"{item.match_percent}%")
    if item.deadline_date:
        tail.append(f"due {escape(item.deadline_date)}")
    suffix = ""
    if tail:
        suffix = f'  <font color="#7F8775" size="8">({" · ".join(tail)})</font>'
    return Paragraph(f"{idx}. {title}{suffix}", styles["AppendixRow"])
