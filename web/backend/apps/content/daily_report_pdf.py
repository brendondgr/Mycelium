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
listing — is the same three-column row (:func:`_entry_row`), and it is the print
half of the shape the app draws in ``portal/primitives/report-entry.tsx``. Four
zones, in this order:

1. **Rank + title** — the list is a ranking and the number says so, but the number
   is not what the reader is scanning for, so it recedes into the gutter.
2. **The insight** — the rationale's first sentence, set against a left rule. It
   answers "why am I looking at this", which is the only question the entry exists
   to answer.
3. **The note** — the rest of the rationale: the caveat, the qualification, what
   actually transfers.
4. **The meta rail** — the match percent set large over a tier-coloured bar with a
   caption naming it, then ``NEW`` and any venue rank as flags beneath.

Under the content column runs the **reference strip**: the entry's next deadline
(named by round, with the later rounds counted rather than listed), its source, and
its focus theme. Those three used to be competing lines between the title and the
reason for it, the deadline in red — an alarm attached to every dated entry, worst
on conferences, where it never even said which of the venue's rounds it meant.

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
#: CCF / CORE / THCPL rank chip. Deliberately *not* a gold/accent tint — per
#: ``docs/styles.md`` gold is reserved for grants, fellowships, deadlines, and
#: opportunity alerts, and a rank is none of those (plan D2: visual only, never
#: a relevance signal). Reuses the neutral surface/text-secondary pairing rather
#: than a fresh one-off tint, so a rank badge reads as an informational label,
#: not a second opportunity flag competing with the match chip beside it.
_RANK_HEX = "#5F6853"
_RANK_BG_HEX = "#EFE7D7"

#: The match bar's three tiers. Mirrors ``matchTier`` in the app's
#: ``primitives/match-ring.tsx`` — same thresholds, same three colours — so the
#: report and the app can never disagree about what a 95 means.
_TIER_STRONG = HexColor("#6F8F4E")
_TIER_FAIR = HexColor("#B88A3B")
_TIER_LOW = HexColor("#A85A3C")
_STRONG_MATCH = 85
_FAIR_MATCH = 60

_SERIF = "Times-Roman"
_SERIF_BOLD = "Times-Bold"
_SANS = "Helvetica"
_SANS_BOLD = "Helvetica-Bold"

_MARGIN = 0.9 * inch
#: The usable text width — the page less both margins. Every table here is laid out
#: against it, so a column change never has to re-derive the page geometry.
_CONTENT_WIDTH = LETTER[0] - 2 * _MARGIN

#: The right-hand meta rail on an entry: the match score, its bar and caption, then
#: the flags. Wider than the chip column it replaced because the caption naming the
#: number ("MATCH SCORE") has to fit on one line — an unlabelled large number in the
#: margin is the one thing this rail must not be.
_RAIL_WIDTH = 1.16 * inch
#: The hanging rank-number column on a found item.
_RANK_WIDTH = 0.34 * inch
#: The gap reportlab leaves to the right of the content cell (its ``RIGHTPADDING``).
_CELL_PAD = 6
#: The content column's usable width — what the insight's rule and the reference
#: strip are laid out against. Derived once here so a column change never has to be
#: re-derived at three call sites, which is how they drift a few points apart and
#: the rules stop lining up down the page.
_BODY_WIDTH = _CONTENT_WIDTH - _RANK_WIDTH - _RAIL_WIDTH - _CELL_PAD
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
    # The insight: the first sentence of the rationale, which is the one line that
    # says why this entry is in front of the reader. Set at body weight in the
    # primary text colour and drawn against a rule (:func:`_insight_flowable`), so
    # it separates from the qualifying sentences that follow it without shouting.
    styles["ItemInsight"] = ParagraphStyle(
        "ItemInsight", fontName=_SANS_BOLD, fontSize=9.5, leading=13.5,
        textColor=TEXT, spaceAfter=0,
    )
    #: The reference strip beneath an entry — its dates, its source, its theme.
    styles["ItemMetaStrip"] = ParagraphStyle(
        "ItemMetaStrip", fontName=_SANS, fontSize=8, leading=11,
        textColor=TEXT_SECONDARY, spaceAfter=0,
    )
    #: The match number itself. The largest thing in the rail by a wide margin —
    #: it is the number the reader compares entries on.
    styles["Score"] = ParagraphStyle(
        "Score", fontName=_SERIF_BOLD, fontSize=21, leading=22, textColor=TEXT,
        alignment=TA_RIGHT, spaceAfter=0,
    )
    #: What the number above it is. Without this the rail is a bare integer in the
    #: margin, which every reader has to decode once and some decode wrongly.
    styles["ScoreCaption"] = ParagraphStyle(
        "ScoreCaption", fontName=_SANS_BOLD, fontSize=6, leading=8,
        textColor=TEXT_MUTED, alignment=TA_RIGHT, spaceAfter=0,
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


# --- The entry's four zones ------------------------------------------------ #
def _tier_color(percent: int):
    """The match bar's colour for a percent — strong, fair, or low.

    Same three thresholds as the app's ``matchTier``. Colour is never the only
    signal here either: the number sits directly above the bar it colours.
    """
    if percent >= _STRONG_MATCH:
        return _TIER_STRONG
    if percent >= _FAIR_MATCH:
        return _TIER_FAIR
    return _TIER_LOW


class _ScoreBar(Flowable):
    """The match percent restated as a length, under the number itself.

    A rounded track filled to the percent — the print counterpart of the app's
    swept ring. A number alone gives the reader nothing to compare against without
    reading every other number on the page; a bar is comparable at a glance, which
    is the whole job of a ranked list's right-hand margin.
    """

    def __init__(self, percent: int, width: float, height: float = 3.0):
        super().__init__()
        self.percent = max(0, min(100, percent))
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):  # noqa: N803 — reportlab's signature
        return (self.width, self.height)

    def draw(self) -> None:
        canvas = self.canv
        radius = self.height / 2
        canvas.saveState()
        canvas.setFillColor(DIVIDER)
        canvas.roundRect(0, 0, self.width, self.height, radius, fill=1, stroke=0)
        if self.percent:
            # Never narrower than the cap radius, or a low percent draws as a
            # malformed sliver rather than a short bar.
            filled = max(self.height, self.width * self.percent / 100)
            canvas.setFillColor(_tier_color(self.percent))
            canvas.roundRect(0, 0, filled, self.height, radius, fill=1, stroke=0)
        canvas.restoreState()


def _insight_flowable(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    """The rationale's first sentence, set against a left rule.

    The rule is a real ``LINEBEFORE`` rather than a drawn glyph, so it grows with
    the sentence when it wraps to two lines. This is the entry's claim; everything
    under it qualifies the claim.
    """
    quote = Table(
        [[Paragraph(text, styles["ItemInsight"])]], colWidths=[_BODY_WIDTH]
    )
    quote.setStyle(
        TableStyle(
            [
                ("LINEBEFORE", (0, 0), (0, 0), 1.4, SECONDARY),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return quote


#: The collector's deadline-kind vocabulary, as the words a reader uses. Mirrors
#: ``DEADLINE_KIND_LABEL`` in the app's ``primitives/report-entry.tsx``.
_DEADLINE_KIND_LABELS = {
    "abstract": "Abstract",
    "manuscript": "Full paper",
    "submission": "Submission",
    "application": "Application",
    "camera_ready": "Camera ready",
    "notification": "Notification",
    "registration": "Registration",
    "event": "Event",
    "rebuttal": "Rebuttal",
    "review": "Review",
    "withdrawal": "Withdrawal",
}

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _format_date(iso: str) -> str:
    """``2026-09-15`` -> ``Sep 15, 2026``; anything else back verbatim.

    Deliberately string surgery rather than ``datetime`` parsing: the value is a
    calendar date the source wrote down, and putting it through a datetime is how a
    deadline ends up rendered a day early in some timezone. Nothing here needs to
    know what instant that day begins at.
    """
    parts = (iso or "")[:10].split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return iso or ""
    year, month, day = (int(part) for part in parts)
    if not 1 <= month <= 12:
        return iso
    return f"{_MONTHS[month - 1]} {day}, {year}"


def _meta_strip(
    bits: list[str], styles: dict[str, ParagraphStyle], *, width: float
) -> Table:
    """The entry's reference row: its dates, its source, its theme.

    One quiet ruled line under the entry's content, rather than a red date wedged
    between the title and the rationale. A deadline is reference material — the
    reader looks it up once they have decided the entry matters — and it was
    reading as an alarm attached to every conference in the report.
    """
    strip = Table(
        [[Paragraph("  ·  ".join(bits), styles["ItemMetaStrip"])]], colWidths=[width]
    )
    strip.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, -1), 0.4, DIVIDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return strip


def _deadline_bits(deadline_date: str, deadlines: list[dict] | None) -> list[str]:
    """The strip's date bits: the nearest round, named, plus a count of the rest.

    Only the nearest round is spelled out. A conference can carry six of them, and
    six dated lines under a two-sentence rationale is a table nobody asked for — the
    feed card is where the full round list and its per-round alert controls live.
    What the report owes the reader is *when the next thing is due* and *how many
    more there are*, which is exactly this.

    Rounds that have already passed are dropped first. ``deadlines`` is the item's
    whole history (``briefing._deadline_rounds``, chronological), while
    ``deadline_date`` is the one round still ahead — so taking the array's first
    entry would print a date that went by months ago as though it were due.
    """
    rounds = [entry for entry in (deadlines or []) if entry.get("date")]
    if deadline_date:
        ahead = [entry for entry in rounds if entry["date"] >= deadline_date]
        # Only trust the filter when it kept something; a round array that
        # disagrees with the snapshot date is not a reason to print no date.
        rounds = ahead or []
    if rounds:
        nearest = rounds[0]
        kind = _DEADLINE_KIND_LABELS.get(
            (nearest.get("kind") or "").strip(), ""
        ) or (nearest.get("label") or "").strip()
        bits = [f"<b>Due {escape(_format_date(nearest['date']))}</b>"]
        if kind:
            bits.append(escape(kind))
        if len(rounds) > 1:
            extra = len(rounds) - 1
            bits.append(f"+{extra} more round{'' if extra == 1 else 's'}")
        return bits
    if deadline_date:
        return [f"<b>Due {escape(_format_date(deadline_date))}</b>"]
    return []


def _flag(
    text: str,
    styles: dict[str, ParagraphStyle],
    *,
    bg,
    fg,
) -> Table:
    """One rounded flag in the rail — ``NEW``, or a venue's CORE/CCF rank.

    Rounded, not square: a square filled rectangle behind a word reads as a
    highlighter stripe. Sized to the rail rather than to the word so the flags stack
    into a column with one right edge instead of a ragged one.
    """
    style = ParagraphStyle("FlagInner", parent=styles["ChipFlag"], textColor=fg)
    chip = Table([[Paragraph(text, style)]], colWidths=[_RAIL_WIDTH])
    chip.setStyle(
        TableStyle(
            [
                ("ROUNDEDCORNERS", [_RADIUS, _RADIUS, _RADIUS, _RADIUS]),
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return chip


def _match_rail(
    match_percent: int | None,
    is_new: bool,
    styles: dict[str, ParagraphStyle],
    rank_badges: list[dict] | None = None,
) -> list:
    """The entry's right-hand rail: the match score, then its flags.

    The score is the number set large over a tier-coloured bar with a caption
    naming it — the same three zones the app's report entry uses, in print's own
    materials. It comes first because it is what a reader ranks entries by.

    Flags follow. ``NEW`` carries the report's gold, which ``docs/styles.md``
    reserves for exactly this kind of signal; a CCF / CORE / THCPL rank stays on the
    neutral surface pairing, because a rank is an informational label and never a
    relevance signal (plan D2) — giving it gold would put a second alert beside the
    one that means something. Only :func:`_item_flowables` has structured rank data
    to pass; the written report's entries are parsed back out of markdown and carry
    none.
    """
    rail: list = []
    if isinstance(match_percent, int):
        rail.append(Paragraph(str(match_percent), styles["Score"]))
        rail.append(Spacer(1, 2))
        rail.append(_ScoreBar(match_percent, _RAIL_WIDTH))
        rail.append(Spacer(1, 2))
        rail.append(Paragraph("MATCH SCORE", styles["ScoreCaption"]))
    if is_new:
        if rail:
            rail.append(Spacer(1, 6))
        rail.append(
            _flag("NEW", styles, bg=HexColor(_NEW_BG_HEX), fg=HexColor(_NEW_HEX))
        )
    for badge in rank_badges or []:
        rank = (badge.get("rank") or "").strip()
        if not rank:
            continue
        system = (badge.get("system") or "").upper()
        if rail:
            rail.append(Spacer(1, 3))
        rail.append(
            _flag(
                f"{system} {rank}".strip(),
                styles,
                bg=HexColor(_RANK_BG_HEX),
                fg=HexColor(_RANK_HEX),
            )
        )
    return rail


def _entry_row(
    rank: int | str,
    body: list,
    match_percent: int | None,
    is_new: bool,
    styles: dict[str, ParagraphStyle],
    rank_badges: list[dict] | None = None,
) -> list:
    """One ranked entry: its number, its content, and its meta rail.

    The report's single entry shape, used by the written report and by every Top-N
    listing, and the print half of the shape the app draws in
    ``primitives/report-entry.tsx``. Laid out as a three-column row so the numbers
    line up down the page and the rail lines up down the right edge — which is what
    makes a ranked list read as one rather than as twenty-five paragraphs.

    The content column carries the entry's four zones in order: title, the insight,
    the note, and the reference strip. The strip is part of ``body`` rather than a
    fourth column, so it spans exactly the content column and no further.

    Returned as a plain list rather than a ``KeepTogether``: a single-row table does
    not split, so the entry is already atomic, and nesting it in a ``KeepTogether``
    that a caller then nests again pushed every section onto a page of its own.
    """
    # An empty cell is "" rather than an empty list — reportlab measures a list cell
    # by wrapping its flowables, and there are none to wrap.
    rail = _match_rail(match_percent, is_new, styles, rank_badges) or ""
    row = Table(
        [[Paragraph(f"{rank}.", styles["Rank"]), body, rail]],
        colWidths=[_RANK_WIDTH, _BODY_WIDTH + _CELL_PAD, _RAIL_WIDTH],
    )
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), _CELL_PAD),
                ("LEFTPADDING", (2, 0), (2, 0), 0),
                ("RIGHTPADDING", (2, 0), (2, 0), 0),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, DIVIDER),
            ]
        )
    )
    return [row, Spacer(1, 3)]


def _split_reason(text: str) -> tuple[str, str]:
    """Split a rationale into its insight (first sentence) and its note (the rest).

    The rationale is one to three model-written sentences and they are not equal:
    the first says why the item is here, and the rest qualify it. Setting all three
    at one weight is what made the old entry a paragraph a reader had to parse
    rather than a claim they could accept or skip.

    The 25-character floor is what keeps "et al." and "Fig. 2" from being read as
    the end of the sentence they sit inside. A single-sentence rationale returns an
    empty note, and the caller renders no second block rather than an empty one.
    """
    trimmed = (text or "").strip()
    if not trimmed:
        return "", ""
    for found in re.finditer(r"[.!?](?=\s+[\"'(“]?[A-Z0-9])", trimmed):
        cut = found.end()
        if cut < 25:
            continue
        return trimmed[:cut].strip(), trimmed[cut:].strip()
    return trimmed, ""


def _content_flowables(
    title_html: str,
    reason: str,
    strip_bits: list[str],
    styles: dict[str, ParagraphStyle],
) -> list:
    """An entry's content column: title, insight, note, reference strip.

    The one place the four zones are assembled, so the written report's entries and
    the Top-N listings' entries cannot drift into two different documents.
    """
    body: list = [Paragraph(title_html, styles["ItemTitle"])]
    insight, note = _split_reason(reason)
    if insight:
        body.append(Spacer(1, 3))
        body.append(_insight_flowable(_inline(insight), styles))
    if note:
        body.append(Spacer(1, 3))
        body.append(Paragraph(_inline(note), styles["ItemReason"]))
    if strip_bits:
        body.append(_meta_strip(strip_bits, styles, width=_BODY_WIDTH))
    return body


def _item_flowables(
    item: ReportItem, rank: int, styles: dict[str, ParagraphStyle]
) -> list:
    """One found item from a Top-N listing, as the report's standard entry row."""
    title = _inline(item.title)
    if item.url:
        title = f'<a href="{escape(item.url)}" color="{_TITLE_HEX}">{title}</a>'

    # Everything that identifies rather than argues — when it is due, where it came
    # from, which of the reader's themes it landed in — goes to the strip. Above it
    # these were three competing lines between the title and the reason for it.
    strip_bits = _deadline_bits(item.deadline_date, item.deadlines)
    if item.source:
        strip_bits.append(escape(item.source))
    if item.cluster_label:
        strip_bits.append(escape(item.cluster_label))

    return _entry_row(
        rank,
        _content_flowables(
            title, item.reason or item.headline, strip_bits, styles
        ),
        item.match_percent,
        item.is_new,
        styles,
        item.rank_badges,
    )


def _written_item_flowables(
    rank: str, lines: list[str], styles: dict[str, ParagraphStyle]
) -> list:
    """One numbered item from the *written* report, as the same entry row.

    The signals are pulled out of the title line and given to the rail and the
    strip, so a Mylo Report entry and a Top-25 entry are the same object on the
    page. They were two different shapes for no reason other than one arriving as
    markdown.
    """
    title, is_new, match_percent, deadline = _split_item_line(lines[0])
    return _entry_row(
        rank,
        _content_flowables(
            _inline(title),
            " ".join(lines[1:]).strip(),
            _deadline_bits(deadline, None),
            styles,
        ),
        match_percent,
        is_new,
        styles,
    )


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
