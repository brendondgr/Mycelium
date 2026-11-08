"""Tests for the scan_literature management command (no network)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tools.retrieval.ingest import ScanSummary
from tools.retrieval.management.commands import scan_literature as cmd


def _fake_summary(**over):
    base = dict(queries=["q"], window="2026-04-29 → 2026-07-29", sources=["openalex"])
    base.update(over)
    return ScanSummary(**base)


def test_command_requires_a_query():
    with pytest.raises(CommandError):
        call_command("scan_literature")


def test_command_runs_inline_and_forwards_args(monkeypatch):
    captured = {}

    def fake_scan(queries, **kwargs):
        captured["queries"] = queries
        captured["kwargs"] = kwargs
        return _fake_summary(new=3, embedded=3, upserted=3)

    monkeypatch.setattr(cmd, "scan", fake_scan)
    out = StringIO()
    call_command(
        "scan_literature",
        query=["agentic ai", "quantum"],
        months_back=2,
        months_forward=1,
        source=["openalex"],
        stdout=out,
    )

    assert captured["queries"] == ["agentic ai", "quantum"]
    assert captured["kwargs"]["months_back"] == 2
    assert captured["kwargs"]["months_forward"] == 1
    assert captured["kwargs"]["sources"] == ["openalex"]
    assert captured["kwargs"]["embed"] is True
    assert "3 new" in out.getvalue()


def test_command_no_embed_flag(monkeypatch):
    captured = {}

    def fake_scan(queries, **kwargs):
        captured["embed"] = kwargs["embed"]
        return _fake_summary()

    monkeypatch.setattr(cmd, "scan", fake_scan)
    call_command("scan_literature", query=["x"], no_embed=True, stdout=StringIO())
    assert captured["embed"] is False


def test_command_async_dispatches_task(monkeypatch):
    sent = {}

    class _Result:
        id = "task-123"

    def fake_delay(queries, **kwargs):
        sent["queries"] = queries
        sent["kwargs"] = kwargs
        return _Result()

    import tools.retrieval.tasks as tasks

    monkeypatch.setattr(tasks.scan_literature, "delay", fake_delay)
    out = StringIO()
    call_command("scan_literature", query=["x"], run_async=True, stdout=out)

    assert sent["queries"] == ["x"]
    assert "task-123" in out.getvalue()
