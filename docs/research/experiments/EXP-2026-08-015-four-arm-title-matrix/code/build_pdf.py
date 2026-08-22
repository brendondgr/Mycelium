"""Typeset the four-arm title matrix (`EXP-2026-08-015`).

    uv run --project eval python .../code/build_pdf.py

Reads `data/lists.json`, writes `tables/four-arm-comparison.pdf`. One page per
category: rows are document titles in full, columns are the four blinded arms,
cells are that arm's rank. Nothing else on the row — no snippet, no source — at
the reader's request, because the previous booklet's completeness was what made
it unreadable.

Rows are ordered by the best rank any arm gave the document, so consensus sits at
the top and disagreement shows as gaps down the page. Arm letters are W-Z and the
key is on the last page only.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

EXP_DIR = Path(__file__).resolve().parent.parent
DATA = EXP_DIR / "data" / "lists.json"
OUT = EXP_DIR / "tables" / "four-arm-comparison.pdf"

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#666666")
RULE = colors.HexColor("#cfcfcf")
BAND = colors.HexColor("#f2f4f6")
ACCENT = colors.HexColor("#0072B2")
TOP3 = colors.HexColor("#d9ecf7")

TYPE_LABEL = {
    "paper": "Papers",
    "grant": "Grants",
    "conference": "Conferences",
    "fellowship": "Fellowships",
}
PRETTY = {
    "fusion_dense_pool": "PRODUCTION AS DEPLOYED — RRF, BM25 restricted to the dense pool",
    "fusion_dense_pool+xenc": (
        "PRODUCTION AS DEPLOYED + cross-encoder rerank of its top 50"
    ),
    "fusion_union_pool": "RRF over a true union pool (dense ∪ corpus-wide BM25)",
    "fusion_union_splade": "RRF over three channels: BM25 ∪ dense ∪ SPLADE",
}


def styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Title"], fontSize=17, leading=20, textColor=INK,
            alignment=TA_LEFT, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=12, leading=15, textColor=INK,
            spaceBefore=10, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=9.5, leading=13.5, textColor=INK,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontSize=8, leading=10.5, textColor=MUTED,
        ),
        "title": ParagraphStyle(
            "title", parent=base["BodyText"], fontSize=8.2, leading=10.2,
            textColor=INK, spaceAfter=0,
        ),
    }


def esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def jaccard(a, b) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa or sb) else 1.0


def build() -> None:
    data = json.loads(DATA.read_text())
    st = styles()
    labels = data["blind_labels"]
    letters = sorted(labels)

    story: list = cover(data, st)
    story.append(PageBreak())
    for i, content_type in enumerate(data["types"]):
        story += matrix_page(data, content_type, letters, labels, st)
        if i < len(data["types"]) - 1:
            story.append(PageBreak())
    story.append(PageBreak())
    story += summary(data, letters, labels, st)
    story.append(PageBreak())
    story += key_page(labels, letters, st)

    OUT.parent.mkdir(exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title="Four-arm retrieval comparison — blinded",
        author="EXP-2026-08-015",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.6 * inch, 0.34 * inch, "EXP-2026-08-015 · arms W–Z · key on the final page")
    canvas.drawRightString(letter[0] - 0.6 * inch, 0.34 * inch, str(doc.page))
    canvas.restoreState()


def cover(data: dict, st: dict) -> list:
    sizes = data["corpus_sizes"]
    return [
        Paragraph("Four arms, one query", st["h1"]),
        Paragraph(f"&ldquo;{esc(data['query'])}&rdquo;", st["h2"]),
        Spacer(1, 4),
        Paragraph(
            "Four retrieval configurations, blinded as <b>W, X, Y and Z</b> — "
            "<b>new letters, deliberately not the A–J of last time</b>, so the "
            "previous verdicts do not carry over. The key is on the last page.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph("How to read a page", st["h2"]),
        Paragraph(
            "One page per category. <b>Each row is one document, title in full and "
            "nothing else. Each column is one arm. The number is where that arm "
            "ranked it — 1 to 10 — and a blank means that arm did not surface it at "
            "all.</b> Read a column downwards to see one arm's top ten in order; "
            "read a row across to see how differently the four treated the same "
            "document. Rows are sorted by the best rank anyone gave, so agreement "
            "sits at the top and disagreement shows as gaps. Top-three placements "
            "are shaded.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph(
            f"Corpus: {sizes.get('paper', 0):,} papers · {sizes.get('grant', 0):,} "
            f"grants · {sizes.get('conference', 0):,} conferences · "
            f"{sizes.get('fellowship', 0):,} fellowships. Match thresholds, "
            "fellowship eligibility and the paper freshness gate are off — these are "
            "rankings, not a screenshot of the feed. No LLM was called.",
            st["small"],
        ),
    ]


def matrix_page(data: dict, content_type: str, letters, labels, st: dict) -> list:
    cell = data["cells"][content_type]
    ranks: dict[str, dict[str, int]] = {}
    titles: dict[str, str] = {}
    for letter_ in letters:
        for position, doc in enumerate(cell[labels[letter_]], start=1):
            titles[doc["id"]] = doc["title"]
            ranks.setdefault(doc["id"], {})[letter_] = position

    order = sorted(
        ranks,
        key=lambda i: (min(ranks[i].values()), -len(ranks[i]), titles[i].casefold()),
    )

    rows = [["Document", *letters]]
    for doc_id in order:
        rows.append([
            Paragraph(esc(titles[doc_id]), st["title"]),
            *[str(ranks[doc_id].get(letter_, "")) for letter_ in letters],
        ])

    table = Table(
        rows,
        colWidths=[5.5 * inch] + [0.45 * inch] * len(letters),
        hAlign="LEFT",
        repeatRows=1,
    )
    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (1, 1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (0, -1), [colors.white, BAND]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ])
    for row_index, doc_id in enumerate(order, start=1):
        for col, letter_ in enumerate(letters, start=1):
            position = ranks[doc_id].get(letter_)
            if position is not None and position <= 3:
                style.add("BACKGROUND", (col, row_index), (col, row_index), TOP3)
    table.setStyle(style)

    return [
        Paragraph(TYPE_LABEL[content_type], st["h1"]),
        Paragraph(
            f"{len(order)} distinct documents across the four top-tens "
            f"(10 would mean the arms agree completely, 40 that they share nothing).",
            st["small"],
        ),
        Spacer(1, 6),
        table,
    ]


def summary(data: dict, letters, labels, st: dict) -> list:
    story = [
        Paragraph("Agreement and cost", st["h1"]),
        Paragraph(
            "Reported without interpretation. Jaccard@10 is the share of the two "
            "arms' top-tens that overlap: 1.00 identical, 0.00 disjoint.",
            st["small"],
        ),
        Spacer(1, 8),
        Paragraph("How much the arms overlap, per category", st["h2"]),
    ]
    pairs = [(a, b) for i, a in enumerate(letters) for b in letters[i + 1 :]]
    rows = [["Category", "distinct docs", *[f"{a}·{b}" for a, b in pairs]]]
    for content_type in data["types"]:
        cell = data["cells"][content_type]
        ids = {ltr: [d["id"] for d in cell[labels[ltr]]] for ltr in letters}
        distinct = len({i for lst in ids.values() for i in lst})
        rows.append([
            TYPE_LABEL[content_type], str(distinct),
            *[f"{jaccard(ids[a], ids[b]):.2f}" for a, b in pairs],
        ])
    table = Table(
        rows,
        colWidths=[1.15 * inch, 0.9 * inch] + [0.72 * inch] * len(pairs),
        hAlign="LEFT",
    )
    table.setStyle(_grid())
    story += [table, Spacer(1, 14), Paragraph("Time to answer this query", st["h2"])]

    by_arm: dict[str, list[float]] = {}
    for row in data["timing"]:
        by_arm.setdefault(row["arm"], []).append(row["seconds"])
    rows = [["Arm", "median seconds per query", "slowest category"]]
    for ltr in letters:
        values = by_arm.get(labels[ltr], [0.0])
        rows.append([ltr, f"{statistics.median(values):.3f} s", f"{max(values):.3f} s"])
    table = Table(
        rows, colWidths=[0.7 * inch, 2.2 * inch, 1.7 * inch], hAlign="LEFT"
    )
    table.setStyle(_grid())
    story += [
        table,
        Spacer(1, 8),
        Paragraph(
            "One of these arms also carries a one-time index cost of about 23 minutes "
            "over the paper corpus, paid once per document and incrementally on new "
            "ingest. Which one is on the next page.",
            st["small"],
        ),
    ]
    return story


def key_page(labels, letters, st: dict) -> list:
    rows = [["Arm", "What it is"]]
    for ltr in letters:
        rows.append([ltr, Paragraph(PRETTY[labels[ltr]], st["title"])])
    table = Table(rows, colWidths=[0.6 * inch, 6.6 * inch], hAlign="LEFT")
    style = _grid()
    style.add("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold")
    style.add("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND])
    table.setStyle(style)
    return [
        Paragraph("Key — read after you have judged", st["h1"]),
        Spacer(1, 8),
        table,
        Spacer(1, 12),
        Paragraph(
            "The three-channel arm is the one carrying the extra index: SPLADE has to "
            "be encoded over every document once (23 minutes for 35,205 papers, then "
            "seconds per daily batch) and kept in step with the corpus, plus a second "
            "model resident in the serving process.",
            st["small"],
        ),
    ]


def _grid() -> TableStyle:
    return TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])


if __name__ == "__main__":
    build()
