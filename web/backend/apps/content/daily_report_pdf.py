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
4. **The meta rail** — the match percent as a filled ring (:class:`_MatchRing`,
   the print counterpart of the app's own), its tier in words beneath, then
   ``NEW`` and any venue rank as pills sized to their own text.

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
from reportlab.pdfbase.pdfmetrics import stringWidth
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

from apps.content import report_grammar
from apps.content.briefing_sections import SECTION_NOUN
from apps.content.daily_report import (
    CATEGORY_LABELS,
    SECTION_NOUNS,
    ReportData,
    ReportItem,
    ReportPart,
)
from apps.content.theme_report import ThemeSection
from apps.content.verdicts import VERDICT_LABELS

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
#: Muted text inside an inline run (a standing row's source/deadline tail).
_MUTED_HEX = "#7F8775"

_SERIF = "Times-Roman"
_SERIF_BOLD = "Times-Bold"
_SANS = "Helvetica"
_SANS_BOLD = "Helvetica-Bold"

_MARGIN = 0.9 * inch
#: The usable text width — the page less both margins. Every table here is laid out
#: against it, so a column change never has to re-derive the page geometry.
_CONTENT_WIDTH = LETTER[0] - 2 * _MARGIN

#: The right-hand meta rail on an entry: the match ring, then the flags. Sized so
#: the ring (38pt) and the widest rank pill a source has produced (~40pt) both sit
#: inside it with a point or two to spare. Everything in the rail is centred on the
#: rail's own axis rather than flush to the margin — a circle right-aligned against
#: pills of differing widths reads as misaligned, because the eye takes the circle's
#: centre as the anchor and the pills' centres then wander left of it.
_RAIL_WIDTH = 0.583 * inch
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
    # A labelled beat under an alert — "Where you still differ: …". Slightly
    # indented so the run of them reads as one block belonging to the title
    # above, rather than as four independent sentences.
    styles["ItemBeat"] = ParagraphStyle(
        "ItemBeat", fontName=_SANS, fontSize=9.5, leading=13.5,
        textColor=TEXT_SECONDARY, leftIndent=8, spaceAfter=1,
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
    styles["Rank"] = ParagraphStyle(
        "Rank", fontName=_SERIF_BOLD, fontSize=12, leading=15, textColor=SECONDARY,
        alignment=TA_RIGHT,
    )
    styles["Muted"] = ParagraphStyle(
        "Muted", fontName=_SANS, fontSize=9.5, leading=14, textColor=TEXT_MUTED,
        spaceAfter=6,
    )
    #: One compact reference row in a theme's standing block. Lighter than an
    #: entry's title: these are things the reader has already been shown, and the
    #: page should make that visible before they read a word of it.
    styles["StandingRow"] = ParagraphStyle(
        "StandingRow", fontName=_SANS, fontSize=9, leading=13,
        textColor=TEXT_SECONDARY, spaceAfter=0,
    )
    #: Mylo's read on one theme — prose set next to the items it describes.
    styles["ThemeRead"] = ParagraphStyle(
        "ThemeRead", fontName=_SERIF, fontSize=10.5, leading=15.5,
        textColor=TEXT, spaceAfter=8,
    )
    #: The lead paragraph, set a shade larger — it is the document's opening claim.
    styles["Lead"] = ParagraphStyle(
        "Lead", fontName=_SERIF, fontSize=11.5, leading=17, textColor=TEXT,
        spaceAfter=10,
    )
    return styles


# --- Inline markdown → reportlab mini-HTML --------------------------------- #
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
#: The report's item grammar (see :mod:`apps.content.briefing_sections`): a bolded
#: ``**NEW**`` marker, a verdict word, and ``deadline 2026-09-01``. Each is a fact a
#: reader scans for, so each is lifted out of the run of text and given a colour.
_NEW_MARKER_RE = re.compile(r"\*\*NEW\*\*")
_VERDICT_RE = re.compile(r"\b(Read|Skim|File)\b")
_DEADLINE_RE = re.compile(r"\bdeadline\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
#: A numbered item line — ``1. **[Title](url)** — **NEW** · Read``.
_NUMBERED_RE = re.compile(r"^(\d{1,3})[.)]\s+(.*)$")
#: The citation into the references block (see :mod:`apps.content.report_grammar`).
#: Set small and muted: it has to be findable without interrupting the sentence
#: it sits in, which is the whole difference between a citation and a footnote.
_CITATION_RE = report_grammar.CITATION


def _inline(text: str, *, verdicts: bool = False) -> str:
    """Escape XML, then re-apply the report's markdown as reportlab tags.

    Deliberately draws **no filled background** anywhere. A reportlab inline
    ``backcolor`` is a square-cornered stripe behind the glyphs — a highlighter mark,
    not a badge — so the two signals it used to paint that way (``NEW``, the
    verdict) are lifted out of the text entirely and rendered as rounded chips
    beside the entry. What is left here is colour and weight, which is all an
    inline run can carry without looking marked-up.

    Verdict colouring is **off by default** (plan step 0.1). ``Read``, ``Skim`` and
    ``File`` are ordinary English words: a lead paragraph opening "Read the
    corruption study first" had its first word painted as a verdict chip colour,
    and so did every sentence mentioning a file. The verdict a ranked item carries
    is parsed out of its title line by :func:`_split_item_line` and drawn as a real
    chip, so nothing here needs to guess at one. The flag stays so a caller that
    genuinely holds a signal segment can opt in.
    """
    # The state markers are grammar for the verifier, not prose for the reader,
    # so they are gone before anything is escaped or styled.
    out = escape(report_grammar.strip_markers(text or ""))
    out = _CITATION_RE.sub(
        lambda m: f'<font size="7" color="{_MUTED_HEX}">[P{m.group(1)}]</font>', out
    )
    out = _LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" color="{_LINK_HEX}">{m.group(1)}</a>', out
    )
    out = _NEW_MARKER_RE.sub(f'<font color="{_NEW_HEX}"><b>NEW</b></font>', out)
    if verdicts:
        out = _VERDICT_RE.sub(
            lambda m: f'<font color="{_MATCH_HEX}"><b>{m.group(1)}</b></font>', out
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
#: The verdict word on a written item's title line, in the markdown the report
#: body uses. It replaced ``88% match``: the percent implied a measurement nobody
#: made, so the qualitative judgement is what the line carries now.
_ITEM_VERDICT_RE = re.compile(r"\b(Read|Skim|File)\b")
_ITEM_DEADLINE_RE = re.compile(
    r"\bdeadline\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE
)
#: Whatever separators the removed signals leave stranded at the end of the line.
_TRAILING_SEPARATORS_RE = re.compile(r"[\s··—–-]+$")

#: The bolded title that opens a ranked item — ``**[Title](url)**`` or ``**Title**``.
#: Non-greedy, because the signals that follow carry their own ``**NEW**`` and a
#: greedy match would swallow it into the title.
_ITEM_TITLE_RE = re.compile(r"^\s*(\*\*.+?\*\*)(.*)$", re.DOTALL)
#: The separator :func:`apps.content.briefing_sections._numbered_item` puts between
#: the title and the signals. Used only when the line carries no bolded title.
_ITEM_SEPARATOR_RE = re.compile(r"^(.*?)\s+—\s+(.*)$", re.DOTALL)


def _signal_segment(text: str) -> tuple[str, str]:
    """Split a ranked item's title line into ``(title, signal segment)``.

    The report's item grammar is ``**[Title](url)** — **NEW** · Read · deadline …``
    (:func:`apps.content.briefing_sections._numbered_item`), so every signal lives
    after the title. Searching the whole line for them is what made a paper called
    *File-Level Provenance* render as a ``File`` verdict, and a title containing the
    word *Read* render as ``Read`` — the signal words are ordinary English, and a
    title is exactly where ordinary English appears.

    Anchored on the bolded title first, because that is what the emitter always
    writes and it survives a title containing its own em dash. A model-written line
    with no bolded title falls back to the ``—`` separator, and a line with neither
    is treated as all title and no signals, which is the safe direction: a missing
    chip is a smaller error than a wrong one.
    """
    matched = _ITEM_TITLE_RE.match(text)
    if matched:
        return matched.group(1), matched.group(2)
    matched = _ITEM_SEPARATOR_RE.match(text)
    if matched:
        return matched.group(1), matched.group(2)
    return text, ""


def _split_item_line(text: str) -> tuple[str, bool, str | None, str]:
    """Split a written item's title line into ``(title, is_new, verdict, deadline)``.

    Order-independent **within the signal segment**, because the line is
    model-written as often as it is generated: each signal is matched wherever it
    sits after the title, removed, and the separators it leaves behind are cleaned
    off the tail.
    """
    title, rest = _signal_segment(text)

    is_new = bool(_ITEM_NEW_RE.search(rest))
    rest = _ITEM_NEW_RE.sub("", rest)

    found_verdict = _ITEM_VERDICT_RE.search(rest)
    verdict = found_verdict.group(1).casefold() if found_verdict else None
    rest = _ITEM_VERDICT_RE.sub("", rest)

    found = _ITEM_DEADLINE_RE.search(rest)
    deadline = found.group(1) if found else ""
    rest = _ITEM_DEADLINE_RE.sub("", rest)

    # Collapse the runs of " · " / " — " the removals opened up mid-line, then trim.
    rest = re.sub(r"\s*[·]\s*(?=[·—–-]|\s*$)", " ", rest)
    # Whatever the signal segment still holds is prose the model wrote alongside the
    # signals ("also in Agentic KG"), so it stays with the title rather than being
    # dropped — the old whole-line parse kept it too.
    remainder = _TRAILING_SEPARATORS_RE.sub("", rest).strip()
    remainder = remainder.lstrip("·—–- ").strip()
    line = f"{title} — {remainder}" if remainder else title
    return _TRAILING_SEPARATORS_RE.sub("", line).strip(), is_new, verdict, deadline


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
            # A labelled beat belongs to the numbered item above it. Flushing
            # here — which is what used to happen for every bullet — split an
            # alert's four beats away from the item they are about and left the
            # title stranded above them at a page break.
            if item is not None and report_grammar.LABELLED_BEAT.match(stripped):
                item[1].append(stripped)
                continue
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
#: Verdict chip colours. Gold is deliberately absent: ``docs/styles.md`` reserves
#: it for opportunity and deadline signals, so a grant deadline never competes
#: visually with a relevance judgement.
_VERDICT_STYLES = {
    "read": (HexColor("#FFFDF8"), PRIMARY, None),        # filled primary, white text
    "skim": (HexColor("#2E3627"), SECONDARY, None),      # sage secondary, dark text
    "file": (HexColor("#5F6853"), SURFACE_ALT, BORDER),  # neutral surface
}


def _shorten(text: str, limit: int) -> str:
    """Trim a theme name to fit a rail chip, on a word boundary and with an ellipsis.

    A hard slice produces ``AI FOR OCEANOG``, which reads as a rendering bug rather
    than an abbreviation. Cutting at a space and marking the cut says the same
    thing and looks deliberate.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] or text[: limit - 1]
    return f"{cut}…"


def _verdict_chip(verdict: str | None, width: float) -> _Pill | None:
    """Mylo's four-point verdict as a chip, or ``None`` when there is nothing to say.

    A ``skip`` never appears as a chip: the item keeps its slate place and shows in
    the reference block, but it earns no write-up and no badge. Chipping it would
    spend the reader's attention on the one judgement that says "do not spend your
    attention here".
    """
    style = _VERDICT_STYLES.get((verdict or "").casefold())
    if style is None:
        return None
    fg, bg, border = style
    return _Pill(
        VERDICT_LABELS[verdict].upper(), width, fg=fg, bg=bg, border=border
    )


class _Pill(Flowable):
    """A flag sized to its own word, centred on the rail's axis.

    A ``Table`` with a fixed column width stretched every flag to the full rail,
    which stops it reading as a tag and starts it reading as a table row. Here the
    box is measured from the text, and the flowable reserves the rail's width so the
    pill can centre itself inside it — on the same axis as the ring above — without
    depending on reportlab's cell alignment for custom flowables.
    """

    _PAD_X = 6.0
    _PAD_Y = 3.0

    def __init__(
        self,
        text: str,
        width: float,
        *,
        font_size: float = 6.5,
        fg,
        bg=None,
        border=None,
    ):
        super().__init__()
        self.text = text
        self.width = width
        self.font_size = font_size
        self.fg = fg
        self.bg = bg
        self.border = border
        self.pill_width = (
            stringWidth(text, _SANS_BOLD, font_size) + 2 * self._PAD_X
        )
        self.height = font_size + 2 * self._PAD_Y

    def wrap(self, availWidth, availHeight):  # noqa: N803 — reportlab's signature
        return (self.width, self.height)

    def draw(self) -> None:
        canvas = self.canv
        left = (self.width - self.pill_width) / 2
        canvas.saveState()
        if self.bg is not None:
            canvas.setFillColor(self.bg)
        if self.border is not None:
            canvas.setStrokeColor(self.border)
            canvas.setLineWidth(0.6)
        canvas.roundRect(
            left,
            0,
            self.pill_width,
            self.height,
            self.height / 2,
            fill=1 if self.bg is not None else 0,
            stroke=1 if self.border is not None else 0,
        )
        canvas.setFillColor(self.fg)
        canvas.setFont(_SANS_BOLD, self.font_size)
        canvas.drawCentredString(
            left + self.pill_width / 2, self._PAD_Y + 1.2, self.text
        )
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


def _match_rail(
    verdict: str | None,
    is_new: bool,
    styles: dict[str, ParagraphStyle],
    rank_badges: list[dict] | None = None,
    bridge_labels: list[str] | None = None,
) -> list:
    """The entry's right-hand rail: Mylo's verdict, then its flags.

    The percent ring used to sit here and carried three jobs at once — the number,
    the tier colour, and Mylo's portrait as attribution. The number is gone (it
    implied a measurement nobody made), the tier colour is now the verdict's own,
    and the attribution survives in the chip being Mylo's word rather than a
    computed one.

    ``NEW`` is filled gold, which ``docs/styles.md`` reserves for exactly this kind
    of signal. ``ALSO IN`` names a theme this item also reaches — derived from the
    slates at render time, never scored, so a bridge costs nothing and stays
    symmetric. A CCF / CORE / THCPL rank is drawn as an outline: a rank is
    informational and never a relevance signal, so a second filled badge beside
    ``NEW`` would compete with the one that means something.
    """
    rail: list = []
    chip = _verdict_chip(verdict, _RAIL_WIDTH)
    if chip is not None:
        rail.append(chip)
    if is_new:
        if rail:
            rail.append(Spacer(1, 4))
        rail.append(
            _Pill(
                "NEW",
                _RAIL_WIDTH,
                fg=HexColor(_NEW_HEX),
                bg=HexColor(_NEW_BG_HEX),
            )
        )
    for label in (bridge_labels or [])[:1]:
        if rail:
            rail.append(Spacer(1, 3))
        rail.append(
            _Pill(
                f"ALSO IN {_shorten(label, 14)}".upper(),
                _RAIL_WIDTH,
                font_size=5.4,
                fg=HexColor(_RANK_HEX),
                border=BORDER,
            )
        )
    for badge in rank_badges or []:
        rank = (badge.get("rank") or "").strip()
        if not rank:
            continue
        system = (badge.get("system") or "").upper()
        if rail:
            rail.append(Spacer(1, 3))
        rail.append(
            _Pill(
                f"{system} {rank}".strip(),
                _RAIL_WIDTH,
                fg=HexColor(_RANK_HEX),
                border=BORDER,
            )
        )
    return rail


def _entry_row(
    position: int | str,
    body: list,
    verdict: str | None,
    is_new: bool,
    styles: dict[str, ParagraphStyle],
    rank_badges: list[dict] | None = None,
    bridge_labels: list[str] | None = None,
) -> list:
    """One entry: its position within its theme, its content, and its meta rail.

    The report's single entry shape, and the print half of what the app draws in
    ``primitives/report-entry.tsx``. Laid out as a three-column row so the numbers
    line up down the page and the rail lines up down the right edge — which is
    what makes a ranked list read as one rather than as twenty-five paragraphs.

    The gutter number is the item's place in **its own theme**, not a global
    position. A global one would be comparing scores that are not comparable,
    which is the failure the per-cluster redesign exists to remove.

    Returned as a plain list rather than a ``KeepTogether``: a single-row table
    does not split, so the entry is already atomic, and nesting it in a
    ``KeepTogether`` that a caller then nests again pushed every section onto a
    page of its own.
    """
    # An empty cell is "" rather than an empty list — reportlab measures a list cell
    # by wrapping its flowables, and there are none to wrap.
    rail = (
        _match_rail(verdict, is_new, styles, rank_badges, bridge_labels) or ""
    )
    row = Table(
        [[Paragraph(f"{position}.", styles["Rank"]), body, rail]],
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
    lead: str,
    strip_bits: list[str],
    styles: dict[str, ParagraphStyle],
) -> list:
    """An entry's content column: title, the lead sentence, reference strip.

    Three zones, not four. The PDF is the **record** — what arrived, in which
    themes, what is closing soon, what is worth opening — and the website is where
    the reasoning lives: the remaining two beats, the caveat, the matched
    interests, the evidence. That split is what keeps a 150-entrant day longer by
    150 compact rows rather than by ninety pages of prose.

    The single lead sentence is the one thing not to cut. Without it a reader gets
    sixty titles and has to open the site to make any judgement at all, which
    defeats the point of a morning brief.
    """
    body: list = [Paragraph(title_html, styles["ItemTitle"])]
    if lead:
        body.append(Spacer(1, 3))
        body.append(_insight_flowable(_inline(lead), styles))
    if strip_bits:
        body.append(_meta_strip(strip_bits, styles, width=_BODY_WIDTH))
    return body


def _item_flowables(
    item: ReportItem, position: int, styles: dict[str, ParagraphStyle]
) -> list:
    """One found item as the report's standard entry row."""
    title = _inline(item.title)
    if item.edition and str(item.edition) not in item.title:
        # The edition carries the returning-reader signal on a reopened annual
        # call — an entry reading *NeurIPS 2027* tells a returning reader
        # everything a "reopened" chip would, so there is no second badge.
        title = f"{title} {escape(str(item.edition))}"
    if item.url:
        title = f'<a href="{escape(item.url)}" color="{_TITLE_HEX}">{title}</a>'

    # Everything that identifies rather than argues — when it is due, where it came
    # from — goes to the strip. Above it these were competing lines between the
    # title and the reason for it. The theme is no longer among them: the section
    # heading already names it.
    strip_bits = _deadline_bits(item.deadline_date, item.deadlines)
    if item.source:
        strip_bits.append(escape(item.source))
    if item.license:
        strip_bits.append(escape(item.license))

    return _entry_row(
        position,
        _content_flowables(
            title, item.lead or item.reason or item.headline, strip_bits, styles
        ),
        item.verdict,
        item.is_new,
        styles,
        item.rank_badges,
        item.bridge_labels,
    )


def _standing_row(
    item: ReportItem, styles: dict[str, ParagraphStyle]
) -> list:
    """One compact reference row: position, linked title, source, deadline.

    No reason, no verdict, no prose. This block serves the reader who skipped
    three days; letting settled items carry commentary is how a document whose job
    is to report change ends up dominated by the things that did not.
    """
    title = _inline(item.title)
    if item.url:
        title = f'<a href="{escape(item.url)}" color="{_TITLE_HEX}">{title}</a>'
    due = (
        f"due {_format_date(item.deadline_date)}" if item.deadline_date else ""
    )
    # The block spans every category the theme holds, so each row names its own —
    # without it a papers row numbered 3 above a grants row numbered 2 reads as a
    # broken list rather than as two lists sharing a heading.
    noun = SECTION_NOUN.get(item.category, item.category)
    bits = [b for b in (noun.title(), item.source, due) if b]
    tail = (
        f'  <font color="{_MUTED_HEX}">· {escape("  ·  ".join(bits))}</font>'
        if bits
        else ""
    )
    row = Table(
        [[
            Paragraph(f"{item.position or '–'}.", styles["Rank"]),
            Paragraph(title + tail, styles["StandingRow"]),
        ]],
        colWidths=[_RANK_WIDTH, _CONTENT_WIDTH - _RANK_WIDTH],
    )
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return [row]


def _written_item_flowables(
    rank: str, lines: list[str], styles: dict[str, ParagraphStyle]
) -> list:
    """One numbered item from a *written* markdown block, as the same entry row.

    Used by the project sections, which are rendered from markdown rather than
    from structured items. The signals are pulled out of the title line and given
    to the rail and the strip, so a project entry and a theme entry are the same
    object on the page.
    """
    title, is_new, verdict, deadline = _split_item_line(lines[0])
    # Labelled beats are the alert blocks' body — "What overlaps", "Where you
    # still differ", "Do this week" — and each is a line of its own, because the
    # label is what a reader scans for when deciding whether to act today.
    beats: list[tuple[str, str]] = []
    prose: list[str] = []
    for line in lines[1:]:
        matched = report_grammar.LABELLED_BEAT.match(line)
        if matched:
            beats.append((matched.group(1), matched.group(2)))
        else:
            prose.append(line)

    body = _content_flowables(
        _inline(title),
        " ".join(prose).strip(),
        _deadline_bits(deadline, None),
        styles,
    )
    for label, text in beats:
        body.append(Spacer(1, 2))
        body.append(
            Paragraph(
                f"<b>{escape(label)}:</b> {_inline(text)}", styles["ItemBeat"]
            )
        )
    return _entry_row(rank, body, verdict, is_new, styles)


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
    theme_rows = 0
    for part in data.parts:
        if part.kind == "personal" and part.themes:
            # The table inverts: the reader's own part becomes one row per
            # **theme**, so the table is a direct index of the sections below it
            # and a reader sees in three seconds which strand moved today.
            for section in part.themes:
                counts = section.counts(data.categories)
                rows.append(
                    [
                        Paragraph(escape(section.label), label_style),
                        *[_cell(counts.get(c, 0)) for c in data.categories],
                    ]
                )
                theme_rows += 1
            continue
        rows.append(
            [
                Paragraph(escape(part.label), label_style),
                *[_cell(part.counts.get(c, 0)) for c in data.categories],
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
    # The reader's own rows are not just more projects; setting them apart keeps a
    # long project list from reading as though the themes were among them.
    if theme_rows:
        style.append(("FONTNAME", (0, 1), (-1, theme_rows), _SANS_BOLD))
    elif data.parts and data.parts[0].kind == "personal":
        style.append(("FONTNAME", (0, 1), (-1, 1), _SANS_BOLD))
    table.setStyle(TableStyle(style))
    return table


def _cell(count: int) -> str:
    """A count, or an em dash for a theme that holds a slate but gained nothing.

    A dash rather than a zero: zero reads as "nothing here", and the theme still
    holds a list the reader can go and look at. A theme with no matches at all
    never reaches this table — it is absent from the document entirely.
    """
    return str(count) if count else "—"


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
            "One row per research theme, and one per project. A dash means the "
            "theme still holds a list but nothing entered it today; a theme with "
            "no matches at all is not listed.",
            styles["CoverFoot"],
        )
    )
    # A lab document lists only projects opted into lab reports, so it says how
    # many it is leaving out — a count, never a name. Without the line a reader who
    # knows the lab runs six projects reads a one-project table as a quiet day.
    if data.private_projects_hidden:
        noun = "project" if data.private_projects_hidden == 1 else "projects"
        cover.append(Spacer(1, 0.06 * inch))
        cover.append(
            Paragraph(
                f"{data.private_projects_hidden} private {noun} not shown.",
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

    # 3. Mylo's lead — one paragraph over the whole profile. It replaces the old
    #    standalone "Your Mylo Report" section, which duplicated the listings
    #    beneath it. A reader with no model reasoning gets the cover table and
    #    goes straight to the themes, which is honest rather than degraded.
    if data.lead:
        _extend_title(story, "Mylo's read on today", styles)
        story.append(Paragraph(_inline(data.lead), styles["Lead"]))
        if data.lead_origin == "fallback":
            story.append(Paragraph(_ORIGIN_NOTE, styles["Muted"]))
        story.append(PageBreak())

    # 3b. What needs attention, above everything else in the body. An alert is a
    #     claim that something must be decided today; putting it under the week's
    #     reading is how it gets read on Thursday. Rendered from the matchers'
    #     own evidence, so every number in it is theirs (plan H2).
    if data.alerts:
        _extend_title(story, "Needs your attention", styles)
        _extend_alerts(story, data.alerts, styles)
        story.append(PageBreak())

    # 4. The body: one section per theme with news, then the quiet line, then one
    #    section per project. A theme with no matches at all appears nowhere.
    personal = data.personal
    wrote_body = bool(data.alerts)
    if personal is not None and personal.live_themes:
        for index, section in enumerate(personal.live_themes):
            if index:
                story.append(Spacer(1, 0.18 * inch))
            _extend_theme(story, section, data.categories, styles)
        wrote_body = True
        quiet = getattr(personal, "quiet", None)
        if quiet:
            named = ", ".join(f"{label} ({count} standing)" for label, count in quiet)
            story.append(Spacer(1, 0.12 * inch))
            story.append(
                Paragraph(
                    f"<b>Quiet today:</b> {escape(named)}. Nothing new entered "
                    "these lists; what they hold is unchanged.",
                    styles["Muted"],
                )
            )
    elif personal is not None and personal.shown:
        # No theme sections: rows written before per-cluster slates existed. One
        # nightly run rewrites them; until then the flat listing is still a real
        # document rather than an empty one.
        story.append(PageBreak()) if wrote_body else None
        _extend_part(story, personal, data.categories, styles)
        wrote_body = True

    # 4b. The open fellowship band. It belongs to no theme by construction, so it
    #     sits after the themes rather than inside one — listed once, and honest
    #     about being eligibility-qualified rather than topically matched.
    if data.open_fellowships:
        story.append(Spacer(1, 0.2 * inch))
        _extend_title(story, "Fellowships open to you", styles)
        story.append(
            Paragraph(
                "Eligible, but not tied to any one strand of your work — so they "
                "are listed once here rather than under every theme.",
                styles["Muted"],
            )
        )
        for item in data.open_fellowships:
            story.extend(_standing_row(item, styles))
        wrote_body = True

    for part in data.projects:
        if not part.total:
            continue
        story.append(PageBreak())
        _extend_part(story, part, data.categories, styles)
        wrote_body = True

    if not wrote_body:
        story.append(
            Paragraph(
                "Nothing entered your lists today. Your feeds and search still "
                "hold everything matched so far.",
                styles["Muted"],
            )
        )

    # 5. The code frame's closing half (plan A.1): what is due soon, what the run
    #    found, and the references every citation points at. All three are
    #    rendered from structured data and never written by the model (plan H6) —
    #    a model renumbering the references would silently re-point every
    #    citation in the document.
    story.extend(_deadline_horizon(data, styles))
    story.extend(_statistics_block(data, styles))

    # 6. Provenance, as one small paragraph rather than decoration.
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(_footer_note(data), styles["CoverFoot"]))

    doc.multiBuild(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buffer.getvalue()


def _extend_alerts(
    story: list, blocks: list, styles: dict[str, ParagraphStyle]
) -> None:
    """The alert blocks, grouped by project and trigger, in the entry-row shape.

    The same object as every other entry on the page — rank, title, chips, body —
    because an alert is not a different kind of thing to read, it is the same kind
    of thing with a reason attached.
    """
    current = ""
    for index, block in enumerate(blocks, start=1):
        heading = f"{block.project_label} · {block.trigger_label}"
        if heading != current:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(escape(heading), styles["H2"]))
            current = heading
        body: list = [
            Paragraph(
                (
                    f'<a href="{escape(block.url)}" color="{_TITLE_HEX}">'
                    f"{_inline(block.title)}</a>"
                )
                if block.url
                else _inline(block.title),
                styles["ItemTitle"],
            )
        ]
        for label, text in block.beats:
            body.append(Spacer(1, 2))
            body.append(
                Paragraph(
                    f"<b>{escape(label)}:</b> {_inline(text)}", styles["ItemBeat"]
                )
            )
        story.extend(_entry_row(str(index), body, None, True, styles))


def _deadline_horizon(
    data: ReportData, styles: dict[str, ParagraphStyle]
) -> list:
    """What is due inside the reader's own buffer, as a table (plan A.1).

    A table rather than prose because it is a list of dates, and because the
    numbers in it must be the matchers' numbers exactly. The window is the
    reader's own deadline buffer, so the heading names it: a reader who thinks 14
    days is the wrong horizon can change it, and this is where they find out it
    is a setting rather than a system constant.
    """
    stats = data.stats
    if not stats.deadlines_in_window:
        return []
    nearest = stats.nearest_deadline or {}
    rows = [["Due", "Days", "What"]]
    rows.append(
        [
            Paragraph(escape(str(nearest.get("due_date") or "")), styles["Body"]),
            Paragraph(escape(str(nearest.get("days", ""))), styles["Body"]),
            Paragraph(escape(str(nearest.get("title") or "")), styles["Body"]),
        ]
    )
    more = stats.deadlines_in_window - 1
    heading = f"Deadlines inside {stats.deadline_window_days} days"
    out: list = [
        Spacer(1, 0.16 * inch),
        Paragraph(heading, styles["H1"]),
        HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=8),
        Table(
            rows,
            colWidths=[1.3 * inch, 0.7 * inch, 4.7 * inch],
            hAlign="LEFT",
            style=[
                ("FONTNAME", (0, 0), (-1, 0), _SANS_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ],
        ),
    ]
    if more > 0:
        noun = "deadline" if more == 1 else "deadlines"
        out.append(
            Paragraph(
                f"And {more} more {noun} inside the window — on the web.",
                styles["Muted"],
            )
        )
    return out


def _statistics_block(data: ReportData, styles: dict[str, ParagraphStyle]) -> list:
    """What the run found, in the words the Discord post uses (plan A.1).

    The same figures, from the same stored ``stats``, so a reader comparing the
    post on their phone with the document on their desk sees one morning and not
    two. Omitted entirely when the run recorded no statistics — a report written
    before they existed says nothing rather than saying zero.
    """
    stats = data.stats
    if not stats.matched and not stats.entered and not stats.has_volume:
        return []

    from apps.content.discord_embeds import volume_line

    subject = "you or your projects" if data.personal is None else (
        "you or your projects" if data.personal.kind == "personal" else "the lab"
    )
    lines = [volume_line(stats, subject=subject, period="overnight")]
    if stats.by_category:
        cells = " · ".join(
            f"{CATEGORY_LABELS.get(category, category.title())} {new} of {total}"
            for category, (new, total) in stats.by_category.items()
        )
        lines.append(f"By category (new of what your feeds hold): {cells}")
    if stats.by_theme:
        themes = " · ".join(f"{label} {count}" for label, count in stats.by_theme)
        lines.append(f"By theme (new): {themes}")
    return [
        Spacer(1, 0.16 * inch),
        Paragraph("What Mylo found", styles["H1"]),
        HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=8),
        *[Paragraph(escape(line), styles["Body"]) for line in lines],
    ]


def _extend_title(story: list, text: str, styles: dict[str, ParagraphStyle]) -> None:
    """A top-level (``H1``) section title, underlined by a hairline rule."""
    story.append(Paragraph(escape(text), styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=8))


#: What the document says when Mylo's writer could not be reached at all. Rendered
#: wherever a fallback stands in for a judgement, so a template is never mistaken
#: for something Mylo actually thought.
_ORIGIN_NOTE = (
    "Mylo's writer was offline for this run, so this is the deterministic "
    "summary. The rankings, positions, and deadlines are unaffected."
)


def _footer_note(data: ReportData) -> str:
    """Provenance: what was scanned and from where. One small paragraph."""
    sources = sorted(
        {
            item.source_name
            for part in data.parts
            for items in part.items.values()
            for item in items
            if item.source_name
        }
    )
    scanned = ", ".join(CATEGORY_LABELS.get(c, c).lower() for c in data.categories)
    line = f"Compiled {escape(data.generated_on)} over your watched {scanned}."
    if sources:
        line += " Sources: " + escape(", ".join(sources)) + "."
    return line


def _extend_theme(
    story: list,
    section: ThemeSection,
    categories: list[str],
    styles: dict[str, ParagraphStyle],
) -> None:
    """One theme: Mylo's read, what entered, then what is standing.

    The order is the argument. A reader opening this document wants to know what
    changed, so the entrants come first and in full; the settled list follows as
    compact reference rows for the reader who skipped three days. Prose sits at the
    top, next to the items it describes, rather than in a separate section that
    repeats them.
    """
    _extend_title(story, section.label, styles)
    if section.read:
        story.append(Paragraph(_inline(section.read), styles["ThemeRead"]))
        if section.read_origin == "fallback":
            story.append(Paragraph(_ORIGIN_NOTE, styles["Muted"]))

    for category in categories:
        entrants = section.entrants.get(category) or []
        if not entrants:
            continue
        noun = SECTION_NOUNS.get(category, CATEGORY_LABELS.get(category, category))
        opening = [Paragraph(f"New {noun.lower()}", styles["H2"])]
        first = _item_flowables(entrants[0], entrants[0].position or 1, styles)
        # The heading travels with its first entry: a heading alone at the foot of
        # a page is precisely the loss of hierarchy this layout exists to prevent.
        story.append(KeepTogether(opening + first))
        for item in entrants[1:]:
            story.extend(_item_flowables(item, item.position or "–", styles))

    standing = sum(
        len(section.standing.get(category) or []) for category in categories
    )
    if not standing:
        # Every one of this theme's slate is an entrant, so there is nothing
        # standing to account for.
        return
    # The standing list itself stays on the web (plan 4.1). Printing it turned a
    # report about what changed into a 25-row-per-theme catalogue that is
    # identical to yesterday's, and a document whose bulk does not change is a
    # document nobody opens twice. The count still prints, because "nothing new
    # in a theme that holds 25" and "nothing at all" are different days.
    noun = "item" if standing == 1 else "items"
    story.append(Spacer(1, 0.06 * inch))
    story.append(
        Paragraph(
            f"{standing} standing {noun} in this list, unchanged — on the web.",
            styles["Muted"],
        )
    )


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
