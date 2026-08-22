"""Typeset the two-arm head-to-head (`EXP-2026-08-017`).

    uv run --project eval python .../code/build_pdf.py

Table, style and page code are `EXP-2026-08-015`'s, imported rather than copied —
three booklets have now gone to the same reader and a layout difference between
them would read as a result. Only what genuinely differs is defined here: the
cover, a per-cell heading that carries the query as well as the category, the
two-arm summary, and the key.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
PRIOR = EXP_DIR.parent / "EXP-2026-08-015-four-arm-title-matrix" / "code"
sys.path.insert(0, str(PRIOR))

import build_pdf as base
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
)

DATA = EXP_DIR / "data" / "lists.json"
OUT = EXP_DIR / "tables" / "splade-vs-dense.pdf"


def cover(data: dict, st: dict, letters) -> list:
    sizes = data["corpus_sizes"]
    return [
        Paragraph("Two arms, head to head", st["h1"]),
        Paragraph(
            " · ".join(f"&ldquo;{base.esc(q)}&rdquo;" for q in data["queries"]),
            st["h2"],
        ),
        Spacer(1, 4),
        Paragraph(
            f"Just <b>{letters[0]}</b> and <b>{letters[1]}</b> this time — a "
            "<b>fourth</b> set of letters, sharing none with any previous booklet. "
            "The same letter means the same arm on every page, so a single overall "
            "verdict is possible. Key on the last page.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph("What this is testing", st["h2"]),
        Paragraph(
            "Every comparison so far has put a reranked arm against an "
            "<i>un-reranked</i> one, which changes two things at once — how the "
            "candidate pool is built, and whether anything re-sorts it. "
            "<b>Here both arms get the identical reranker, so the only difference "
            "left is which documents are in the pool.</b> One builds its pool "
            "narrowly; the other builds it from three separate retrieval channels. "
            "If you cannot tell them apart, that is a real answer — the wider pool "
            "costs an extra index and about 23 minutes of one-time work, so a tie "
            "settles it.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph("How to read a page", st["h2"]),
        Paragraph(
            "One page per category per query, both areas in one booklet. <b>Each row "
            "is one document, title in full and nothing else. Each column is one arm. "
            "The number is where that arm ranked it — 1 to 10 — and a blank means "
            "that arm did not surface it at all.</b> Rows are sorted by the best rank "
            "either arm gave, so agreement sits at the top. Top-three placements are "
            "shaded.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph(
            f"Corpus: {sizes.get('paper', 0):,} papers · {sizes.get('grant', 0):,} "
            f"grants · {sizes.get('conference', 0):,} conferences · "
            f"{sizes.get('fellowship', 0):,} fellowships. Match thresholds, "
            "fellowship eligibility and the paper freshness gate are off. No LLM was "
            "called. Fellowships were unreadable in both previous booklets — a shrug "
            "there is a legitimate answer.",
            st["small"],
        ),
    ]


def summary(data: dict, letters, labels, st: dict) -> list:
    def jac(a, b):
        sa, sb = set(a), set(b)
        return len(sa & sb) / len(sa | sb) if (sa or sb) else 1.0

    rows = [["Query", "Category", "distinct documents", f"{letters[0]}·{letters[1]} overlap"]]
    for query in data["queries"]:
        for content_type in data["types"]:
            cell = data["cells"][f"{query}|{content_type}"]
            ids = {ltr: [d["id"] for d in cell[labels[ltr]]] for ltr in letters}
            rows.append([
                query,
                base.TYPE_LABEL[content_type],
                str(len({i for v in ids.values() for i in v})),
                f"{jac(ids[letters[0]], ids[letters[1]]):.2f}",
            ])
    table = Table(
        rows, colWidths=[2.2 * inch, 1.3 * inch, 1.6 * inch, 1.5 * inch], hAlign="LEFT"
    )
    table.setStyle(base._grid())

    by_arm: dict[str, list[float]] = {}
    for row in data["timing"]:
        by_arm.setdefault(row["arm"], []).append(row["seconds"])
    trows = [["Arm", "median seconds per query", "one-time index cost"]]
    for ltr in letters:
        values = by_arm.get(labels[ltr], [0.0])
        extra = (
            "~23 min over the papers corpus, plus a second index and a second model"
            if "splade" in labels[ltr]
            else "none"
        )
        trows.append([ltr, f"{statistics.median(values):.3f} s", extra])
    ttable = Table(
        trows, colWidths=[0.6 * inch, 1.9 * inch, 4.1 * inch], hAlign="LEFT"
    )
    ttable.setStyle(base._grid())

    return [
        Paragraph("Agreement and cost", st["h1"]),
        Paragraph(
            "Reported without interpretation. Overlap is the share of the two "
            "top-tens they share: 1.00 identical, 0.00 disjoint. 10 distinct "
            "documents would mean the two arms agree completely, 20 that they share "
            "nothing.",
            st["small"],
        ),
        Spacer(1, 10),
        table,
        Spacer(1, 16),
        Paragraph("Cost", st["h2"]),
        ttable,
        Spacer(1, 6),
        Paragraph(
            "Both arms pay the same cross-encoder pass, so the per-query difference "
            "between them is small. The column that matters is the third one.",
            st["small"],
        ),
    ]


def key_page(labels, letters, st: dict) -> list:
    pretty = {
        "fusion_dense_pool+xenc": (
            "PRODUCTION AS DEPLOYED — dense top-100 per interest, BM25 indexed only "
            "over that pool — <b>+ cross-encoder rerank</b>"
        ),
        "fusion_union_splade+xenc": (
            "THREE CHANNELS — BM25 ∪ dense ∪ SPLADE, RRF-fused over a true union pool "
            "— <b>+ the identical cross-encoder rerank</b>"
        ),
    }
    rows = [["Arm", "What it is"]]
    for ltr in letters:
        rows.append([ltr, Paragraph(pretty[labels[ltr]], st["title"])])
    table = Table(rows, colWidths=[0.6 * inch, 6.6 * inch], hAlign="LEFT")
    style = base._grid()
    style.add("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold")
    style.add("ROWBACKGROUNDS", (0, 1), (-1, -1), [base.colors.white, base.BAND])
    table.setStyle(style)
    return [
        Paragraph("Key — read after you have judged", st["h1"]),
        Spacer(1, 8),
        table,
        Spacer(1, 12),
        Paragraph(
            "One of these two won papers, grants and conferences in both of the "
            "previous booklets. The other has been in both and won nothing — but was "
            "never given a reranker until now, which is the confound this booklet "
            "exists to remove.",
            st["small"],
        ),
    ]


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(base.MUTED)
    canvas.drawString(
        0.6 * inch, 0.34 * inch, "EXP-2026-08-017 · arms K and V · key on the final page"
    )
    canvas.drawRightString(letter[0] - 0.6 * inch, 0.34 * inch, str(doc.page))
    canvas.restoreState()


def build() -> None:
    data = json.loads(DATA.read_text())
    st = base.styles()
    labels = data["blind_labels"]
    letters = sorted(labels)

    story = cover(data, st, letters)
    story.append(PageBreak())
    for query in data["queries"]:
        for content_type in data["types"]:
            cell = data["cells"][f"{query}|{content_type}"]
            parts = base.matrix_page(
                {"cells": {content_type: cell}}, content_type, letters, labels, st
            )
            distinct = len({d["id"] for lst in cell.values() for d in lst})
            story += [
                Paragraph(
                    f"{base.TYPE_LABEL[content_type]} — "
                    f"&ldquo;{base.esc(query)}&rdquo;",
                    st["h1"],
                ),
                # `base.matrix_page`'s own caption is written for four arms; with
                # two, both its counts would be wrong, so it is replaced rather
                # than reused.
                Paragraph(
                    f"{distinct} distinct documents across the two top-tens "
                    "(10 would mean the arms agree completely, 20 that they share "
                    "nothing).",
                    st["small"],
                ),
            ]
            story += parts[2:]
            story.append(PageBreak())
    story += summary(data, letters, labels, st)
    story.append(PageBreak())
    story += key_page(labels, letters, st)

    OUT.parent.mkdir(exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title="Three channels vs the dense pool, both reranked (blinded)",
        author="EXP-2026-08-017",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
