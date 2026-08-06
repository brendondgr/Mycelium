"""The run summary renders real numbers, stays inside Discord's limits, and
degrades to the plain notice when the analytics stage produced nothing.

Dependency-free (stdlib ``unittest``): this runs in the bare root runner
environment alongside the reporter.

    uv run python -m unittest discover -s mylo -p 'test_*.py'
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import manual_all
from mylo import analytics


def _payload(**overrides) -> dict:
    payload = {
        "generated_on": "2026-08-06",
        "headline": "Mylo ran for 12 people and 3 labs, found 240 new item(s), "
        "and wrote 1,908 recommendation(s).",
        "coverage": {"users": 12, "labs": 3, "departments": 1, "projects": 7},
        "discovery": {
            "papers": 180,
            "grants": 42,
            "fellowships": 6,
            "conferences": 12,
            "total": 240,
        },
        "recommendations": {
            "total": 1908,
            "by_category": {
                "papers": 1500,
                "grants": 300,
                "fellowships": 48,
                "conferences": 60,
            },
            "by_target": {"user": 1400, "lab": 400, "project": 108, "department": 0},
            "member_suggestions": 20,
            "member_suggestions_delivered": 11,
        },
        "llm": {
            "calls": 512,
            "failures": 4,
            "prompt_tokens": 820_000,
            "completion_tokens": 96_000,
            "total_tokens": 916_000,
            "components": [
                {
                    "component": "papers",
                    "calls": 400,
                    "failures": 3,
                    "prompt_tokens": 700_000,
                    "completion_tokens": 80_000,
                },
                {
                    "component": "briefing",
                    "calls": 112,
                    "failures": 1,
                    "prompt_tokens": 120_000,
                    "completion_tokens": 16_000,
                },
            ],
        },
        "delivery": {
            "briefings_generated": 15,
            "briefings_users": 12,
            "briefings_labs": 3,
            "briefings_fallback": 1,
            "reports_queued": 12,
            "reports_delivered": 9,
            "reports_failed": 0,
            "reports_pending": 3,
            "digests_queued": 3,
            "digests_delivered": 3,
            "digests_failed": 0,
        },
        "trend": [
            {
                "day": f"2026-08-0{index}",
                "discovered": 100 + index,
                "recommendations": 900 + index * 10,
                "llm_calls": 300,
                "total_tokens": 500_000,
            }
            for index in range(1, 7)
        ],
    }
    payload.update(overrides)
    return payload


class BarTests(unittest.TestCase):
    def test_a_nonzero_value_never_renders_as_an_empty_bar(self):
        # 1 out of 10,000 would round to zero blocks and read as "found nothing".
        rendered = analytics.bar(1, 10_000, width=18)
        self.assertIn("█", rendered)

    def test_zero_is_an_empty_bar_not_a_missing_row(self):
        self.assertNotIn("█", analytics.bar(0, 100))
        self.assertEqual(len(analytics.bar(0, 100, width=18)), 18)

    def test_peak_fills_the_width(self):
        self.assertEqual(analytics.bar(50, 50, width=10), "█" * 10)

    def test_no_data_at_all_does_not_divide_by_zero(self):
        self.assertEqual(len(analytics.bar(0, 0, width=6)), 6)


class ChartAndTableTests(unittest.TestCase):
    def test_bar_chart_aligns_labels_and_counts(self):
        chart = analytics.bar_chart([("Papers", 180), ("Grants", 42)])
        lines = chart.splitlines()
        self.assertEqual(len(lines), 2)
        # Bars start at the same column, so the chart reads as a chart.
        self.assertEqual(lines[0].index("█"), lines[1].index("█"))
        self.assertIn("180", lines[0])

    def test_table_is_column_aligned(self):
        rendered = analytics.table(
            ["Component", "Calls"], [["papers", "400"], ["briefing", "112"]]
        )
        lines = rendered.splitlines()
        self.assertEqual(len(lines), 4)  # header, rule, two rows
        self.assertTrue(all(len(line) == len(lines[0]) for line in lines))


class CodeBlockTests(unittest.TestCase):
    def test_fits_within_the_discord_field_limit(self):
        long_text = "\n".join(f"row-{index} " + "x" * 60 for index in range(200))
        block = analytics.code_block(long_text)
        self.assertLessEqual(len(block), analytics.FIELD_MAX)

    def test_truncation_is_announced_rather_than_silent(self):
        long_text = "\n".join(f"row-{index} " + "x" * 60 for index in range(200))
        block = analytics.code_block(long_text)
        self.assertIn("more", block)

    def test_short_text_is_untouched(self):
        self.assertEqual(analytics.code_block("hi"), "```\nhi\n```")


class SummaryTests(unittest.TestCase):
    def test_every_field_fits_discords_limit(self):
        for name, value in analytics.summary_fields(_payload()).items():
            text = value[0] if isinstance(value, tuple) else value
            self.assertLessEqual(len(text), analytics.FIELD_MAX, name)

    def test_body_fits_the_description_limit(self):
        body = analytics.summary_body(_payload())
        self.assertLessEqual(len(body), 4096)

    def test_the_numbers_actually_appear(self):
        fields = analytics.summary_fields(_payload())
        self.assertIn("180", fields["Discovery"][0])
        self.assertIn("12", fields["Coverage"][0])
        self.assertIn("916,000", analytics.summary_body(_payload()) + str(fields))
        self.assertIn("papers", fields["Language model"])
        self.assertIn("400", fields["Language model"])

    def test_a_zero_category_is_shown_as_zero_not_dropped(self):
        payload = _payload()
        payload["discovery"]["grants"] = 0
        fields = analytics.summary_fields(payload)
        self.assertIn("Grants", fields["Discovery"][0])
        self.assertIn("0", fields["Discovery"][0])

    def test_skipped_scrape_is_stated_in_the_body(self):
        body = analytics.summary_body(_payload(), scrape_ran=False)
        self.assertIn("skipped", body.lower())

    def test_empty_llm_ledger_says_so(self):
        payload = _payload()
        payload["llm"]["components"] = []
        self.assertIn("No language-model", analytics.summary_fields(payload)["Language model"])

    def test_malformed_payload_does_not_raise(self):
        # A truncated or half-written file must not take the summary down with it.
        for broken in ({}, {"llm": None}, {"discovery": {"papers": "many"}}):
            analytics.summary_fields(broken)
            analytics.summary_body(broken)
            analytics.attention_line(broken)


class AttentionTests(unittest.TestCase):
    def test_healthy_run_flags_nothing(self):
        payload = _payload()
        payload["llm"]["failures"] = 0
        self.assertEqual(analytics.attention_line(payload), "")

    def test_llm_failures_are_flagged_with_a_rate(self):
        line = analytics.attention_line(_payload())
        self.assertIn("LLM", line)
        self.assertIn("4", line)

    def test_a_night_that_found_nothing_is_flagged(self):
        payload = _payload()
        payload["discovery"] = {"papers": 0, "grants": 0, "total": 0}
        payload["llm"]["failures"] = 0
        self.assertIn("no new items", analytics.attention_line(payload))

    def test_undeliverable_reports_are_flagged(self):
        payload = _payload()
        payload["delivery"]["reports_failed"] = 2
        self.assertIn("undeliverable", analytics.attention_line(payload))


class ReadAnalyticsTests(unittest.TestCase):
    def test_reads_a_written_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analytics.json"
            path.write_text(json.dumps(_payload()), encoding="utf-8")
            self.assertEqual(
                analytics.read_analytics(path)["generated_on"], "2026-08-06"
            )

    def test_missing_file_is_none_not_an_exception(self):
        self.assertIsNone(analytics.read_analytics("/nonexistent/analytics.json"))

    def test_corrupt_file_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analytics.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(analytics.read_analytics(path))


class RunCompleteTests(unittest.TestCase):
    """``manual_all`` posts the rich summary, or the plain one, but always one."""

    def setUp(self) -> None:
        self.calls: list[tuple[str, str, str, dict]] = []
        patcher = mock.patch.object(
            manual_all,
            "_notify",
            lambda kind, title, body="", **kw: self.calls.append(
                (kind, title, body, kw)
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rich_summary_carries_fields_and_the_pdf(self):
        payload = _payload(pdf_path="/app/data/analytics/report.pdf")
        manual_all.report_run_complete(payload, scrape_ran=True)

        self.assertEqual(len(self.calls), 1)
        kind, title, body, kwargs = self.calls[0]
        self.assertEqual(kind, "info")
        self.assertIn("2026-08-06", title)
        self.assertIn("New items found today", body)
        self.assertEqual(kwargs["attachment"], "/app/data/analytics/report.pdf")
        self.assertIn("Language model", kwargs["fields"])
        self.assertLessEqual(len(kwargs["fields"]), 25)

    def test_missing_analytics_still_announces_the_run(self):
        manual_all.report_run_complete(None, scrape_ran=True)
        self.assertEqual(len(self.calls), 1)
        _kind, title, _body, kwargs = self.calls[0]
        self.assertEqual(title, "Daily run complete")
        self.assertIsNone(kwargs.get("attachment"))

    def test_no_pdf_means_no_attachment_key_value(self):
        manual_all.report_run_complete(_payload(), scrape_ran=True)
        self.assertIsNone(self.calls[0][3]["attachment"])

    def test_skipped_scrape_is_reported_either_way(self):
        manual_all.report_run_complete(None, scrape_ran=False)
        self.assertIn("skipped", self.calls[0][2])
        self.calls.clear()
        manual_all.report_run_complete(_payload(), scrape_ran=False)
        self.assertIn("skipped", self.calls[0][2].lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
