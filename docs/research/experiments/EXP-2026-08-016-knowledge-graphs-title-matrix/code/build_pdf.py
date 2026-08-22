"""Typeset the knowledge-graphs matrix (`EXP-2026-08-016`).

    uv run --project eval python .../code/build_pdf.py

The table, page and style code is `EXP-2026-08-015`'s, imported rather than
copied — the two booklets must be typeset identically or a reader comparing them
would be reading a layout difference as a result. Only the parts that genuinely
differ are redefined here: the cover prose (different query, different letters)
and the key page.
"""

from __future__ import annotations

import json
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
OUT = EXP_DIR / "tables" / "knowledge-graphs-comparison.pdf"


def cover(data: dict, st: dict, letters) -> list:
    sizes = data["corpus_sizes"]
    joined = ", ".join(letters[:-1]) + f" and {letters[-1]}"
    return [
        Paragraph("Four arms, a second research area", st["h1"]),
        Paragraph(f"&ldquo;{base.esc(data['query'])}&rdquo;", st["h2"]),
        Spacer(1, 4),
        Paragraph(
            f"The same four retrieval configurations as the healthcare booklet, "
            f"blinded as <b>{joined}</b> — a <b>third</b> set of letters, sharing "
            "none with either previous booklet, so no earlier verdict carries over "
            "and no letter can be assumed to have kept its meaning. The key is on "
            "the last page.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph("How to read a page", st["h2"]),
        Paragraph(
            "One page per category. <b>Each row is one document, title in full and "
            "nothing else. Each column is one arm. The number is where that arm "
            "ranked it — 1 to 10 — and a blank means that arm did not surface it at "
            "all.</b> Read a column downwards for one arm's top ten in order; read a "
            "row across to see how differently the four treated the same document. "
            "Rows are sorted by the best rank anyone gave, so agreement sits at the "
            "top and disagreement shows as gaps. Top-three placements are shaded.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph("Why this one exists", st["h2"]),
        Paragraph(
            "The healthcare read gave a clear per-category winner. This asks whether "
            "that was a property of the arms or of that corner of the corpus. If the "
            "same one wins here, there is a configuration to ship; if a different one "
            "does, then no single configuration is right for the whole product.",
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


def key_page(labels, letters, st: dict) -> list:
    rows = [["Arm", "What it is"]]
    for ltr in letters:
        rows.append([ltr, Paragraph(base.PRETTY[labels[ltr]], st["title"])])
    table = Table(rows, colWidths=[0.6 * inch, 6.6 * inch], hAlign="LEFT")
    style = base._grid()
    style.add("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold")
    style.add(
        "ROWBACKGROUNDS", (0, 1), (-1, -1), [base.colors.white, base.BAND]
    )
    table.setStyle(style)
    return [
        Paragraph("Key — read after you have judged", st["h1"]),
        Spacer(1, 8),
        table,
        Spacer(1, 12),
        Paragraph(
            "These are the same four arms as the healthcare booklet under different "
            "letters, so the two reads can be laid side by side once both are done.",
            st["small"],
        ),
    ]


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(base.MUTED)
    canvas.drawString(
        0.6 * inch, 0.34 * inch, "EXP-2026-08-016 · arms M–R · key on the final page"
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
    for i, content_type in enumerate(data["types"]):
        story += base.matrix_page(data, content_type, letters, labels, st)
        if i < len(data["types"]) - 1:
            story.append(PageBreak())
    story.append(PageBreak())
    story += base.summary(data, letters, labels, st)
    story.append(PageBreak())
    story += key_page(labels, letters, st)

    OUT.parent.mkdir(exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title="Knowledge graphs — four-arm retrieval comparison (blinded)",
        author="EXP-2026-08-016",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
