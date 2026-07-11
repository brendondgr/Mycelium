"""Unit tests for the Mylo error-reporting seam.

Dependency-free (stdlib ``unittest``): the reporter runs in the bare root runner
environment, so its tests must too. A recording transport stands in for the
network — no live Discord calls.

    uv run python -m unittest discover -s mylo -p 'test_*.py'
"""

from __future__ import annotations

import json
import unittest

from mylo.config import MyloConfig
from mylo.reporting import Severity, report, report_error, report_warning


def _enabled_config() -> MyloConfig:
    return MyloConfig(token="tok_123", error_channel_id=42)


class RecordingTransport:
    """Captures the last POST and returns a canned status code."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, headers: dict, body: bytes) -> int:
        self.calls.append((url, headers, json.loads(body.decode("utf-8"))))
        return self.status


class ReportPayloadTests(unittest.TestCase):
    def test_posts_to_the_configured_channel_with_bot_auth(self) -> None:
        transport = RecordingTransport()
        ok = report(
            "Pivot login needed",
            "No saved session on this host.",
            severity=Severity.ERROR,
            stage="scrape",
            action="Run `uv run pivot.py login`.",
            config=_enabled_config(),
            transport=transport,
        )
        self.assertTrue(ok)
        self.assertEqual(len(transport.calls), 1)
        url, headers, payload = transport.calls[0]
        self.assertIn("/channels/42/messages", url)
        self.assertEqual(headers["Authorization"], "Bot tok_123")

        embed = payload["embeds"][0]
        self.assertIn("Pivot login needed", embed["title"])
        self.assertEqual(embed["description"], "No saved session on this host.")
        self.assertEqual(embed["color"], Severity.ERROR.color)
        # Never allowed to ping the server from a status post.
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_stage_and_action_become_fields(self) -> None:
        transport = RecordingTransport()
        report(
            "Stage failed",
            stage="run_daily_opportunities",
            action="Check the backend logs.",
            fields={"Exit code": "1"},
            config=_enabled_config(),
            transport=transport,
        )
        embed = transport.calls[0][2]["embeds"][0]
        names = {f["name"]: f["value"] for f in embed["fields"]}
        self.assertEqual(names["Stage"], "run_daily_opportunities")
        self.assertEqual(names["Action needed"], "Check the backend logs.")
        self.assertEqual(names["Exit code"], "1")

    def test_footer_carries_the_hostname(self) -> None:
        transport = RecordingTransport()
        report("hi", config=_enabled_config(), transport=transport)
        embed = transport.calls[0][2]["embeds"][0]
        self.assertTrue(embed["footer"]["text"].startswith("Mylo · "))

    def test_long_body_is_truncated_to_the_embed_limit(self) -> None:
        transport = RecordingTransport()
        report("big", "x" * 9000, config=_enabled_config(), transport=transport)
        embed = transport.calls[0][2]["embeds"][0]
        self.assertLessEqual(len(embed["description"]), 4096)
        self.assertTrue(embed["description"].endswith("…"))

    def test_severity_wrappers_set_colour(self) -> None:
        transport = RecordingTransport()
        report_warning("careful", config=_enabled_config(), transport=transport)
        self.assertEqual(
            transport.calls[0][2]["embeds"][0]["color"], Severity.WARN.color
        )


class ReportResilienceTests(unittest.TestCase):
    def test_missing_credentials_is_a_no_op_returning_false(self) -> None:
        transport = RecordingTransport()
        disabled = MyloConfig(token="", error_channel_id=None)
        ok = report("nope", config=disabled, transport=transport)
        self.assertFalse(ok)
        self.assertEqual(transport.calls, [])  # transport never invoked

    def test_non_2xx_response_returns_false(self) -> None:
        transport = RecordingTransport(status=403)
        ok = report_error("denied", config=_enabled_config(), transport=transport)
        self.assertFalse(ok)

    def test_transport_exception_is_swallowed(self) -> None:
        def boom(url: str, headers: dict, body: bytes) -> int:
            raise ConnectionError("network down")

        ok = report_error("x", config=_enabled_config(), transport=boom)
        self.assertFalse(ok)  # did not raise


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
