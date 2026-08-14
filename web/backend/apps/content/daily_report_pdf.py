"""Render a :class:`apps.content.daily_report.ReportData` into a PDF (reportlab).

A calm, scholarly one-file report in the Mycelium light palette (cream page, forest
green headings, restrained gold for opportunity/deadline signals — see
``docs/styles.md``). The document is:

1. a cover — centred on the page in both directions, under Mylo and the Mycelium
   logo — with the recipient, date, and the **summary table**: one row per part
   (the reader's own, then each project) against a column per category, each cell
   the count of what is new today,
2. a **table of contents** (real page numbers, resolved by a two-pass build) whose
   entries are **links**: every heading is bookmarked and every contents line jumps
   to it,
3. **Your Mylo Report** — the written briefing, rendered with the same hierarchy the
   listings use, and
4. one section per part — the reader's own (``Top 25 Articles`` / ``Top 25 Grants``
   / …) then one per project, capped at ten.

Every level of the document is one of four heading styles, and each maps to one
table-of-contents depth, so the contents page is a true map of the hierarchy rather
than a list of the top two levels:

===== ===================== =============================================
Level Style                 What carries it
===== ===================== =============================================
0     ``H1``                A part: "Your Mylo Report", the reader's own
                            section, each project
1     ``H2``                A section within a part: ``Top 25 Articles``,
                            or the written report's ``## <part>``
2     ``H3``                A category within the written report
3     ``H4``                A focus theme, drawn as a rounded pill
===== ===================== =============================================

Every ranked entry in the document — in the written report and in every Top-N
listing — is the same three-column row (:func:`_entry_row`): its number, its
content, and its chips. The list is a ranking and the numbers say so; the percent
match and ``NEW`` are rounded chips down the right edge rather than a run of small
grey text or an inline highlight, because "is this new and how well does it match
me" is the question a reader scans the page with.

Each list is the reader's whole top slice, every day — not just what arrived. The
``NEW`` chip marks the items that entered it on this run, which is the only part of
the page that changes when the day is quiet.

There is no "everything Mylo found" appendix. Reprinting the entire feed at the
bottom of a daily report made a long document longer without answering a question
anyone had; the feeds and search are where an exhaustive list belongs.

No system fonts are required: headings use Times (scholarly serif) and body uses
Helvetica, both bundled with reportlab, so this renders anywhere the backend runs.
The cover's two marks are the only image assets, they live in ``report_assets/``
beside this module, and a missing one is logged and skipped rather than raised —
cover art is decoration, and a report that cannot find its logo is still the
document the reader needs. :func:`render_report_pdf` returns the PDF as ``bytes``.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
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

logger = logging.getLogger(__name__)

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

#: Hex strings for the inline ``<font color=…>`` runs inside paragraphs.
_LINK_HEX = "#4D6733"
_TITLE_HEX = "#2E3627"
_MATCH_HEX = "#3F5429"
_MATCH_BG_HEX = "#DCE7CC"
_NEW_HEX = "#7A5A14"
_NEW_BG_HEX = "#E7D8B8"
_DEADLINE_HEX = "#B07C1F"

_SERIF = "Times-Roman"
_SERIF_BOLD = "Times-Bold"
_SANS = "Helvetica"
_SANS_BOLD = "Helvetica-Bold"

_MARGIN = 0.9 * inch
#: The usable text width — the page less both margins. Every table here is laid out
#: against it, so a column change never has to re-derive the page geometry.
_CONTENT_WIDTH = LETTER[0] - 2 * _MARGIN

#: The right-hand chip column on a found item (percent match, ``NEW``).
_CHIP_WIDTH = 0.86 * inch
#: The hanging rank-number column on a found item.
_RANK_WIDTH = 0.34 * inch
#: Corner radius shared by every filled container — chips and theme pills. Square
#: corners read as a highlighter stripe; rounded ones read as a badge.
_RADIUS = 4
#: Horizontal breathing room inside a theme pill.
_PILL_PAD_X = 8
_PILL_PAD_Y = 3

#: The cover's two marks — Mylo and the Mycelium logo — checked in beside this
#: module so a container that cannot reach the repo's art pipeline still renders a
#: cover. Both are 400px tall and drawn at :data:`_MARK_HEIGHT`; a missing or
#: unreadable file simply drops out (see :func:`_cover_marks`).
_ASSETS = Path(__file__).with_name("report_assets")
_MARK_HEIGHT = 0.95 * inch
#: The gap between the two marks.
_MARK_GAP = 0.3 * inch


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}
    # The cover is centred on the page in both directions (:class:`_CenteredCover`
    # handles the vertical), so everything on it is centred type.
    styles["Cover"] = ParagraphStyle(
        "Cover", parent=base["Title"], fontName=_SERIF_BOLD, fontSize=30,
        leading=34, textColor=PRIMARY_HOVER, spaceAfter=0, alignment=TA_CENTER,
    )
    styles["CoverSub"] = ParagraphStyle(
        "CoverSub", fontName=_SANS, fontSize=12, leading=17,
        textColor=TEXT_SECONDARY, spaceAfter=0, alignment=TA_CENTER,
    )
    styles["CoverNote"] = ParagraphStyle(
        "CoverNote", fontName=_SANS, fontSize=9.5, leading=14, textColor=TEXT_MUTED,
        spaceAfter=0, alignment=TA_CENTER,
    )
    styles["CoverFoot"] = ParagraphStyle(
        "CoverFoot", fontName=_SANS, fontSize=8.5, leading=12, textColor=TEXT_MUTED,
        spaceAfter=0, alignment=TA_CENTER,
    )
    # --- The four heading levels. Each maps to one contents depth (see the module
    # docstring); nothing else in the document is allowed to look like a heading.
    # All four are ``keepWithNext``: a heading stranded at the foot of a page is the
    # one layout failure that makes a structured document read as an unstructured
    # one, because the reader meets the list before its title.
    styles["H1"] = ParagraphStyle(
        "H1", fontName=_SERIF_BOLD, fontSize=20, leading=24, textColor=PRIMARY_HOVER,
        spaceBefore=8, spaceAfter=4, keepWithNext=1,
    )
    styles["H2"] = ParagraphStyle(
        "H2", fontName=_SERIF_BOLD, fontSize=14.5, leading=18, textColor=PRIMARY,
        spaceBefore=14, spaceAfter=6, keepWithNext=1,
    )
    styles["H3"] = ParagraphStyle(
        "H3", fontName=_SANS_BOLD, fontSize=11.5, leading=15, textColor=TEXT,
        spaceBefore=11, spaceAfter=4, keepWithNext=1,
    )
    # A focus theme. Set *larger* than the items beneath it and drawn on a rounded
    # pill (:class:`_PillHeading`) — at 9.5pt with no ground it was smaller than the
    # entries it introduced, which is the one thing a heading cannot be.
    styles["H4"] = ParagraphStyle(
        "H4", fontName=_SANS_BOLD, fontSize=11.5, leading=15, textColor=PRIMARY_HOVER,
        spaceBefore=13, spaceAfter=7, leftIndent=_PILL_PAD_X, keepWithNext=1,
    )
    # Same look as H1 but a distinct name, so afterFlowable does NOT list the
    # "Contents" page-title as its own table-of-contents entry.
    styles["TocTitle"] = ParagraphStyle("TocTitle", parent=styles["H1"])
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
    styles["Rank"] = ParagraphStyle(
        "Rank", fontName=_SERIF_BOLD, fontSize=12, leading=15, textColor=SECONDARY,
        alignment=TA_RIGHT,
    )
    styles["Chip"] = ParagraphStyle(
        "Chip", fontName=_SANS_BOLD, fontSize=11, leading=12, textColor=PRIMARY_HOVER,
        alignment=TA_CENTER,
    )
    # ``NEW`` is a flag, not a headline. At the match chip's 11pt bold it was the
    # loudest thing in the column while carrying the least information — the
    # percent is the number the reader is actually comparing entries on.
    styles["ChipFlag"] = ParagraphStyle(
        "ChipFlag", fontName=_SANS, fontSize=9, leading=11, textColor=PRIMARY_HOVER,
        alignment=TA_CENTER,
    )
    styles["ChipNote"] = ParagraphStyle(
        "ChipNote", fontName=_SANS, fontSize=6.5, leading=8, textColor=TEXT_SECONDARY,
        alignment=TA_CENTER,
    )
    styles["Muted"] = ParagraphStyle(
        "Muted", fontName=_SANS, fontSize=9.5, leading=14, textColor=TEXT_MUTED,
        spaceAfter=6,
    )
    return styles


# --- Inline markdown → reportlab mini-HTML --------------------------------- #
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
#: The report's item grammar (see :mod:`apps.content.briefing_sections`): a bolded
#: ``**NEW**`` marker, ``88% match``, and ``deadline 2026-09-01``. Each is a fact a
#: reader scans for, so each is lifted out of the run of text and given a colour.
_NEW_MARKER_RE = re.compile(r"\*\*NEW\*\*")
_MATCH_RE = re.compile(r"\b(\d{1,3})%\s+match\b", re.IGNORECASE)
_DEADLINE_RE = re.compile(r"\bdeadline\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
#: A numbered item line — ``1. **[Title](url)** — 88% match``.
_NUMBERED_RE = re.compile(r"^(\d{1,3})[.)]\s+(.*)$")


def _inline(text: str) -> str:
    """Escape XML, then re-apply the report's markdown as reportlab tags.

    Deliberately draws **no filled background** anywhere. A reportlab inline
    ``backcolor`` is a square-cornered stripe behind the glyphs — a highlighter mark,
    not a badge — so the two signals it used to paint that way (``NEW``, the percent
    match) are lifted out of the text entirely and rendered as rounded chips beside
    the entry (:func:`_chip`). What is left here is colour and weight, which is all
    an inline run can carry without looking marked-up.
    """
    out = escape(text or "")
    out = _LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" color="{_LINK_HEX}">{m.group(1)}</a>', out
    )
    out = _NEW_MARKER_RE.sub(f'<font color="{_NEW_HEX}"><b>NEW</b></font>', out)
    out = _MATCH_RE.sub(
        lambda m: f'<font color="{_MATCH_HEX}"><b>{m.group(1)}% match</b></font>', out
    )
    out = _DEADLINE_RE.sub(
        lambda m: f'<font color="{_DEADLINE_HEX}"><b>deadline {m.group(1)}</b></font>',
        out,
    )
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    return out


class _PillHeading(Paragraph):
    """A heading drawn on a rounded, filled pill.

    A ``Paragraph`` subclass rather than a one-cell ``Table`` so it still reaches
    ``afterFlowable`` as a heading and keeps its place in the contents page — a
    table would look the same and vanish from the document's map.

    The pill is sized to the text, not to the column: a full-width band would read
    as a section rule, and the point of the shape is that the theme is a label.
    """

    def _text_width(self) -> float:
        """The widest laid-out line, taken from the wrap reportlab already did.

        Not ``stringWidth`` of the plain text: the paragraph may carry inline runs
        in other faces and sizes, and measuring it a second way is how the pill ends
        up a different width from the text sitting in it.
        """
        style = self.style
        available = self.width - style.leftIndent - style.rightIndent
        widths = [
            available
            - (line[0] if isinstance(line, list | tuple) else line.extraSpace)
            for line in getattr(getattr(self, "blPara", None), "lines", None) or []
        ]
        return max(widths) if widths else available

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(SURFACE_ALT)
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        # The text is drawn at ``leftIndent`` (reportlab's own origin for an
        # indented paragraph), so the pill starts one pad to the left of that and
        # ends one pad past the text — equal on both sides.
        canvas.roundRect(
            self.style.leftIndent - _PILL_PAD_X,
            -_PILL_PAD_Y,
            self._text_width() + 2 * _PILL_PAD_X,
            self.height + 2 * _PILL_PAD_Y,
            _RADIUS,
            fill=1,
            stroke=1,
        )
        canvas.restoreState()
        super().draw()


#: The signals a numbered item's title line carries, in the grammar
#: :mod:`apps.content.briefing_sections` emits. Each is pulled out of the line and
#: rendered as a chip, leaving the title to be a title.
_ITEM_NEW_RE = re.compile(r"\*\*NEW\*\*")
_ITEM_MATCH_RE = re.compile(r"\b(\d{1,3})%\s+match\b", re.IGNORECASE)
_ITEM_DEADLINE_RE = re.compile(
    r"\bdeadline\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE
)
#: Whatever separators the removed signals leave stranded at the end of the line.
_TRAILING_SEPARATORS_RE = re.compile(r"[\s··—–-]+$")


def _split_item_line(text: str) -> tuple[str, bool, int | None, str]:
    """Split a written item's title line into ``(title, is_new, match, deadline)``.

    Order-independent, because the line is model-written as often as it is
    generated: each signal is matched wherever it sits, removed, and the separators
    it leaves behind are cleaned off the tail.
    """
    is_new = bool(_ITEM_NEW_RE.search(text))
    rest = _ITEM_NEW_RE.sub("", text)

    match = _ITEM_MATCH_RE.search(rest)
    percent = int(match.group(1)) if match else None
    rest = _ITEM_MATCH_RE.sub("", rest)

    found = _ITEM_DEADLINE_RE.search(rest)
    deadline = found.group(1) if found else ""
    rest = _ITEM_DEADLINE_RE.sub("", rest)

    # Collapse the runs of " · " / " — " the removals opened up mid-line, then trim.
    rest = re.sub(r"\s*[·]\s*(?=[·—–-]|\s*$)", " ", rest)
    return _TRAILING_SEPARATORS_RE.sub("", rest).strip(), is_new, percent, deadline


def _markdown_flowables(md: str, styles: dict[str, ParagraphStyle]) -> list:
    """Convert the briefing markdown into reportlab flowables.

    Parses exactly the grammar :mod:`apps.content.briefing_sections` emits —
    ``##``/``###``/``####`` headings, ``N.`` numbered items whose following line is
    that item's rationale, ``-`` bullets, and blank-line paragraphs. Anything else
    degrades to a paragraph, so an unexpected construct still reads.
    """
    flow: list = []
    para: list[str] = []
    #: The numbered item currently open — its rank and the lines gathered for it.
    item: tuple[str, list[str]] | None = None

    def flush_para():
        if para:
            flow.append(Paragraph(_inline(" ".join(para)), styles["Body"]))
            para.clear()

    def flush_item():
        nonlocal item
        if item is None:
            return
        rank, lines = item
        flow.extend(_written_item_flowables(rank, lines, styles))
        item = None

    def flush():
        flush_item()
        flush_para()

    for raw in (md or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("#### "):
            flush()
            flow.append(_PillHeading(_inline(stripped[5:]), styles["H4"]))
        elif stripped.startswith("### "):
            flush()
            flow.append(Paragraph(_inline(stripped[4:]), styles["H3"]))
        elif stripped.startswith("## "):
            flush()
            flow.append(Paragraph(_inline(stripped[3:]), styles["H2"]))
        elif stripped.startswith("# "):
            flush()
            flow.append(Paragraph(_inline(stripped[2:]), styles["H2"]))
        elif _NUMBERED_RE.match(stripped):
            flush()
            match = _NUMBERED_RE.match(stripped)
            assert match is not None
            item = (match.group(1), [match.group(2)])
        elif stripped[:2] in ("- ", "* "):
            flush()
            flow.append(
                Paragraph(_inline(stripped[2:]), styles["Bullet"], bulletText="•")
            )
        elif item is not None:
            # The line after a numbered item is that item's rationale, not a new
            # paragraph — keeping them in one flowable is what stops a page break
            # from stranding a title above its own explanation.
            item[1].append(stripped)
        else:
            para.append(stripped)
    flush()
    return flow


# --- Item + table rendering ------------------------------------------------ #
def _chip(
    text: str,
    note: str,
    styles: dict[str, ParagraphStyle],
    *,
    bg,
    fg,
    base: str = "Chip",
) -> Table:
    """A small filled chip — the percent match, or ``NEW``.

    A chip rather than another run of 8.5pt grey: the match percent is the single
    number a reader uses to decide whether to read the entry at all, and it was
    losing that argument to the title beside it. ``base`` picks the weight, so the
    two chips can share a shape without shouting equally loudly.
    """
    style = ParagraphStyle("ChipInner", parent=styles[base], textColor=fg)
    cell: list = [Paragraph(text, style)]
    if note:
        cell.append(Paragraph(note, styles["ChipNote"]))
    chip = Table([[cell]], colWidths=[_CHIP_WIDTH])
    chip.setStyle(
        TableStyle(
            [
                # Rounded, not square: a square filled rectangle behind a number
                # reads as a highlighter stripe, which is exactly what this chip
                # replaced in the written report.
                ("ROUNDEDCORNERS", [_RADIUS, _RADIUS, _RADIUS, _RADIUS]),
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return chip


def _chip_stack(
    match_percent: int | None, is_new: bool, styles: dict[str, ParagraphStyle]
) -> list:
    """The right-hand column of an entry: its match chip, then ``NEW``."""
    stack: list = []
    if isinstance(match_percent, int):
        stack.append(
            _chip(
                f"{match_percent}%",
                "match",
                styles,
                bg=HexColor(_MATCH_BG_HEX),
                fg=HexColor(_MATCH_HEX),
            )
        )
    if is_new:
        if stack:
            stack.append(Spacer(1, 3))
        stack.append(
            _chip(
                "NEW",
                "",
                styles,
                bg=HexColor(_NEW_BG_HEX),
                fg=HexColor(_NEW_HEX),
                base="ChipFlag",
            )
        )
    return stack


def _entry_row(
    rank: int | str,
    body: list,
    match_percent: int | None,
    is_new: bool,
    styles: dict[str, ParagraphStyle],
) -> list:
    """One ranked entry: its number, its content, and its chips.

    The report's single entry shape, used by the written report and by every Top-N
    listing. Laid out as a three-column row so the numbers line up down the page and
    the chips line up down the right edge — which is what makes a ranked list read
    as one rather than as twenty-five paragraphs.

    Returned as a plain list rather than a ``KeepTogether``: a single-row table does
    not split, so the entry is already atomic, and nesting it in a ``KeepTogether``
    that a caller then nests again pushed every section onto a page of its own.
    """
    # An empty cell is "" rather than an empty list — reportlab measures a list cell
    # by wrapping its flowables, and there are none to wrap.
    chips = _chip_stack(match_percent, is_new, styles) or ""
    row = Table(
        [[Paragraph(f"{rank}.", styles["Rank"]), body, chips]],
        colWidths=[
            _RANK_WIDTH,
            _CONTENT_WIDTH - _RANK_WIDTH - _CHIP_WIDTH - 0.18 * inch,
            _CHIP_WIDTH + 0.18 * inch,
        ],
    )
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (2, 0), (2, 0), 0),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, DIVIDER),
            ]
        )
    )
    return [row, Spacer(1, 3)]


def _item_flowables(
    item: ReportItem, rank: int, styles: dict[str, ParagraphStyle]
) -> list:
    """One found item from a Top-N listing, as the report's standard entry row."""
    title = _inline(item.title)
    if item.url:
        title = f'<a href="{escape(item.url)}" color="{_TITLE_HEX}">{title}</a>'
    body: list = [Paragraph(title, styles["ItemTitle"])]

    meta_bits = []
    if item.source:
        meta_bits.append(escape(item.source))
    if item.cluster_label:
        meta_bits.append(escape(item.cluster_label))
    if item.deadline_date:
        meta_bits.append(
            f'<font color="{_DEADLINE_HEX}"><b>Deadline '
            f"{escape(item.deadline_date)}</b></font>"
        )
    if meta_bits:
        body.append(Paragraph("  ·  ".join(meta_bits), styles["ItemMeta"]))

    reason = item.reason or item.headline
    if reason:
        body.append(Paragraph(_inline(reason), styles["ItemReason"]))

    return _entry_row(rank, body, item.match_percent, item.is_new, styles)


def _written_item_flowables(
    rank: str, lines: list[str], styles: dict[str, ParagraphStyle]
) -> list:
    """One numbered item from the *written* report, as the same entry row.

    The signals are pulled out of the title line and given to the chip column, so a
    Mylo Report entry and a Top-25 entry are the same object on the page. They were
    two different shapes for no reason other than one arriving as markdown.
    """
    title, is_new, match_percent, deadline = _split_item_line(lines[0])
    body: list = [Paragraph(_inline(title), styles["ItemTitle"])]
    if deadline:
        body.append(
            Paragraph(
                f'<font color="{_DEADLINE_HEX}"><b>Deadline '
                f"{escape(deadline)}</b></font>",
                styles["ItemMeta"],
            )
        )
    reason = " ".join(lines[1:]).strip()
    if reason:
        body.append(Paragraph(_inline(reason), styles["ItemReason"]))
    return _entry_row(rank, body, match_percent, is_new, styles)


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
        hAlign="CENTER",
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
    # The reader's own row is not just another project; setting it apart keeps a
    # long project list from reading as though the first row were one of them.
    if data.parts and data.parts[0].kind == "personal":
        style.append(("FONTNAME", (0, 1), (-1, 1), _SANS_BOLD))
    table.setStyle(TableStyle(style))
    return table


# --- Cover ----------------------------------------------------------------- #
def _mark(name: str) -> Image | None:
    """One cover mark, scaled to :data:`_MARK_HEIGHT`, or ``None`` if unusable.

    Cover art is decoration: a report that cannot find its logo is still the
    document the reader needs, so a missing or corrupt file is logged once and
    dropped rather than raised. The alternative is a backend that stops delivering
    reports because an image went missing.
    """
    path = _ASSETS / name
    try:
        # reportlab reads the file lazily, on the first dimension access rather
        # than at construction, so the measuring has to be inside the guard too.
        image = Image(str(path))
        ratio = image.imageWidth / image.imageHeight
    except Exception as exc:  # noqa: BLE001 — any unreadable asset => no mark
        logger.warning(
            "report cover art %s unusable (%s); rendering without it.", path, exc
        )
        return None
    image.drawHeight = _MARK_HEIGHT
    image.drawWidth = _MARK_HEIGHT * ratio
    return image


def _cover_marks() -> Table | None:
    """Mylo and the Mycelium logo, side by side and centred, or ``None``.

    They are a pair on purpose: the mascot alone is a character and the logo alone
    is a company, and the report is from both — Mylo did the reading, Mycelium
    vouches for it.
    """
    marks = [m for m in (_mark("mylo-headshot.png"), _mark("mycelium-logo.png")) if m]
    if not marks:
        return None
    row: list = []
    widths: list[float] = []
    for index, mark in enumerate(marks):
        if index:
            row.append("")
            widths.append(_MARK_GAP)
        row.append(mark)
        widths.append(mark.drawWidth)
    table = Table([row], colWidths=widths, hAlign="CENTER")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


class _CenteredCover(Flowable):
    """Holds the cover's flowables and centres them in the page's whole frame.

    Platypus lays a story out from the top, so vertical centring is not something a
    style can ask for — the block has to measure its own content against the space
    it is given and place itself. Horizontal centring is left to the content
    (``TA_CENTER`` on the paragraphs, ``hAlign`` on the tables), which is why the
    marks row and the summary table both come in already centred.

    If the content is taller than the page — a reader on enough projects that the
    summary table runs long — it gives up centring and hands its flowables back to
    the frame to lay out normally, rather than centring them off the page.
    """

    def __init__(self, content: list) -> None:
        super().__init__()
        self.content = list(content)
        self._available = (0.0, 0.0)
        self._content_height = 0.0

    def _measure(self, width: float, height: float) -> float:
        return sum(f.wrapOn(self.canv, width, height)[1] for f in self.content)

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self._available = (availWidth, availHeight)
        self._content_height = self._measure(availWidth, availHeight)
        if self._content_height > availHeight:
            return availWidth, self._content_height
        return availWidth, availHeight

    def split(self, availWidth: float, availHeight: float) -> list:
        return self.content if self._content_height > availHeight else []

    def draw(self) -> None:
        width, height = self._available
        y = height - max((height - self._content_height) / 2, 0)
        for flowable in self.content:
            drawn_width, drawn_height = flowable.wrapOn(self.canv, width, height)
            y -= drawn_height
            # ``_sW`` is the slack an ``hAlign`` centres within; without it a table
            # narrower than the frame would sit hard against the left margin.
            flowable.drawOn(self.canv, 0, y, width - drawn_width)


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


#: Heading style name -> its depth in the table of contents.
_TOC_LEVELS = {"H1": 0, "H2": 1, "H3": 2, "H4": 3}


class _ReportDoc(SimpleDocTemplate):
    """SimpleDocTemplate that feeds every heading into a *linked* contents page.

    Each heading is bookmarked under a generated key and that key is handed to the
    contents entry, which is what makes the line clickable — a contents page you
    cannot navigate from is a list of page numbers, not a table of contents. The key
    has to be stable between the two passes of ``multiBuild``, so it is derived from
    a counter that resets whenever the story is rebuilt.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._heading_seq = 0

    def beforeDocument(self) -> None:  # pragma: no cover - reportlab hook
        self._heading_seq = 0

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        level = _TOC_LEVELS.get(flowable.style.name)
        if level is None:
            return
        self._heading_seq += 1
        key = f"sec{self._heading_seq}"
        self.canv.bookmarkPage(key)
        self.notify("TOCEntry", (level, flowable.getPlainText(), self.page, key))


def _toc(styles: dict[str, ParagraphStyle]) -> TableOfContents:
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC0", fontName=_SERIF_BOLD, fontSize=12, leading=20, textColor=TEXT,
            spaceBefore=6,
        ),
        ParagraphStyle(
            "TOC1", fontName=_SANS_BOLD, fontSize=10, leading=15, leftIndent=16,
            textColor=TEXT_SECONDARY,
        ),
        ParagraphStyle(
            "TOC2", fontName=_SANS, fontSize=9.5, leading=13.5, leftIndent=32,
            textColor=TEXT_SECONDARY,
        ),
        ParagraphStyle(
            "TOC3", fontName=_SANS, fontSize=9, leading=12.5, leftIndent=48,
            textColor=TEXT_MUTED,
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

    # 1. Cover — centred on the page, under Mylo and the Mycelium logo.
    cover: list = []
    marks = _cover_marks()
    if marks is not None:
        cover.append(marks)
        cover.append(Spacer(1, 0.32 * inch))
    cover.append(Paragraph("Mylo Daily Research Report", styles["Cover"]))
    cover.append(Spacer(1, 0.14 * inch))
    cover.append(
        Paragraph(f"Prepared for {escape(data.display_name)}", styles["CoverSub"])
    )
    cover.append(Paragraph(escape(data.generated_on), styles["CoverSub"]))
    cover.append(Spacer(1, 0.34 * inch))
    cover.append(Paragraph(escape(data.summary_line()), styles["CoverNote"]))
    cover.append(Spacer(1, 0.16 * inch))
    cover.append(_summary_table(data, styles))
    cover.append(Spacer(1, 0.14 * inch))
    cover.append(
        Paragraph(
            "New today, for you and for each project you are on. Items that did not "
            "clear the relevance bar are left on your feeds and in search.",
            styles["CoverFoot"],
        )
    )
    story.append(_CenteredCover(cover))
    story.append(PageBreak())

    # 2. Table of contents — every line links to its heading.
    story.append(Paragraph("Contents", styles["TocTitle"]))
    story.append(
        Paragraph("Every entry below jumps to its section.", styles["Muted"])
    )
    story.append(_toc(styles))
    story.append(PageBreak())

    # 3. The written report (main section).
    _extend_title(story, "Your Mylo Report", styles)
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


def _extend_title(story: list, text: str, styles: dict[str, ParagraphStyle]) -> None:
    """A top-level (``H1``) section title, underlined by a hairline rule."""
    story.append(Paragraph(escape(text), styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=8))


def _extend_part(
    story: list,
    part: ReportPart,
    categories: list[str],
    styles: dict[str, ParagraphStyle],
) -> None:
    """One part: its title, then a capped ``Top N <Category>`` section per area."""
    _extend_title(story, part.label, styles)
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
        opening: list = [Paragraph(f"Top {part.cap} {noun}", styles["H2"])]
        found = part.slate_sizes.get(category, len(items))
        if found > len(items):
            opening.append(
                Paragraph(
                    f"Showing {len(items)} of {found} — the rest are on your "
                    f"{noun.lower()} page.",
                    styles["Muted"],
                )
            )
        first = _item_flowables(items[0], 1, styles)
        # The heading travels with its first entry: a "Top 25 Conferences" alone at
        # the foot of a page is precisely the loss of hierarchy this layout exists
        # to prevent.
        story.append(KeepTogether(opening + first))
        for rank, item in enumerate(items[1:], start=2):
            story.extend(_item_flowables(item, rank, styles))
