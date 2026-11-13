"""Daily Discord report — compile, PDF render, and phased send orchestration.

The PDF is read back with ``pypdf`` (already a backend dependency) to assert the
required structure: a summary table with a row per project, a table of contents that
points at the written report, and one capped section per category inside the
Personal part and each project part. Compile is exercised against real
``RelevanceScore`` rows; the send flow is driven with injected seams so it needs no
live Discord.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from apps.accounts.models import WatchPreference
from apps.research.models import Project
from django.contrib.auth.models import User
from pypdf import PdfReader

from tools.delivery import daily_report_send
from tools.delivery.daily_report import (
    ReportData,
    ReportItem,
    ReportPart,
    compile_report_for_user,
)
from tools.delivery.daily_report_pdf import _split_reason, render_report_pdf
from tools.delivery.daily_report_send import run_daily_report_send
from tools.delivery.models import DailyBriefing
from tools.delivery.report_stats import ReportStats
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem


# --------------------------------------------------------------------------- #
# PDF rendering (pure — no database)
# --------------------------------------------------------------------------- #
def _paper_items(n: int, *, entrant: bool = True) -> list[ReportItem]:
    return [
        ReportItem(
            type="paper",
            category="papers",
            title=f"Paper number {i}",
            url=f"https://example.org/p{i}",
            headline="",
            reason=f"Relevant to your work on topic {i}.",
            source="Nature",
            deadline_date="",
            is_new=entrant,
            position=i + 1,
            verdict="read" if i == 0 else "skim",
            lead=f"Relevant to your work on topic {i}.",
            caveat="The cohort is small.",
        )
        for i in range(n)
    ]


def _grant_item(title: str) -> ReportItem:
    return ReportItem(
        type="grant",
        category="grants",
        title=title,
        url="https://example.org/grant",
        headline="",
        reason="Matches your funding needs.",
        source="NSF",
        deadline_date="2026-09-01",
        is_new=True,
        position=1,
        verdict="read",
        lead="Matches your funding needs.",
        caveat="The match rules out non-US applicants.",
    )


def _project_papers() -> list[ReportItem]:
    """A project's own item, worded distinctly from the reader's own list.

    Sharing wording with the personal part makes any "appears once" assertion
    accidentally true or accidentally false depending on the project section.
    """
    item = _paper_items(1)[0]
    item.title = "Project paper"
    item.reason = item.lead = "The baseline Coral Atlas is missing."
    return [item]


def _theme(label: str, papers: list[ReportItem], grants: list[ReportItem]):
    from tools.delivery.theme_report import ThemeSection

    section = ThemeSection(
        cluster_id=f"c-{label.lower().replace(' ', '-')}",
        label=label,
        read=f"Mylo's read on {label}.",
    )
    entrants = {
        "papers": [p for p in papers if p.is_new],
        "grants": [g for g in grants if g.is_new],
    }
    standing = {
        "papers": [p for p in papers if not p.is_new],
        "grants": [g for g in grants if not g.is_new],
    }
    section.entrants = {k: v for k, v in entrants.items() if v}
    section.standing = {k: v for k, v in standing.items() if v}
    return section


def _sample_data() -> ReportData:
    papers = _paper_items(3)
    settled = _paper_items(1, entrant=False)
    settled[0].title = "Settled paper"
    opps = [_grant_item("Big Research Grant")]
    reef = _theme("Reef Mapping", papers + settled, opps)
    return ReportData(
        username="tester",
        display_name="Test Person",
        generated_on="2026-07-19",
        briefing_markdown=(
            "Three strong papers today.\n\n"
            "## Reef Mapping\n\n"
            "### Papers\n\n"
            "1. **[Paper number 0](https://example.org/p0)** — **NEW** · Read\n"
            "Relevant to your work on topic 0.\n\n"
            "2. **Paper number 1** — Skim\n"
            "Relevant to your work on topic 1.\n\n"
            "### Grants\n\n"
            "1. **Big Research Grant** — Read · deadline 2026-09-01\n"
            "Matches your funding needs.\n"
        ),
        briefing_origin="llm",
        categories=["papers", "grants"],
        lead="Today is about reef mapping.",
        lead_origin="llm",
        counts={"papers": 4, "grants": 1},
        new_counts={"papers": 3, "grants": 1},
        personal=ReportPart(
            key="personal",
            label="Personal",
            kind="personal",
            cap=25,
            counts={"papers": 3, "grants": 1},
            items={"papers": papers + settled, "grants": opps},
            themes=[reef],
            quiet=[("Sensor Fusion", 4)],
        ),
        projects=[
            ReportPart(
                key="p1",
                label="Coral Atlas",
                kind="project",
                cap=10,
                counts={"papers": 1, "grants": 0},
                items={"papers": _project_papers(), "grants": []},
            ),
        ],
    )


def _text(data: ReportData) -> str:
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_render_returns_pdf_bytes() -> None:
    pdf = render_report_pdf(_sample_data())
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def _link_uris(data: ReportData) -> list[str]:
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    out = []
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            action = annot.get_object().get("/A") or {}
            if "/URI" in action:
                out.append(str(action["/URI"]))
    return out


def test_a_scraped_url_cannot_break_out_of_its_link() -> None:
    """An item URL is page data: a ``"`` in it cannot close the ``href`` and
    add attributes, and only http(s) is ever made clickable."""
    from tools.delivery.daily_report_pdf import _href, _inline

    assert _href('https://a.example/x" color="red') == (
        "https://a.example/x&quot; color=&quot;red"
    )
    assert _href("javascript:alert(1)") == ""
    assert _href(" JavaScript:alert(1)") == ""
    assert _href("data:text/html,<b>") == ""
    assert _href("https://a.example/?a=1&b=<2>") == (
        "https://a.example/?a=1&amp;b=&lt;2&gt;"
    )
    assert '"' not in _inline('[x](https://a.example/y"onclick="z)').split('href="')[
        1
    ].split('" color=')[0]

    data = _sample_data()
    theme = data.personal.themes[0]
    papers = theme.entrants["papers"]
    papers[0].url = 'https://a.example/x" color="red'
    papers[1].url = "javascript:alert(1)"
    uris = _link_uris(data)
    assert not [u for u in uris if not u.startswith(("http://", "https://"))]
    assert any(u.startswith("https://a.example/x") for u in uris)
    assert "Paper number 1" in _text(data)  # the title stays, unlinked


def test_the_document_is_organised_by_theme() -> None:
    """theme → what's new → what's standing, with the prose beside the items."""
    text = _text(_sample_data())
    for heading in (
        "Contents",
        "Mylo's read on today",
        "Reef Mapping",
        "New articles",
        "New grants",
        "Coral Atlas",
    ):
        assert heading in text, f"missing section: {heading}"
    # The lead opens the body and the theme read sits above its own listings.
    assert "Today is about reef mapping." in text
    assert "Mylo's read on Reef Mapping." in text
    assert "Big Research Grant" in text
    assert "Test Person" in text


def test_a_quiet_theme_is_one_line_not_a_section() -> None:
    text = _text(_sample_data())
    assert "Quiet today:" in text
    assert "Sensor Fusion (4 standing)" in text
    # Named in the quiet line, never given a heading of its own.
    assert text.count("Sensor Fusion") == 1


def test_no_percentage_appears_anywhere_in_the_document() -> None:
    """Position and a verdict replace it — the number measured nothing."""
    text = _text(_sample_data())
    assert "% match" not in text
    assert "STRONG" not in text
    # What stands in its place: the verdict chip and the position in the gutter.
    assert "READ" in text
    assert "1." in text


def test_the_appendix_is_gone() -> None:
    """Reprinting the whole feed answered no question anyone had."""
    text = _text(_sample_data())
    assert "Everything Mylo Found" not in text
    assert "Top 25 Grants, Fellowships & Conferences" not in text


def test_the_cover_carries_both_marks() -> None:
    """Mylo and the Mycelium logo, side by side — the report is from both."""
    from tools.delivery.daily_report_pdf import _ASSETS, _cover_marks

    for name in ("mylo-headshot.png", "mycelium-logo.png"):
        assert (_ASSETS / name).is_file(), f"missing cover art: {name}"
    marks = _cover_marks()
    assert marks is not None
    images = [cell for cell in marks._cellvalues[0] if hasattr(cell, "drawHeight")]
    assert len(images) == 2
    assert len({round(image.drawHeight, 3) for image in images}) == 1


def test_a_missing_mark_does_not_stop_the_report(monkeypatch) -> None:
    """Cover art is decoration; a report that cannot find it is still the report."""
    from tools.delivery import daily_report_pdf

    monkeypatch.setattr(daily_report_pdf, "_ASSETS", Path("/nonexistent/report-art"))
    assert daily_report_pdf._cover_marks() is None
    assert render_report_pdf(_sample_data())[:5] == b"%PDF-"


def test_the_cover_counts_one_grant_as_a_grant() -> None:
    """The summary line is the first full sentence a reader meets."""
    data = _sample_data()
    assert "1 grant for you" in data.summary_line()
    assert "1 grants" not in data.summary_line()
    data.personal.counts["grants"] = 2
    assert "2 grants" in data.summary_line()


def test_the_cover_table_has_a_row_per_theme_then_per_project() -> None:
    """The table inverts: it is a direct index of the sections below it."""
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    cover = reader.pages[0].extract_text()
    assert "Reef Mapping" in cover
    assert "Coral Atlas" in cover
    assert "Papers" in cover and "Grants" in cover
    # The part label is no longer a row — the themes replaced it.
    assert "Personal" not in cover


def test_a_theme_with_a_slate_but_no_news_shows_a_dash_not_a_zero() -> None:
    """Zero reads as "nothing here"; the theme still holds a list to go and look at."""
    data = _sample_data()
    data.personal.themes[0].entrants.pop("grants")
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    assert "—" in reader.pages[0].extract_text()


def test_toc_lists_the_lead_the_themes_and_the_projects() -> None:
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    toc_text = reader.pages[1].extract_text()  # cover=0, TOC=1
    wanted = ("Mylo's read on today", "Reef Mapping", "New articles", "Coral Atlas")
    for entry in wanted:
        assert entry in toc_text, f"missing contents entry: {entry}"
    # The TOC lists real, resolved page numbers (two-pass build), not just dots.
    assert any(ch.isdigit() for ch in toc_text)


def test_every_toc_entry_is_a_link() -> None:
    """A contents page you cannot navigate from is a list of page numbers."""
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    annotations = reader.pages[1].get("/Annots") or []
    links = [
        a.get_object()
        for a in annotations
        if a.get_object().get("/Subtype") == "/Link"
    ]
    assert links, "the contents page has no link annotations at all"
    assert len(links) >= 6
    assert all(link.get("/Dest") or link.get("/A") for link in links)


def test_listed_items_are_numbered_by_their_position_in_their_theme() -> None:
    """A global position would compare scores that are not comparable."""
    text = _text(_sample_data())
    for position in ("1.", "2.", "3."):
        assert position in text
    assert "NEW" in text


def test_the_printed_report_counts_what_is_standing_but_does_not_list_it() -> None:
    """Plan 4.1: the standing list stays on the web.

    Printing it turned a report about what *changed* into a 25-row-per-theme
    catalogue identical to yesterday's, and a document whose bulk does not change
    is a document nobody opens twice. The count survives, because "nothing new in
    a theme that holds 25" and "nothing at all" are different days.
    """
    text = _text(_sample_data())
    assert "Settled paper" not in text
    assert "standing" in text
    # The entrants' lead sentence still appears, exactly once.
    assert text.count("Relevant to your work on topic 0.") == 1


def test_a_deadline_is_reference_material_under_the_entry() -> None:
    """Dates live in the strip below an entry, formatted, never under its title."""
    text = _text(_sample_data())
    assert "Due Sep 1, 2026" in text
    assert "Deadline 2026-09-01" not in text
    assert "2026-09-01" not in text


def test_a_multi_round_item_names_the_next_and_counts_the_rest() -> None:
    """Six dated lines under a two-sentence rationale is a table nobody asked for."""
    data = _sample_data()
    item = data.personal.themes[0].entrants["grants"][0]
    item.deadline_date = "2026-11-20"
    item.deadlines = [
        {"date": "2026-11-20", "kind": "abstract", "label": ""},
        {"date": "2027-01-08", "kind": "manuscript", "label": ""},
        {"date": "2027-06-14", "kind": "event", "label": ""},
    ]
    text = _text(data)
    assert "Due Nov 20, 2026" in text
    assert "Abstract" in text
    assert "+2 more rounds" in text
    # The later rounds are counted, not listed — that is the feed card's job.
    assert "2027-01-08" not in text


def test_an_edition_rides_the_title_rather_than_a_second_badge() -> None:
    """A reopened annual call is badged NEW; the edition says which cycle."""
    data = _sample_data()
    item = data.personal.themes[0].entrants["grants"][0]
    item.title = "OCEANS"
    item.edition = "2027"
    text = _text(data)
    assert "OCEANS 2027" in text
    assert "REOPENED" not in text


def test_a_bridge_item_names_the_other_theme_it_reaches() -> None:
    data = _sample_data()
    data.personal.themes[0].entrants["papers"][0].bridge_labels = ["Sensor Fusion"]
    text = _text(data)
    assert "ALSO IN" in text


def test_a_fallback_origin_is_visible_rather_than_silent() -> None:
    """A template must never be mistaken for something Mylo actually thought."""
    data = _sample_data()
    data.lead_origin = "fallback"
    data.personal.themes[0].read_origin = "fallback"
    text = _text(data)
    assert "Mylo's writer was offline" in text


@pytest.mark.parametrize(
    ("reason", "insight", "note"),
    [
        (
            "It closes the scale-drift gap in your surveys. The weights are "
            "released, so this is a fine-tune rather than a retrain.",
            "It closes the scale-drift gap in your surveys.",
            "The weights are released, so this is a fine-tune rather than a retrain.",
        ),
        (
            "A public benchmark you can report against.",
            "A public benchmark you can report against.",
            "",
        ),
        (
            "Follows Reyes et al. and reuses the same transect protocol you do.",
            "Follows Reyes et al. and reuses the same transect protocol you do.",
            "",
        ),
        ("", "", ""),
    ],
)
def test_a_rationale_splits_into_its_claim_and_its_qualifications(
    reason: str, insight: str, note: str
) -> None:
    assert _split_reason(reason) == (insight, note)


def test_a_written_items_signals_move_out_of_its_title_line() -> None:
    """The written report's chips come from parsing the item line, so parse it."""
    from tools.delivery.daily_report_pdf import _split_item_line

    title, is_new, verdict, deadline = _split_item_line(
        "**[A paper](https://x.org/1)** — **NEW** · Read · deadline 2026-09-01"
    )
    assert title == "**[A paper](https://x.org/1)**"
    assert (is_new, verdict, deadline) == (True, "read", "2026-09-01")

    title, is_new, verdict, deadline = _split_item_line("**Plain** — Skim")
    assert title == "**Plain**"
    assert (is_new, verdict, deadline) == (False, "skim", "")

    assert _split_item_line("**Bare title**") == ("**Bare title**", False, None, "")


def test_verdict_regex_ignores_title_words_like_file_level() -> None:
    """A verdict is read from the signal segment, never from the title (plan 0.1).

    ``Read``, ``Skim`` and ``File`` are ordinary English words. Scanning the whole
    line for them gave *File-Level Provenance* a ``File`` verdict it never earned,
    and any title mentioning reading a ``Read`` one.
    """
    from tools.delivery.daily_report_pdf import _split_item_line

    title, _new, verdict, _due = _split_item_line(
        "**[File-Level Provenance for Agent Tool Calls](https://x.org/2)** "
        "— **NEW** · Skim"
    )
    assert title == "**[File-Level Provenance for Agent Tool Calls](https://x.org/2)**"
    assert verdict == "skim"

    assert _split_item_line("**[A Study of Read-Write Conflicts](https://x.org/3)**")[
        2
    ] is None

    # Prose the model wrote beside the signals stays with the title rather than
    # being silently dropped.
    title, _new, verdict, _due = _split_item_line(
        "**[Cross-theme paper](https://x.org/4)** — **NEW** · File · also in KGs"
    )
    assert title == "**[Cross-theme paper](https://x.org/4)** — also in KGs"
    assert verdict == "file"


def test_inline_does_not_style_prose_starting_with_read() -> None:
    """``_inline`` paints no verdict colour into prose (plan 0.1)."""
    from tools.delivery.daily_report_pdf import _MATCH_HEX, _inline

    lead = _inline("Read the corruption study first, then file the rest.")
    assert _MATCH_HEX not in lead
    assert "<b>Read</b>" not in lead

    # Opt-in still works for a caller that genuinely holds a signal segment.
    assert _MATCH_HEX in _inline("**NEW** · Read", verdicts=True)


def test_the_written_report_renders_its_signals_as_chips_not_highlights() -> None:
    """No inline filled backgrounds anywhere — a chip is a container, not a stripe."""
    from tools.delivery.daily_report_pdf import _inline

    marked = _inline("**NEW** · Read · deadline 2026-09-01", verdicts=True)
    assert "backcolor" not in marked
    assert "Read" in marked


def test_the_sample_report_renders_the_real_written_body() -> None:
    """``render_sample_report`` is the formatting review loop, so it must be real."""
    from tools.delivery.management.commands.render_sample_report import build_sample

    for kind in ("personal", "lab"):
        data = build_sample(kind)
        assert "## AI for Oceanography" in data.briefing_markdown
        assert "1. **[" in data.briefing_markdown
        assert "% match" not in data.briefing_markdown
        assert render_report_pdf(data)[:5] == b"%PDF-"
    assert build_sample("lab").personal.label == "Pulse Lab"
    assert build_sample("personal").personal.label == "Personal"


def test_the_report_never_says_who_an_item_is_best_suited_to() -> None:
    data = _sample_data()
    data.briefing_markdown += "\n\n1. **Something** — Skim\nA reason.\n"
    assert "Best suited to" not in _text(data)


def test_a_quiet_project_gets_no_section() -> None:
    data = _sample_data()
    data.projects.append(
        ReportPart(key="p2", label="Dormant", kind="project", cap=10, counts={})
    )
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    body = "\n".join(page.extract_text() for page in reader.pages[2:])
    assert "Dormant" not in body


def test_the_footer_records_what_was_scanned() -> None:
    """Provenance, not decoration."""
    assert "Compiled 2026-07-19 over your watched papers, grants." in _text(
        _sample_data()
    )


def test_empty_day_still_renders() -> None:
    data = ReportData(
        username="q",
        display_name="Quiet User",
        generated_on="2026-07-19",
        briefing_markdown="",
        briefing_origin="fallback",
        categories=["papers"],
        counts={"papers": 0},
        new_counts={"papers": 0},
        personal=ReportPart(
            key="personal", label="Personal", kind="personal", cap=25, counts={}
        ),
    )
    text = _text(data)
    assert "Nothing entered your lists today." in text


# --------------------------------------------------------------------------- #
# Compile (database)
# --------------------------------------------------------------------------- #
def _paper(
    user,
    i,
    *,
    match,
    rank,
    run_at="2026-07-19",
    first_seen="2026-07-19",
    entered_on="2026-07-19",
):
    """A paper in the reader's slate at ``rank``, entering on ``entered_on``.

    ``entered_on`` is what the report reads: pass an earlier date for a row the
    reader has already been shown.
    """
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=f"p{i}",
        metadata={"title": f"Paper {i}", "venue": "Journal X"},
    )
    return RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=match / 100.0,
        signals={
            "suggested": True,
            "match_percent": match,
            "embedding_match": 0.8,
            "rank": rank,
            "run_at": run_at,
            "first_seen": first_seen,
            "reason": f"reason {i}",
            "top_rank": rank,
            "entered_top_on": entered_on,
            "is_new_top": entered_on == "2026-07-19",
        },
    )


def _opp(
    target, kind, i, *, match, first_seen, deadline="", rank=1,
    entered_on="2026-07-19",
):
    type_map = {
        "grants": ContentItem.Type.GRANT,
        "fellowships": ContentItem.Type.FELLOWSHIP,
    }
    item = ContentItem.objects.create(
        type=type_map[kind],
        source="legacy",
        external_id=f"{kind}-{i}",
        metadata={"title": f"{kind} {i}", "sponsor": "Sponsor Y"},
    )
    return RelevanceScore.objects.create(
        content=item,
        score=match / 100.0,
        signals={
            "suggested": True,
            "match_percent": match,
            "embedding_match": 0.8,
            "first_seen": first_seen,
            "deadline_date": deadline,
            "top_rank": rank,
            "entered_top_on": entered_on,
            "is_new_top": entered_on == "2026-07-19",
        },
        **target,
    )


@pytest.mark.django_db
def test_compile_caps_each_category_in_its_own_right(monkeypatch) -> None:
    # Freeze "today" so the first_seen new-reckoning is deterministic. Both
    # briefing and daily_report reference the same django.utils.timezone module, so
    # one patch covers both; keep it a real datetime so model auto_now_add still works.
    from django.utils import timezone as dj_tz

    fixed = dj_tz.now().replace(year=2026, month=7, day=19)
    monkeypatch.setattr(dj_tz, "now", lambda: fixed)

    user = User.objects.create_user("compiler")
    WatchPreference.objects.create(
        user=user, categories=["papers", "grants", "fellowships"]
    )
    for i in range(27):  # more than the 25 cap
        _paper(user, i, match=99 - i, rank=i + 1)
    _opp(
        {"target_user": user}, "grants", 0,
        match=90, first_seen="2026-07-19", deadline="2026-10-01",
    )
    _opp(
        {"target_user": user}, "fellowships", 0,
        match=95, first_seen="2026-07-19", deadline="2026-09-01",
    )

    data = compile_report_for_user(user)

    assert data.counts == {"papers": 27, "grants": 1, "fellowships": 1}
    assert data.personal.counts == {"papers": 27, "grants": 1, "fellowships": 1}
    assert len(data.personal.items["papers"]) == 25  # capped
    # Grants and fellowships each keep their own list — no pooled top-25 that a
    # heavy category could crowd the others out of.
    assert len(data.personal.items["grants"]) == 1
    assert len(data.personal.items["fellowships"]) == 1


@pytest.mark.django_db
def test_compile_shows_the_whole_slate_and_flags_only_what_entered(monkeypatch) -> None:
    """The PDF prints the reader's Top-25 and marks the part of it that is new.

    Both halves matter. Printing only the day's entrants gave a reader a page of
    whatever had just arrived and hid the strongest matches they had; counting the
    whole slate as new re-announced the same items every morning.
    """
    from django.utils import timezone as dj_tz

    fixed = dj_tz.now().replace(year=2026, month=7, day=19)
    monkeypatch.setattr(dj_tz, "now", lambda: fixed)

    user = User.objects.create_user("narrow")
    WatchPreference.objects.create(user=user, categories=["papers"])
    _paper(user, 1, match=90, rank=1)  # entered the slate today
    _paper(user, 2, match=90, rank=2, entered_on="2026-07-01")  # already showing
    _paper(user, 3, match=90, rank=3, entered_on="2026-07-01")  # already showing

    data = compile_report_for_user(user)

    assert data.counts["papers"] == 3  # the feed holds all three…
    assert [i.title for i in data.personal.items["papers"]] == [
        "Paper 1",
        "Paper 2",
        "Paper 3",
    ]  # …and the report shows all three, in rank order
    assert data.personal.counts["papers"] == 1  # exactly one of them is news
    assert [i.is_new for i in data.personal.items["papers"]] == [True, False, False]


@pytest.mark.django_db
def test_compile_leaves_out_what_is_below_the_slate(monkeypatch) -> None:
    """A row in the feed but outside the Top-25 is not in the report."""
    from django.utils import timezone as dj_tz

    fixed = dj_tz.now().replace(year=2026, month=7, day=19)
    monkeypatch.setattr(dj_tz, "now", lambda: fixed)

    user = User.objects.create_user("deep-feed")
    WatchPreference.objects.create(user=user, categories=["papers"])
    _paper(user, 1, match=90, rank=1)
    below = _paper(user, 2, match=90, rank=2)
    del below.signals["top_rank"]
    below.signals["is_new_top"] = False
    below.save(update_fields=["signals"])

    data = compile_report_for_user(user)

    assert data.counts["papers"] == 2  # both are in the feed
    assert [i.title for i in data.personal.items["papers"]] == ["Paper 1"]


@pytest.mark.django_db
def test_compile_breaks_out_the_readers_projects(monkeypatch) -> None:
    from django.utils import timezone as dj_tz

    fixed = dj_tz.now().replace(year=2026, month=7, day=19)
    monkeypatch.setattr(dj_tz, "now", lambda: fixed)

    user = User.objects.create_user("owner")
    WatchPreference.objects.create(user=user, categories=["papers", "grants"])
    project = Project.objects.create(scope_user=user, name="Coral Atlas")
    _opp(
        {"target_project": project}, "grants", 0,
        match=91, first_seen="2026-07-19",
    )

    data = compile_report_for_user(user)

    assert [p.label for p in data.projects] == ["Coral Atlas"]
    assert data.projects[0].counts["grants"] == 1
    assert data.projects[0].cap == 10
    # Personal first, then the project — the report's section order.
    assert [p.label for p in data.parts] == ["Personal", "Coral Atlas"]


@pytest.mark.django_db
def test_compile_reads_written_briefing() -> None:
    user = User.objects.create_user("briefed")
    DailyBriefing.objects.create(
        user=user, body="## Papers\nHello.", origin=DailyBriefing.Origin.LLM
    )
    data = compile_report_for_user(user)
    assert "Hello." in data.briefing_markdown
    assert data.briefing_origin == DailyBriefing.Origin.LLM


# --------------------------------------------------------------------------- #
# Phased send orchestration (injected seams)
# --------------------------------------------------------------------------- #
class _FakeUser:
    def __init__(self, uid, name):
        self.id = uid
        self._name = name

    def get_username(self):
        return self._name


class _Outcome:
    def __init__(self, ok):
        self.ok = ok


def _no_urgent(_usernames=None, **_kwargs):
    """A stand-in for the urgent pass, which reads the database."""
    from tools.delivery.urgent_alerts import UrgentSummary

    return UrgentSummary()


def _report_for(user) -> ReportData:
    return ReportData(
        username=user.get_username(),
        display_name=user.get_username(),
        generated_on="2026-07-19",
        briefing_markdown="body",
        briefing_origin="llm",
        categories=["papers"],
        counts={"papers": 1},
        new_counts={"papers": 0},
        # A day with nothing new and no alerts pushes nothing (plan H7), so a
        # fixture about the *send* flow has to be a day worth sending.
        stats=ReportStats(matched=1, entered=1),
    )


def test_send_flow_is_phased_and_keeps_the_bytes_for_the_drain(
    monkeypatch, tmp_path
) -> None:
    """Compile-all, render-all, queue-all — and the PDFs survive the batch.

    They used to be deleted the moment the batch finished, which was correct while
    sending was synchronous. Now the drain reads them minutes later (longer during an
    outage), so deleting here would guarantee the very failure the queue exists to
    prevent. The outbox retention sweep owns removal instead, once a row has settled.
    """
    recipients = [_FakeUser(1, "alice"), _FakeUser(2, "bob")]
    monkeypatch.setattr(
        daily_report_send, "eligible_recipients", lambda u, **_kw: recipients
    )
    monkeypatch.setattr(daily_report_send, "_report_dir", lambda: tmp_path / "outbox")

    queued: list[str] = []

    def send_fn(user, data, path, filename):
        assert Path(path).read_bytes() == b"%PDF-fake"
        assert filename.startswith("mylo-report-")
        queued.append(user.get_username())
        return _Outcome(True)

    summary = run_daily_report_send(
        # The urgent pass reads the database; this flow test does not have one.
        urgent_fn=_no_urgent,
        compile_fn=_report_for,
        render_fn=lambda data: b"%PDF-fake",
        send_fn=send_fn,
    )

    assert summary.eligible == 2
    assert summary.compiled == 2
    assert summary.rendered == 2
    assert summary.sent == 2
    assert sorted(queued) == ["alice", "bob"]
    assert len(list((tmp_path / "outbox").glob("*.pdf"))) == 2


def test_send_flow_isolates_one_failure(monkeypatch) -> None:
    recipients = [_FakeUser(1, "good"), _FakeUser(2, "bad")]
    monkeypatch.setattr(
        daily_report_send, "eligible_recipients", lambda u, **_kw: recipients
    )

    def render_fn(data):
        if data.username == "bad":
            raise ValueError("boom")
        return b"%PDF-ok"

    summary = run_daily_report_send(
        # The urgent pass reads the database; this flow test does not have one.
        urgent_fn=_no_urgent,
        compile_fn=_report_for,
        render_fn=render_fn,
        send_fn=lambda *a: _Outcome(True),
    )

    assert summary.eligible == 2
    assert summary.rendered == 1
    assert summary.sent == 1
    assert summary.errors == 1


def test_unreachable_send_is_counted_not_sent(monkeypatch, tmp_path) -> None:
    recipients = [_FakeUser(1, "u")]
    monkeypatch.setattr(
        daily_report_send, "eligible_recipients", lambda u, **_kw: recipients
    )
    monkeypatch.setattr(daily_report_send, "_report_dir", lambda: tmp_path / "outbox")
    summary = run_daily_report_send(
        # The urgent pass reads the database; this flow test does not have one.
        urgent_fn=_no_urgent,
        compile_fn=_report_for,
        render_fn=lambda d: b"%PDF-x",
        send_fn=lambda *a: _Outcome(False),
    )
    assert summary.sent == 0
    assert summary.unreachable == 1
    # Nothing was queued, so no sweep will ever come for this file — drop it now.
    assert list((tmp_path / "outbox").glob("*.pdf")) == []


def test_saved_dir_keeps_the_pdfs(monkeypatch, tmp_path) -> None:
    recipients = [_FakeUser(1, "keeper")]
    monkeypatch.setattr(
        daily_report_send, "eligible_recipients", lambda u, **_kw: recipients
    )
    run_daily_report_send(
        urgent_fn=_no_urgent,
        compile_fn=_report_for,
        render_fn=lambda d: b"%PDF-x",
        send_fn=lambda *a: _Outcome(True),
        report_dir=str(tmp_path),
    )
    files = list(Path(tmp_path).glob("*.pdf"))
    assert len(files) == 1  # report_dir given → files are kept
