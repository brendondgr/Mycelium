"""Daily Discord report — compile, PDF render, and phased send orchestration.

The PDF is read back with ``pypdf`` (already a backend dependency) to assert the
required structure: a table of contents that points at the written report, the two
top-25 sections, and the full appendix. Compile is exercised against real
``RelevanceScore`` rows; the send flow is driven with injected seams so it needs no
live Discord.
"""

from __future__ import annotations

import tempfile
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
    compile_report_for_user,
)
from apps.content.daily_report_pdf import render_report_pdf
from apps.content.daily_report_send import run_daily_report_send
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore


# --------------------------------------------------------------------------- #
# PDF rendering (pure — no database)
# --------------------------------------------------------------------------- #
def _sample_data() -> ReportData:
    papers = [
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
            is_new=(i == 0),
        )
        for i in range(3)
    ]
    opps = [
        ReportItem(
            type="grant",
            category="grants",
            title="Big Research Grant",
            url="https://example.org/grant",
            match_percent=88,
            headline="",
            reason="Matches your funding needs.",
            source="NSF",
            deadline_date="2026-09-01",
            is_new=True,
        )
    ]
    return ReportData(
        username="tester",
        display_name="Test Person",
        generated_on="2026-07-19",
        briefing_markdown=(
            "## Papers\nThree strong papers today. **Read the first.**\n\n- One\n- Two"
        ),
        briefing_origin="llm",
        categories=["papers", "grants"],
        counts={"papers": 3, "grants": 1},
        new_counts={"papers": 1, "grants": 1},
        top_papers=papers,
        top_opportunities=opps,
        all_items={"papers": papers, "grants": opps},
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
        "Top 25 Articles",
        "Top 25 Grants, Fellowships & Conferences",
        "Everything Mylo Found",
    ):
        assert heading in text, f"missing section: {heading}"
    # An item title and the recipient reach the page.
    assert "Big Research Grant" in text
    assert "Test Person" in text


def test_toc_points_at_the_written_report_with_a_page_number() -> None:
    reader = PdfReader(BytesIO(render_report_pdf(_sample_data())))
    toc_text = reader.pages[1].extract_text()  # cover=0, TOC=1
    assert "Your Mylo Report" in toc_text
    # The TOC lists real, resolved page numbers (two-pass build), not just dots.
    assert any(ch.isdigit() for ch in toc_text)
    # The TOC does not list its own "Contents" title as an entry.
    assert toc_text.count("Your Mylo Report") == 1


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
    )
    pdf = render_report_pdf(data)
    assert pdf[:5] == b"%PDF-"


# --------------------------------------------------------------------------- #
# Compile (database)
# --------------------------------------------------------------------------- #
def _paper(user, i, *, match, rank, run_at="2026-07-19", first_seen="2026-07-10"):
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
            "rank": rank,
            "run_at": run_at,
            "first_seen": first_seen,
            "reason": f"reason {i}",
        },
    )


def _opp(user, kind, i, *, match, first_seen, deadline=""):
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
        target_user=user,
        score=match / 100.0,
        signals={
            "suggested": True,
            "match_percent": match,
            "first_seen": first_seen,
            "deadline_date": deadline,
        },
    )


@pytest.mark.django_db
def test_compile_caps_and_sorts(monkeypatch) -> None:
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
    # A new, high-match fellowship should sort ahead of an older, lower grant.
    _opp(user, "grants", 0, match=60, first_seen="2026-07-01", deadline="2026-10-01")
    _opp(
        user, "fellowships", 0, match=95,
        first_seen="2026-07-19", deadline="2026-09-01",
    )

    data = compile_report_for_user(user)

    assert data.counts == {"papers": 27, "grants": 1, "fellowships": 1}
    assert len(data.top_papers) == 25  # capped
    assert len(data.top_opportunities) == 2
    # New + higher-match fellowship first.
    assert data.top_opportunities[0].type == "fellowship"
    assert data.top_opportunities[0].is_new is True
    assert data.new_counts["fellowships"] == 1
    assert data.new_counts["grants"] == 0
    assert len(data.all_items["papers"]) == 27  # appendix holds everything


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


def test_send_flow_is_phased_and_cleans_up(monkeypatch, tmp_path) -> None:
    recipients = [_FakeUser(1, "alice"), _FakeUser(2, "bob")]
    monkeypatch.setattr(daily_report_send, "eligible_recipients", lambda u: recipients)

    made_dir = tmp_path / "run"
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(made_dir))

    sent: list[str] = []

    def send_fn(user, data, pdf_bytes, filename):
        assert pdf_bytes == b"%PDF-fake"
        assert filename.startswith("mylo-report-")
        sent.append(user.get_username())
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
    assert sorted(sent) == ["alice", "bob"]
    # The temp dir (and every PDF in it) is deleted afterwards.
    assert not made_dir.exists()


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


def test_unreachable_send_is_counted_not_sent(monkeypatch) -> None:
    recipients = [_FakeUser(1, "u")]
    monkeypatch.setattr(daily_report_send, "eligible_recipients", lambda u: recipients)
    summary = run_daily_report_send(
        compile_fn=_report_for,
        render_fn=lambda d: b"%PDF-x",
        send_fn=lambda *a: _Outcome(False),
    )
    assert summary.sent == 0
    assert summary.unreachable == 1


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
