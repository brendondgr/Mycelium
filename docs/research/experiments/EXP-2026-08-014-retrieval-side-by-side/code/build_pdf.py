"""Typeset the blinded comparison booklet for `EXP-2026-08-014`.

    uv run --project eval --with matplotlib python .../code/build_pdf.py

Reads `data/lists.json` and emits `tables/retrieval-comparison.pdf`. Every number
and every title comes from that file; nothing is written by hand here, and no
opinion about which arm is better appears anywhere in the document except the
space left for the reader to write one.

**Layout.** Ten ranked lists of long scientific titles cannot be read side by
side as ten columns of text — so each cell is presented document-centrically:
every distinct document that any arm placed in its top ten appears once, with its
full title and a row number, and the arms' orderings are then given underneath as
sequences of those row numbers. That shows both the contents and the ordering
without truncating a single title, and it makes disagreement visible at a glance
rather than something you have to reconstruct.

Arms are labelled A-J throughout. The mapping is on the last page only.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from timing_chart import make_chart

EXP_DIR = Path(__file__).resolve().parent.parent
DATA = EXP_DIR / "data" / "lists.json"
OUT = EXP_DIR / "tables" / "retrieval-comparison.pdf"
CHART = EXP_DIR / "figures" / "fig-timing.png"

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#666666")
RULE = colors.HexColor("#cccccc")
BAND = colors.HexColor("#f2f4f6")
ACCENT = colors.HexColor("#0072B2")

TYPE_LABEL = {
    "paper": "Papers",
    "grant": "Grants",
    "conference": "Conferences",
    "fellowship": "Fellowships",
}


def styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Title"], fontSize=20, leading=24, textColor=INK,
            alignment=TA_LEFT, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=13, leading=16, textColor=INK,
            spaceBefore=10, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=10.5, leading=13, textColor=MUTED,
            spaceBefore=8, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=9.5, leading=13.5, textColor=INK,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontSize=8, leading=10.5, textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["BodyText"], fontSize=7.6, leading=9.4, textColor=INK,
            spaceAfter=0,
        ),
        "cellmuted": ParagraphStyle(
            "cellmuted", parent=base["BodyText"], fontSize=6.8, leading=8.4,
            textColor=MUTED, spaceAfter=0,
        ),
    }


def esc(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa or sb) else 1.0


def norm_title(text: str) -> str:
    """Lowercased, whitespace-collapsed title — the key duplicates collapse under.

    The store holds the same document more than once under distinct ids (see the
    corpus-hygiene page), and different arms pick different copies. Measuring
    agreement on ids alone therefore counts two arms as disagreeing when they
    chose the same paper, so every agreement number is computed **both** ways.
    """
    return " ".join(str(text).split()).casefold()


def build() -> None:
    data = json.loads(DATA.read_text())
    st = styles()
    labels = data["blind_labels"]          # letter -> arm key
    letters = sorted(labels)
    arm_of = {letters[i]: labels[letters[i]] for i in range(len(letters))}

    story: list = []
    story += cover(data, st)
    story.append(PageBreak())
    story += agreement_section(data, arm_of, st)
    story.append(PageBreak())

    for content_type in data["types"]:
        for query in data["queries"]:
            story += cell_pages(data, content_type, query, arm_of, st)
            story.append(PageBreak())

    story += timing_section(data, arm_of, st)
    story.append(PageBreak())
    story += scorecard(data, st)
    story.append(PageBreak())
    story += key_page(arm_of, st)

    OUT.parent.mkdir(exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=landscape(letter),
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        title="Retrieval comparison — blinded",
        author="EXP-2026-08-014",
    )
    doc.build(story, onLaterPages=footer, onFirstPage=footer)
    print(f"wrote {OUT}")


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        0.55 * inch, 0.32 * inch,
        "EXP-2026-08-014 · blinded retrieval comparison · arm key on the final page",
    )
    canvas.drawRightString(
        landscape(letter)[0] - 0.55 * inch, 0.32 * inch, str(doc.page)
    )
    canvas.restoreState()


def cover(data: dict, st: dict) -> list:
    sizes = data["corpus_sizes"]
    story = [
        Paragraph("Which retrieval process gives you a better list?", st["h1"]),
        Paragraph(
            "Ten retrieval configurations, run over Mycelium's own corpus, for three "
            "queries in your own area. Each one produced a top ten. "
            "<b>The lists are blinded — labelled A to J, with the key on the last "
            "page.</b> Nothing in this document says which is better, because there "
            "is nothing in the record that could say it: this corpus has no "
            "relevance judgments, and an LLM judge is the component we already "
            "measured as non-monotonic in relevance. The judgment is yours.",
            st["body"],
        ),
        Spacer(1, 10),
        Paragraph("How to read it", st["h2"]),
        Paragraph(
            "One page per (category, query). Every document that any arm put in its "
            "top ten is listed once with a row number, so no title is truncated. "
            "Underneath, each arm's ordering is given as a sequence of those row "
            "numbers — read left to right for that arm's rank 1 through 10. "
            "A page is a disagreement map: where the arms agree the sequences look "
            "alike, and where they do not, they do not.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph("What is switched off, and why it matters", st["h2"]),
        Paragraph(
            "These are <i>rankings</i>, not screenshots of the feed. The match "
            "thresholds are off (they gate on a cosine only the dense channel "
            "populates, which would silently empty the lexical arms — that is "
            "C-019), the fellowship eligibility rules are off (otherwise the "
            "fellowship pages compare rule engines, not retrieval), the paper "
            "freshness gate is off, and no LLM was called anywhere.",
            st["body"],
        ),
        Spacer(1, 12),
        Paragraph("Corpus", st["h2"]),
    ]
    rows = [["Category", "Documents", "Query"]]
    for i, content_type in enumerate(data["types"]):
        rows.append([
            TYPE_LABEL[content_type],
            f"{sizes.get(content_type, 0):,}",
            data["queries"][i] if i < len(data["queries"]) else "",
        ])
    table = Table(rows, colWidths=[1.6 * inch, 1.2 * inch, 3.6 * inch], hAlign="LEFT")
    table.setStyle(_grid(header=True))
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "The three queries are run against <i>every</i> category; the right-hand "
            "column above simply lists them.",
            st["small"],
        )
    )
    return story


def _cells(data: dict, content_type: str, query: str) -> dict:
    return data["cells"][f"{content_type}|{query}"]


def agreement_section(data: dict, arm_of: dict, st: dict) -> list:
    """How much do the arms actually differ? The one question needing no judgment."""
    letters = sorted(arm_of)
    per_cell = []
    for content_type in data["types"]:
        for query in data["queries"]:
            cell = _cells(data, content_type, query)
            ids = {ltr: [d["id"] for d in cell[arm_of[ltr]]] for ltr in letters}
            titles = {
                ltr: [norm_title(d["title"]) for d in cell[arm_of[ltr]]]
                for ltr in letters
            }
            union = {i for lst in ids.values() for i in lst}
            union_titles = {t for lst in titles.values() for t in lst}
            pairs = [
                jaccard(ids[a], ids[b])
                for i, a in enumerate(letters)
                for b in letters[i + 1 :]
            ]
            tpairs = [
                jaccard(titles[a], titles[b])
                for i, a in enumerate(letters)
                for b in letters[i + 1 :]
            ]
            wasted = sum(len(lst) - len(set(lst)) for lst in titles.values())
            per_cell.append({
                "type": content_type, "query": query,
                "distinct": len(union),
                "distinct_titles": len(union_titles),
                "mean_jaccard": statistics.mean(pairs) if pairs else 1.0,
                "mean_jaccard_title": statistics.mean(tpairs) if tpairs else 1.0,
                "wasted_slots": wasted,
                "unanimous": len(
                    {t for t in union_titles if all(t in lst for lst in titles.values())}
                ),
            })

    wasted_total = sum(r["wasted_slots"] for r in per_cell)
    story = [
        Paragraph("Do these ten processes actually return different things?", st["h1"]),
        Paragraph(
            "This is the half of the question that needs no opinion. If ten "
            "configurations return nearly the same ten documents, then the "
            "differences the benchmark measures are invisible here whichever one "
            "is theoretically better — and the benchmark is not answering a "
            "question about this product. If they return wildly different "
            "documents, the choice matters a great deal and the benchmark still "
            "may not be the right way to choose.",
            st["body"],
        ),
        Spacer(1, 8),
        Paragraph(
            "<b>Distinct documents</b> counts how many different items appear across "
            "all ten top-tens. Ten means total agreement; one hundred means total "
            "disagreement. <b>Unanimous</b> counts documents every single arm ranked "
            "in its top ten.",
            st["small"],
        ),
        Spacer(1, 10),
    ]
    rows = [[
        "Category", "Query", "Distinct documents\n(10 = identical, 100 = disjoint)",
        "Distinct after\ncollapsing duplicates",
        "Unanimous\ntop-10 items", "Mean pairwise\nJaccard@10\n(by id)",
        "…collapsing\nduplicates",
    ]]
    for row in per_cell:
        rows.append([
            TYPE_LABEL[row["type"]], row["query"], str(row["distinct"]),
            str(row["distinct_titles"]),
            str(row["unanimous"]), f"{row['mean_jaccard']:.2f}",
            f"{row['mean_jaccard_title']:.2f}",
        ])
    rows.append([
        "", "overall (mean)",
        f"{statistics.mean([r['distinct'] for r in per_cell]):.0f}",
        f"{statistics.mean([r['distinct_titles'] for r in per_cell]):.0f}",
        f"{statistics.mean([r['unanimous'] for r in per_cell]):.1f}",
        f"{statistics.mean([r['mean_jaccard'] for r in per_cell]):.2f}",
        f"{statistics.mean([r['mean_jaccard_title'] for r in per_cell]):.2f}",
    ])
    table = Table(
        rows,
        colWidths=[
            1.0 * inch, 2.5 * inch, 1.7 * inch, 1.35 * inch,
            1.0 * inch, 1.05 * inch, 0.95 * inch,
        ],
        hAlign="LEFT",
    )
    style = _grid(header=True)
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    style.add("BACKGROUND", (0, -1), (-1, -1), BAND)
    table.setStyle(style)
    story.append(table)
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            "Two columns, because the store holds the same document more than once "
            "under different ids and different arms pick different copies — which "
            "counts as disagreement when it is not. The right-hand figures collapse "
            "on normalised title. See the next page.",
            st["small"],
        )
    )
    story.append(PageBreak())
    story += hygiene_page(wasted_total, st)
    return story


def hygiene_page(wasted_total: int, st: dict) -> list:
    """A defect reading the lists made obvious and no aggregate metric would."""
    stats = json.loads((EXP_DIR / "data" / "corpus_stats.json").read_text())
    story = [
        Paragraph("A finding that fell out of looking at the lists", st["h1"]),
        Paragraph(
            "The same document is in the store several times under different ids, so "
            "it appears several times in one top ten. On the first page of papers "
            "below, one framework occupies three of the ten slots in several arms. "
            "This belongs to no arm — every retrieval process inherits it — and it "
            "costs the reader slots no matter which one wins.",
            st["body"],
        ),
        Spacer(1, 6),
        Paragraph(
            f"<b>Across the 120 ranked lists in this booklet, "
            f"{wasted_total} top-ten slots were spent on a document whose title had "
            f"already appeared higher in the same list.</b>",
            st["body"],
        ),
        Spacer(1, 10),
    ]
    rows = [["Category", "Rows", "Duplicate rows by title", "Share", "Untitled rows"]]
    for content_type in ("paper", "grant", "conference", "fellowship"):
        row = stats.get(content_type)
        if not row:
            continue
        rows.append([
            TYPE_LABEL[content_type],
            f"{row['rows']:,}",
            f"{row['duplicate_title_rows']:,}",
            f"{row['duplicate_share']:.1%}",
            f"{row['untitled']:,}",
        ])
    table = Table(
        rows,
        colWidths=[1.4 * inch, 1.2 * inch, 1.9 * inch, 1.0 * inch, 1.3 * inch],
        hAlign="LEFT",
    )
    table.setStyle(_grid(header=True))
    story += [table, Spacer(1, 10), Paragraph("Most-duplicated titles", st["h3"])]

    rows = [["Copies", "Title"]]
    for row in stats.get("worst_offenders", [])[:8]:
        rows.append([str(row["copies"]), Paragraph(esc(row["title"]), st["cell"])])
    table = Table(rows, colWidths=[0.7 * inch, 8.1 * inch], hAlign="LEFT")
    table.setStyle(_grid(header=True, zebra=True))
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Under 1% of rows in every category, which is why no aggregate metric "
            "ever flagged it — and highly visible at rank 1 to 3, which is the only "
            "place a reader looks.",
            st["small"],
        )
    )
    return story


def cell_pages(data: dict, content_type: str, query: str, arm_of: dict, st: dict) -> list:
    letters = sorted(arm_of)
    cell = _cells(data, content_type, query)

    # Row numbering: every document any arm surfaced, ordered by its best rank
    # anywhere, then by how many arms carried it.
    best: dict[str, tuple[int, int]] = {}
    meta: dict[str, dict] = {}
    for ltr in letters:
        for rank, doc in enumerate(cell[arm_of[ltr]], start=1):
            meta[doc["id"]] = doc
            prior = best.get(doc["id"])
            count = (prior[1] if prior else 0) + 1
            best[doc["id"]] = (min(prior[0], rank) if prior else rank, count)
    order = sorted(best, key=lambda i: (best[i][0], -best[i][1], meta[i]["title"]))
    number = {doc_id: n for n, doc_id in enumerate(order, start=1)}

    story = [
        Paragraph(
            f"{TYPE_LABEL[content_type]} — &ldquo;{esc(query)}&rdquo;", st["h1"]
        ),
        Paragraph(
            f"{len(order)} distinct documents across the ten top-tens. "
            "Numbers on the left are row ids used by the ordering table underneath.",
            st["small"],
        ),
        Spacer(1, 6),
    ]

    rows = [["#", "Document", "Source", "In top-10 of"]]
    seen_title: dict[str, int] = {}
    for doc_id in order:
        doc = meta[doc_id]
        carriers = "".join(
            ltr for ltr in letters if doc_id in {d["id"] for d in cell[arm_of[ltr]]}
        )
        first = seen_title.setdefault(norm_title(doc["title"]), number[doc_id])
        mark = (
            f" <font color='#B4531A'>[duplicate row — same title as #{first}]</font>"
            if first != number[doc_id]
            else ""
        )
        title = Paragraph(f"<b>{esc(doc['title'])}</b>{mark}", st["cell"])
        snippet = Paragraph(esc(doc["snippet"][:190]), st["cellmuted"])
        rows.append([
            str(number[doc_id]),
            [title, snippet],
            Paragraph(esc(doc["source"]), st["cellmuted"]),
            Paragraph(f"<b>{carriers}</b>", st["cell"]),
        ])
    table = Table(
        rows,
        colWidths=[0.3 * inch, 5.9 * inch, 1.5 * inch, 1.1 * inch],
        hAlign="LEFT",
        repeatRows=1,
    )
    table.setStyle(_grid(header=True, zebra=True))
    story.append(table)

    story.append(Spacer(1, 10))
    story.append(Paragraph("Each arm's top ten, in order", st["h3"]))
    seq_rows = [["Arm", "rank 1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]]
    for ltr in letters:
        docs = cell[arm_of[ltr]]
        seq_rows.append(
            [ltr] + [str(number[d["id"]]) for d in docs] + [""] * (10 - len(docs))
        )
    seq = Table(
        seq_rows,
        colWidths=[0.5 * inch] + [0.62 * inch] * 10,
        hAlign="LEFT",
    )
    style = _grid(header=True, zebra=True)
    style.add("ALIGN", (1, 1), (-1, -1), "CENTER")
    style.add("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold")
    seq.setStyle(style)
    story.append(seq)
    return story


def timing_section(data: dict, arm_of: dict, st: dict) -> list:
    letters = sorted(arm_of)
    by_arm: dict[str, list[float]] = {}
    for row in data["timing"]:
        by_arm.setdefault(row["arm"], []).append(row["seconds"])
    medians = {
        ltr: statistics.median(by_arm.get(arm_of[ltr], [0.0])) for ltr in letters
    }
    make_chart(medians, out_dir=CHART.parent)

    story = [
        Paragraph("How long each one took", st["h1"]),
        Paragraph(
            "Median seconds to answer <i>one</i> query, per arm, over the twelve "
            "(category, query) cells. Log scale — the arms differ by more than two "
            "orders of magnitude, which a linear axis would hide entirely.",
            st["body"],
        ),
        Spacer(1, 8),
        Image(str(CHART), width=9.2 * inch, height=3.9 * inch),
        Spacer(1, 8),
        Paragraph("One-time costs, paid before any query is answered", st["h3"]),
    ]
    rows = [["Category", "BM25 index build", "Sparse index load", "Sparse index encode (once)"]]
    grouped: dict[str, dict[str, float]] = {}
    for row in data["index_cost"]:
        grouped.setdefault(row["type"], {})[row["stage"]] = row["seconds"]
    for content_type, stages in grouped.items():
        encode = stages.get("splade_encode_one_time")
        rows.append([
            TYPE_LABEL[content_type],
            f"{stages.get('bm25_index_build', 0):.1f} s",
            f"{stages.get('splade_matrix_load', 0):.1f} s",
            "—" if encode is None or math.isnan(encode) else f"{encode / 60:.1f} min",
        ])
    table = Table(
        rows, colWidths=[1.5 * inch, 1.8 * inch, 1.8 * inch, 2.4 * inch], hAlign="LEFT"
    )
    table.setStyle(_grid(header=True))
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "The chart is per-query latency; the table is setup. Conflating them is "
            "how a method that costs half an hour once looks the same as one that "
            "costs half a second every single time somebody opens their feed.",
            st["small"],
        )
    )
    return story


def scorecard(data: dict, st: dict) -> list:
    story = [
        Paragraph("Your scorecard", st["h1"]),
        Paragraph(
            "One row per page you looked at. Write the arm letter you would rather "
            "ship, and — more useful than the winner — the letter you would refuse. "
            "If two are indistinguishable, say so; that is a finding, and it is the "
            "finding the benchmark cannot produce.",
            st["body"],
        ),
        Spacer(1, 10),
    ]
    rows = [["Category", "Query", "Best", "Worst", "Indistinguishable?", "Note"]]
    for content_type in data["types"]:
        for query in data["queries"]:
            rows.append([TYPE_LABEL[content_type], query, "", "", "", ""])
    table = Table(
        rows,
        colWidths=[1.1 * inch, 2.6 * inch, 0.6 * inch, 0.7 * inch, 1.3 * inch, 3.3 * inch],
        rowHeights=[0.26 * inch] + [0.38 * inch] * (len(rows) - 1),
        hAlign="LEFT",
    )
    table.setStyle(_grid(header=True, zebra=True))
    story.append(table)
    return story


def key_page(arm_of: dict, st: dict) -> list:
    pretty = {
        "bm25_only": "BM25 alone, over the whole corpus",
        "dense_only": "Embedding similarity alone (pgvector cosine)",
        "fusion_dense_pool": "PRODUCTION AS DEPLOYED — RRF, BM25 restricted to the dense pool",
        "fusion_union_pool": "RRF over a true union pool (dense ∪ corpus-wide BM25)",
        "fusion_union_splade": "RRF over three channels: BM25 ∪ dense ∪ SPLADE",
    }
    story = [
        Paragraph("Key — read after you have judged", st["h1"]),
        Paragraph(
            "&ldquo;+ cross-encoder&rdquo; means that arm's top 50 was re-scored by "
            "<font face='Courier'>ms-marco-MiniLM-L-6-v2</font> and the new top ten "
            "reported. The record's position on that reranker is a refutation "
            "(C-013), measured on an external collection and never looked at "
            "directly until now.",
            st["body"],
        ),
        Spacer(1, 12),
    ]
    rows = [["Arm", "What it is"]]
    for ltr in sorted(arm_of):
        key = arm_of[ltr]
        base = key.removesuffix("+xenc")
        text = pretty[base] + (
            "  <b>+ cross-encoder rerank</b>" if key.endswith("+xenc") else ""
        )
        rows.append([ltr, Paragraph(text, st["cell"])])
    table = Table(rows, colWidths=[0.6 * inch, 8.2 * inch], hAlign="LEFT")
    style = _grid(header=True, zebra=True)
    style.add("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold")
    table.setStyle(style)
    story.append(table)
    return story


def _grid(*, header: bool = False, zebra: bool = False) -> TableStyle:
    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
    if header:
        style.add("BACKGROUND", (0, 0), (-1, 0), ACCENT)
        style.add("TEXTCOLOR", (0, 0), (-1, 0), colors.white)
        style.add("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")
    if zebra:
        style.add("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND])
    return style


if __name__ == "__main__":
    build()
