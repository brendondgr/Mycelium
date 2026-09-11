"""Render a sample daily report PDF from synthetic data — no database, no model.

The formatting of the daily report is the one thing about it that cannot be
reviewed from a test assertion: "is the hierarchy clear, does the match percent
stand out, does the contents page navigate" are questions you answer by looking at
a page. Waiting for 3am to look at one is not a review loop, so this command builds
a representative day and renders it on demand.

The sample is not hand-written markdown. It runs the real writer
(:func:`apps.content.briefing_sections.generate_report_body`) over synthetic items
with the model seam stubbed out, so what you review is the deterministic body the
report actually emits — and the same items are rendered into the Top-N listings
below it. A formatting change that this sample does not show is a formatting change
the report does not have.

    uv run --project web/backend python web/backend/manage.py render_sample_report
    ... --kind lab               # a lab's report (its own section carries its name)
    ... --out /tmp/sample.pdf
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.content import briefing_sections
from apps.content.briefing import ScopePart
from apps.content.daily_report import (
    PERSONAL_LABEL,
    TOP_PERSONAL,
    TOP_PROJECT,
    ReportData,
    ReportItem,
    ReportPart,
)
from apps.content.daily_report_pdf import render_report_pdf
from apps.content.theme_report import ThemeSection

_TODAY = "2026-08-14"
_LAB_NAME = "Pulse Lab"

#: One synthetic day, in the flattened shape ``briefing._showcase_item`` produces.
#: Papers carry two distinct focus clusters so the grouped write-up is exercised;
#: opportunities carry deadlines and no cluster, which is the other real shape.
_PAPERS: list[dict] = [
    {
        "title": "Self-supervised depth estimation for reef-scale photogrammetry",
        "url": "https://example.org/papers/reef-depth",
        "verdict": "read",
        "lead": (
            "It solves the scale-drift problem your Coral Atlas surveys hit on long "
            "transects, and the released weights are trained on imagery close enough "
            "to yours to fine-tune rather than retrain."
        ),
        "deadline_date": "",
        "is_entrant": True,
        "cluster_label": "AI for Oceanography",
    },
    {
        "title": "Benthic habitat classification under variable turbidity",
        "url": "https://example.org/papers/turbidity",
        "verdict": "read",
        "lead": (
            "Directly addresses the turbidity failure mode you flagged in the mid- "
            "season surveys, with an ablation over the exact sensor band you use."
        ),
        "deadline_date": "",
        "is_entrant": True,
        "cluster_label": "AI for Oceanography",
    },
    {
        "title": "Temporal consistency losses for long-horizon video segmentation",
        "url": "https://example.org/papers/temporal",
        "verdict": "skim",
        "lead": (
            "A method you could lift wholesale into the transect pipeline; the loss "
            "needs no extra labels, which matters given your annotation budget."
        ),
        "deadline_date": "",
        "is_entrant": False,
        "cluster_label": "AI for Oceanography",
    },
    {
        "title": "Clinician-in-the-loop evaluation of diagnostic agent chains",
        "url": "https://example.org/papers/agent-eval",
        "verdict": "skim",
        "lead": (
            "The evaluation protocol is the part worth borrowing: it measures where "
            "the human overrides the chain, which is the number your review board "
            "asked for."
        ),
        "deadline_date": "",
        "is_entrant": True,
        "cluster_label": "Medical AI Agents",
    },
    {
        "title": "Calibration of uncertainty estimates in clinical decision support",
        "url": "https://example.org/papers/calibration",
        "verdict": "file",
        "lead": (
            "Gives you a defensible way to report confidence alongside each "
            "recommendation instead of a bare score."
        ),
        "deadline_date": "",
        "is_entrant": False,
        "cluster_label": "Medical AI Agents",
    },
]

_GRANTS: list[dict] = [
    {
        "title": "NSF Ocean Technology and Interdisciplinary Coordination",
        "url": "https://example.org/grants/nsf-oceantech",
        "verdict": "read",
        "lead": (
            "The instrumentation track fits the survey rig you are already building, "
            "and the interdisciplinary requirement is satisfied by the clinical arm "
            "of the lab."
        ),
        "deadline_date": "2026-10-02",
        "is_entrant": True,
        "cluster_label": "AI for Oceanography",
    },
    {
        "title": "Moore Foundation Data-Driven Discovery Investigator",
        "url": "https://example.org/grants/moore-ddd",
        "verdict": "skim",
        "lead": (
            "Method-first funding with no domain restriction — the strongest fit for "
            "the segmentation work that sits between both of your focus areas."
        ),
        "deadline_date": "2026-09-15",
        "is_entrant": False,
        "cluster_label": "AI for Oceanography",
    },
]

#: Conferences are the shape that most needed the entry redesign: several dated
#: rounds of different kinds, and a venue rank that must read as a label rather than
#: as a second opportunity signal. Both are here so the sample shows them.
_CONFERENCES: list[dict] = [
    {
        "title": "OCEANS 2027 — Sensing and Autonomy track",
        "url": "https://example.org/conf/oceans-2027",
        "verdict": "read",
        "lead": (
            "The autonomy track has run a reef-mapping session for three years; your "
            "transect results would land in scope without reframing."
        ),
        "deadline_date": "2026-11-20",
        "deadlines": [
            {"date": "2026-11-20", "kind": "abstract", "label": ""},
            {"date": "2027-01-08", "kind": "manuscript", "label": ""},
            {"date": "2027-06-14", "kind": "event", "label": ""},
        ],
        "rank_badges": [{"system": "core", "rank": "B"}],
        "is_entrant": True,
        "cluster_label": "AI for Oceanography",
        "edition": "2027",
    },
    {
        "title": (
            "NORA: The Third Workshop on Knowledge Graphs & Agentic Systems "
            "Interplay"
        ),
        "url": "https://example.org/conf/nora-2027",
        "verdict": "read",
        "lead": (
            "Your work on agentic querying and tool-calling design fits the technical "
            "scope squarely."
        ),
        "deadline_date": "2026-09-15",
        "deadlines": [{"date": "2026-09-15", "kind": "submission", "label": ""}],
        "rank_badges": [],
        "is_entrant": True,
        "cluster_label": "Medical AI Agents",
        "bridge_labels": ["AI for Oceanography"],
    },
]

_PROJECT_PAPERS: list[dict] = [
    {
        "title": "Photogrammetric change detection across seasonal reef surveys",
        "url": "https://example.org/papers/change-detection",
        "verdict": "read",
        "lead": (
            "The change-detection baseline here is the one Coral Atlas is missing; it "
            "would give the seasonal comparison a number instead of a figure."
        ),
        "deadline_date": "",
        "is_entrant": True,
        "cluster_label": "AI for Oceanography",
    },
    {
        "title": "Open benchmark for multi-year coral cover estimation",
        "url": "https://example.org/papers/coral-benchmark",
        "verdict": "file",
        "lead": "A public benchmark you can report against rather than build.",
        "deadline_date": "",
        "is_entrant": False,
        "cluster_label": "AI for Oceanography",
    },
]

_CATEGORIES = ["papers", "grants", "conferences"]
_PERSONAL_ITEMS = {
    "papers": _PAPERS,
    "grants": _GRANTS,
    "conferences": _CONFERENCES,
}
_PROJECT_ITEMS = {"papers": _PROJECT_PAPERS, "grants": [], "conferences": []}
_PROJECT_LABEL = "Coral Atlas"


def _counts(items: dict[str, list[dict]]) -> dict[str, int]:
    """How many of each category entered the slate — the report's "new"."""
    return {
        category: sum(1 for item in rows if item.get("is_entrant"))
        for category, rows in items.items()
    }


def _no_model(system: str, user: str) -> None:
    """The stubbed model seam: always fall back to the deterministic writer.

    A sample rendered from live model prose would be a sample of that morning's
    wording, which is not what anyone is reviewing here.
    """
    return None


#: The reader's declared themes, in the order the report sections them.
_THEMES = [
    ("c-ocean", "AI for Oceanography"),
    ("c-medai", "Medical AI Agents"),
]

#: A theme holding a settled list but no news today — it must appear once, in the
#: quiet line, and never as a heading over a page of things the reader has seen.
_QUIET_THEME = ("Sensor Fusion", 7)

_TYPE_OF = {"papers": "paper", "grants": "grant", "conferences": "conference"}
_SOURCE_OF = {
    "papers": "Nature Methods",
    "grants": "National Science Foundation",
    "conferences": "Lisbon, Portugal",
}


def _report_item(category: str, row: dict, position: int) -> ReportItem:
    return ReportItem(
        # Synthetic but stable, so the sample's deadline horizon and its listings
        # agree the way they do on a real day.
        content_id=f"sample-{category}-{position}",
        type=_TYPE_OF[category],
        category=category,
        title=row["title"],
        url=row["url"],
        headline="",
        reason=row["lead"],
        source=_SOURCE_OF[category],
        deadline_date=row["deadline_date"],
        is_new=row["is_entrant"],
        cluster_label=row["cluster_label"],
        position=position,
        verdict=row["verdict"],
        lead=row["lead"],
        caveat=row.get("caveat", ""),
        bridge_labels=row.get("bridge_labels", []),
        edition=row.get("edition", ""),
        deadlines=row.get("deadlines", []),
        rank_badges=row.get("rank_badges", []),
    )


def _report_items(category: str, rows: list[dict]) -> list[ReportItem]:
    return [_report_item(category, row, n) for n, row in enumerate(rows, start=1)]


def _theme_sections(items: dict[str, list[dict]]) -> list[ThemeSection]:
    """Split the synthetic day into one section per theme.

    Entrants and standing rows are separated exactly the way the real gather does
    it, so the sample shows the real document: what entered leads, what is settled
    follows as reference rows, and a theme with no news never gets a heading.
    """
    sections: list[ThemeSection] = []
    for cluster_id, label in _THEMES:
        section = ThemeSection(cluster_id=cluster_id, label=label)
        for category, rows in items.items():
            mine = [row for row in rows if row["cluster_label"] == label]
            entrants = [row for row in mine if row["is_entrant"]]
            standing = [row for row in mine if not row["is_entrant"]]
            if entrants:
                section.entrants[category] = [
                    _report_item(category, row, n)
                    for n, row in enumerate(entrants, start=1)
                ]
            if standing:
                section.standing[category] = [
                    _report_item(category, row, len(entrants) + n)
                    for n, row in enumerate(standing, start=1)
                ]
        if section.is_alive:
            sections.append(section)
    return sections


#: Mylo's prose for the sample, written by hand rather than by a live call: a
#: sample rendered from this morning's wording would be a sample of that wording,
#: not of the page.
_NARRATIVE = {
    "lead": (
        "The oceanography strand is where today actually moved — two papers land "
        "on the same scale-drift failure you flagged after the mid-season "
        "transects, and the NSF instrumentation call would fund the rig that "
        "fixes it. Start there; the clinical items can wait until the review "
        "board's protocol question comes back."
    ),
    "lead_origin": "llm",
    "themes": [
        {
            "cluster_id": "c-ocean",
            "label": "AI for Oceanography",
            "read": (
                "Both new papers attack scale drift from opposite ends — one by "
                "constraining depth, one by conditioning on turbidity — and read "
                "together they suggest the survey pipeline is losing accuracy at "
                "the sensor rather than at the model. The NSF call closing in "
                "October funds exactly that instrumentation."
            ),
            "origin": "llm",
        },
        {
            "cluster_id": "c-medai",
            "label": "Medical AI Agents",
            "read": (
                "Quiet strand today, but the one entrant is the protocol your "
                "review board asked for: it measures where a clinician overrides "
                "the chain rather than whether the chain was right."
            ),
            "origin": "llm",
        },
    ],
}


def build_sample(kind: str) -> ReportData:
    """A representative day for ``kind`` ("personal" or "lab"), ready to render."""
    own_label = _LAB_NAME if kind == "lab" else PERSONAL_LABEL
    display_name = _LAB_NAME if kind == "lab" else "Dr. Ana Reyes"

    personal_scope = ScopePart(
        key="personal",
        label=own_label,
        kind="personal",
        scope="",
        counts=_counts(_PERSONAL_ITEMS),
        items=_PERSONAL_ITEMS,
        themes=_scope_sections(_PERSONAL_ITEMS),
        quiet=[_QUIET_THEME],
    )
    project_scope = ScopePart(
        key="p1",
        label=_PROJECT_LABEL,
        kind="project",
        scope="lab" if kind == "lab" else "user",
        counts=_counts(_PROJECT_ITEMS),
        items=_PROJECT_ITEMS,
    )
    body, _ = briefing_sections.generate_report_body(
        "Research focus: AI for oceanography, medical AI agents\n"
        "Keywords: reef photogrammetry, segmentation, clinical decision support",
        _CATEGORIES,
        personal_scope,
        [project_scope],
        complete=_no_model,
        narrative=_NARRATIVE,
    )

    sections = _theme_sections(_PERSONAL_ITEMS)
    return ReportData(
        username="sample",
        display_name=display_name,
        generated_on=_TODAY,
        briefing_markdown=body,
        briefing_origin="llm",
        categories=_CATEGORIES,
        lead=_NARRATIVE["lead"],
        lead_origin="llm",
        counts={c: len(rows) for c, rows in _PERSONAL_ITEMS.items()},
        new_counts=_counts(_PERSONAL_ITEMS),
        personal=ReportPart(
            key="personal",
            label=own_label,
            kind="personal",
            cap=TOP_PERSONAL,
            counts=_counts(_PERSONAL_ITEMS),
            items={c: _report_items(c, rows) for c, rows in _PERSONAL_ITEMS.items()},
            # A deeper slate than the sample lists, so the "showing N of M" note is
            # part of what gets reviewed.
            slate_sizes={"papers": 25, "grants": 2, "conferences": 1},
            themes=sections,
            quiet=[_QUIET_THEME],
        ),
        projects=[
            ReportPart(
                key="p1",
                label=_PROJECT_LABEL,
                kind="project",
                cap=TOP_PROJECT,
                counts=_counts(_PROJECT_ITEMS),
                items={c: _report_items(c, rows) for c, rows in _PROJECT_ITEMS.items()},
                slate_sizes={"papers": 2, "grants": 0, "conferences": 0},
            ),
            # A project with nothing today, to show it holds its summary-table row
            # and gets no section of its own.
            ReportPart(
                key="p2",
                label="Turbidity Compensation",
                kind="project",
                cap=TOP_PROJECT,
                counts=dict.fromkeys(_CATEGORIES, 0),
                items=dict.fromkeys(_CATEGORIES, []),
            ),
        ],
    )


def _scope_sections(items: dict[str, list[dict]]) -> list:
    """The same sections, carrying the flattened dicts the markdown writer reads."""
    out = []
    for section in _theme_sections(items):
        flat = ThemeSection(cluster_id=section.cluster_id, label=section.label)
        for category, rows in section.entrants.items():
            flat.entrants[category] = [_as_dict(item) for item in rows]
        for category, rows in section.standing.items():
            flat.standing[category] = [_as_dict(item) for item in rows]
        out.append(flat)
    return out


def _as_dict(item: ReportItem) -> dict:
    return {
        "title": item.title,
        "url": item.url,
        "verdict": item.verdict,
        "lead": item.lead,
        "caveat": item.caveat,
        "is_entrant": item.is_new,
        "position": item.position,
        "bridge_labels": item.bridge_labels,
        "source_name": item.source,
        "deadline_date": item.deadline_date,
        "cluster_label": item.cluster_label,
    }


class Command(BaseCommand):
    help = "Render a sample daily report PDF from synthetic data (no database)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--kind",
            choices=["personal", "lab"],
            default="personal",
            help="Whose report to sample. A lab's own section carries the lab name.",
        )
        parser.add_argument(
            "--out",
            dest="out",
            metavar="PATH",
            help="Where to write the PDF (default: sample-report-<kind>.pdf here).",
        )

    def handle(self, *args, **options) -> None:
        kind = options["kind"]
        out = Path(options.get("out") or f"sample-report-{kind}.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(render_report_pdf(build_sample(kind)))
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {kind} sample report to {out.resolve()}")
        )
