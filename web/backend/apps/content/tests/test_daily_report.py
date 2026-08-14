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
from django.contrib.auth.models import User
from pypdf import PdfReader

from apps.accounts.models import WatchPreference
from apps.content import daily_report_send
from apps.content.daily_report import (
    ReportData,
    ReportItem,
    ReportPart,
    compile_report_for_user,
)
from apps.content.daily_report_pdf import render_report_pdf
from apps.content.daily_report_send import run_daily_report_send
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore
from apps.research.models import Project


# --------------------------------------------------------------------------- #
# PDF rendering (pure — no database)
# --------------------------------------------------------------------------- #
def _paper_items(n: int) -> list[ReportItem]:
    return [
        ReportItem(
            type="paper",
            category="papers",
            title=f"Paper number {i}",
            url=f"https://example.org/p{i}",
            match_percent=90 - i,
            headline="",
            reason=f"Relevant to your work on topic {i}.",
            source="Nature",
            deadline_date="",
            is_new=True,
        )
        for i in range(n)
    ]


def _grant_item(title: str) -> ReportItem:
    return ReportItem(
        type="grant",
        category="grants",
        title=title,
        url="https://example.org/grant",
        match_percent=88,
        headline="",
        reason="Matches your funding needs.",
        source="NSF",
        deadline_date="2026-09-01",
        is_new=True,
    )


def _sample_data() -> ReportData:
    papers = _paper_items(3)
    opps = [_grant_item("Big Research Grant")]
    return ReportData(
        username="tester",
        display_name="Test Person",
        generated_on="2026-07-19",
        briefing_markdown=(
            "Three strong papers today.\n\n"
            "## Personal\n\n"
            "### Papers\n\n"
            "#### Reef Mapping\n\n"
            "1. **[Paper number 0](https://example.org/p0)** — **NEW** · 90% match\n"
            "Relevant to your work on topic 0.\n\n"
            "2. **Paper number 1** — 89% match\n"
            "Relevant to your work on topic 1.\n\n"
            "### Grants\n\n"
            "1. **Big Research Grant** — 88% match · deadline 2026-09-01\n"
            "Matches your funding needs.\n"
        ),
        briefing_origin="llm",
        categories=["papers", "grants"],
        counts={"papers": 3, "grants": 1},
        new_counts={"papers": 3, "grants": 1},
        personal=ReportPart(
            key="personal",
            label="Personal",
            kind="personal",
            cap=25,
            counts={"papers": 3, "grants": 1},
            items={"papers": papers, "grants": opps},
        ),
        projects=[
            ReportPart(
                key="p1",
                label="Coral Atlas",
                kind="project",
                cap=10,
                counts={"papers": 1, "grants": 0},
                items={"papers": _paper_items(1), "grants": []},
            ),
        ],
    )


def test_render_returns_pdf_bytes() -> None:
    pdf = render_report_pdf(_sample_data())
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def test_pdf_has_all_required_sections() -> None:
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for heading in (
        "Contents",
        "Your Mylo Report",
        "Personal",
        "Top 25 Articles",
        "Top 25 Grants",
        "Coral Atlas",
        "Top 10 Articles",
    ):
        assert heading in text, f"missing section: {heading}"
    # An item title and the recipient reach the page.
    assert "Big Research Grant" in text
    assert "Test Person" in text


def test_the_appendix_is_gone() -> None:
    """Reprinting the whole feed answered no question anyone had."""
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Everything Mylo Found" not in text
    # Nor the pooled opportunity section it sat under — every category is capped
    # in its own right now, so a heavy grant day can't crowd out conferences.
    assert "Top 25 Grants, Fellowships & Conferences" not in text


def test_the_summary_table_has_a_row_per_project() -> None:
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    cover = reader.pages[0].extract_text()
    assert "Personal" in cover
    assert "Coral Atlas" in cover
    assert "Papers" in cover and "Grants" in cover


def test_toc_lists_the_personal_and_project_sections() -> None:
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    toc_text = reader.pages[1].extract_text()  # cover=0, TOC=1
    assert "Your Mylo Report" in toc_text
    assert "Personal" in toc_text
    assert "Coral Atlas" in toc_text
    assert "Top 25 Articles" in toc_text
    # The TOC lists real, resolved page numbers (two-pass build), not just dots.
    assert any(ch.isdigit() for ch in toc_text)
    # The TOC does not list its own "Contents" title as an entry.
    assert toc_text.count("Your Mylo Report") == 1


def test_toc_mirrors_the_whole_hierarchy() -> None:
    """Every level of the document is on the contents page, not just the top two.

    Including what is *inside* the written report — its parts, its categories, and
    its focus-cluster groups — which is the half of the document a reader could
    previously only find by scrolling.
    """
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    toc_text = reader.pages[1].extract_text()
    for entry in (
        "Your Mylo Report",
        "Reef Mapping",  # the #### focus theme inside the written report
        "Top 25 Articles",
        "Top 25 Grants",
        "Top 10 Articles",  # a project's capped section
    ):
        assert entry in toc_text, f"missing contents entry: {entry}"


def test_every_toc_entry_is_a_link() -> None:
    """A contents page you cannot navigate from is a list of page numbers.

    Each heading is bookmarked and each contents line points at that bookmark, so
    the page carries one ``/Link`` annotation per entry (title and page number are
    both live).
    """
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    annotations = reader.pages[1].get("/Annots") or []
    links = [
        a.get_object()
        for a in annotations
        if a.get_object().get("/Subtype") == "/Link"
    ]
    assert links, "the contents page has no link annotations at all"
    # One entry per H1/H2/H3/H4 in the sample, and every link resolves somewhere.
    assert len(links) >= 10
    assert all(link.get("/Dest") or link.get("/A") for link in links)


def test_a_lab_report_labels_its_own_section_with_the_lab_name() -> None:
    """The reader's own part is named for whoever the report is about."""
    data = _sample_data()
    data.display_name = "Reyes Lab"
    data.personal.label = "Reyes Lab"
    # The written body carries the same label — `briefing._write_briefing` names the
    # part once and both the prose and the listings are built from it.
    data.briefing_markdown = data.briefing_markdown.replace(
        "## Personal", "## Reyes Lab"
    )
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Reyes Lab" in text
    # Not the cover, not the summary table, not the contents page.
    assert "Personal" not in reader.pages[0].extract_text()
    assert "Personal" not in reader.pages[1].extract_text()


def test_listed_items_are_numbered_and_show_their_match() -> None:
    """A Top-25 is a ranking, and the percent match is why an entry earned its rank."""
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for rank in ("1.", "2.", "3."):
        assert rank in text
    assert "90%" in text and "match" in text
    assert "NEW" in text


def test_a_written_items_signals_move_out_of_its_title_line() -> None:
    """The written report's chips come from parsing the item line, so parse it.

    Order-independent on purpose: the line is model-written as often as it is
    generated, and a signal left in the title would print twice — once as text,
    once as a chip.
    """
    from apps.content.daily_report_pdf import _split_item_line

    title, is_new, match, deadline = _split_item_line(
        "**[A paper](https://x.org/1)** — **NEW** · 88% match · deadline 2026-09-01"
    )
    assert title == "**[A paper](https://x.org/1)**"
    assert (is_new, match, deadline) == (True, 88, "2026-09-01")

    # A different order, and a missing signal, land the same way.
    title, is_new, match, deadline = _split_item_line("**Plain** — 40% match")
    assert title == "**Plain**"
    assert (is_new, match, deadline) == (False, 40, "")

    # Nothing to strip leaves the title alone.
    assert _split_item_line("**Bare title**") == ("**Bare title**", False, None, "")


def test_the_written_report_renders_its_signals_as_chips_not_highlights() -> None:
    """No inline filled backgrounds anywhere — a chip is a container, not a stripe."""
    from apps.content.daily_report_pdf import _inline

    marked = _inline("**NEW** · 88% match · deadline 2026-09-01")
    assert "backcolor" not in marked
    assert "88% match" in marked


def test_the_sample_report_renders_the_real_written_body() -> None:
    """``render_sample_report`` is the formatting review loop, so it must be real.

    Its body comes from the actual writer over synthetic items, not from hand-typed
    markdown — a sample that drifts from the generator reviews nothing.
    """
    from apps.content.management.commands.render_sample_report import build_sample

    for kind in ("personal", "lab"):
        data = build_sample(kind)
        assert "#### AI for Oceanography" in data.briefing_markdown
        assert "1. **[" in data.briefing_markdown
        assert render_report_pdf(data)[:5] == b"%PDF-"
    assert build_sample("lab").personal.label == "Pulse Lab"
    assert build_sample("personal").personal.label == "Personal"


def test_the_report_never_says_who_an_item_is_best_suited_to() -> None:
    data = _sample_data()
    data.briefing_markdown += "\n\n1. **Something** — 70% match\nA reason.\n"
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Best suited to" not in text


def test_a_capped_section_says_how_many_it_is_hiding() -> None:
    data = _sample_data()
    data.personal.slate_sizes["papers"] = 40  # a slate deeper than the part prints
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Showing 3 of 40" in text


def test_a_quiet_project_gets_no_section() -> None:
    data = _sample_data()
    data.projects.append(
        ReportPart(key="p2", label="Dormant", kind="project", cap=10, counts={})
    )
    reader = PdfReader(BytesIO(render_report_pdf(data)))
    body = "\n".join(page.extract_text() for page in reader.pages[2:])
    assert "Dormant" not in body


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
            key="personal", label="Personal", kind="personal", cap=25,
            counts={"papers": 0}, items={"papers": []},
        ),
    )
    pdf = render_report_pdf(data)
    assert pdf[:5] == b"%PDF-"


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
        source="pivot",
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
    monkeypatch.setattr(daily_report_send, "eligible_recipients", lambda u: recipients)
    monkeypatch.setattr(daily_report_send, "_report_dir", lambda: tmp_path / "outbox")

    queued: list[str] = []

    def send_fn(user, data, path, filename):
        assert Path(path).read_bytes() == b"%PDF-fake"
        assert filename.startswith("mylo-report-")
        queued.append(user.get_username())
        return _Outcome(True)

    summary = run_daily_report_send(
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
    monkeypatch.setattr(daily_report_send, "eligible_recipients", lambda u: recipients)

    def render_fn(data):
        if data.username == "bad":
            raise ValueError("boom")
        return b"%PDF-ok"

    summary = run_daily_report_send(
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
    monkeypatch.setattr(daily_report_send, "eligible_recipients", lambda u: recipients)
    monkeypatch.setattr(daily_report_send, "_report_dir", lambda: tmp_path / "outbox")
    summary = run_daily_report_send(
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
    monkeypatch.setattr(daily_report_send, "eligible_recipients", lambda u: recipients)
    run_daily_report_send(
        compile_fn=_report_for,
        render_fn=lambda d: b"%PDF-x",
        send_fn=lambda *a: _Outcome(True),
        report_dir=str(tmp_path),
    )
    files = list(Path(tmp_path).glob("*.pdf"))
    assert len(files) == 1  # report_dir given → files are kept
