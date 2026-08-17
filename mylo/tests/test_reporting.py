"""Unit tests for the Mylo error-reporting seam.

Dependency-free (stdlib ``unittest``): the reporter runs in the bare root runner
environment, so its tests must too. A recording transport stands in for the
network — no live Discord calls.

    uv run python -m unittest discover -s mylo -p 'test_*.py'
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
            "Fellowship scrape failed",
            "The Illinois fellowship scrape did not complete on this host.",
            severity=Severity.ERROR,
            stage="scrape",
            action="Check the Playwright/Chromium install.",
            config=_enabled_config(),
            transport=transport,
        )
        self.assertTrue(ok)
        self.assertEqual(len(transport.calls), 1)
        url, headers, payload = transport.calls[0]
        self.assertIn("/channels/42/messages", url)
        self.assertEqual(headers["Authorization"], "Bot tok_123")

        embed = payload["embeds"][0]
        self.assertIn("Fellowship scrape failed", embed["title"])
        self.assertEqual(
            embed["description"],
            "The Illinois fellowship scrape did not complete on this host.",
        )
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


class RawRecordingTransport:
    """Captures the raw bytes, so a multipart body can be inspected as sent."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, dict, bytes]] = []

    def __call__(self, url: str, headers: dict, body: bytes) -> int:
        self.calls.append((url, headers, body))
        return self.status


class InlineFieldTests(unittest.TestCase):
    def test_a_value_pair_marks_the_field_inline(self) -> None:
        transport = RecordingTransport()
        report(
            "summary",
            fields={"Coverage": ("12 people", True), "Detail": "full width"},
            config=_enabled_config(),
            transport=transport,
        )
        fields = {
            f["name"]: f for f in transport.calls[0][2]["embeds"][0]["fields"]
        }
        self.assertTrue(fields["Coverage"]["inline"])
        self.assertEqual(fields["Coverage"]["value"], "12 people")
        self.assertFalse(fields["Detail"]["inline"])

    def test_more_than_25_fields_are_clamped(self) -> None:
        transport = RecordingTransport()
        report(
            "summary",
            fields={f"f{index}": str(index) for index in range(40)},
            config=_enabled_config(),
            transport=transport,
        )
        self.assertEqual(len(transport.calls[0][2]["embeds"][0]["fields"]), 25)


class AttachmentTests(unittest.TestCase):
    def _pdf(self, directory: str, size: int = 1024) -> str:
        path = Path(directory) / "run-analytics.pdf"
        path.write_bytes(b"%PDF-1.4\n" + b"0" * size)
        return str(path)

    def test_attachment_is_sent_as_multipart_with_payload_json(self) -> None:
        transport = RawRecordingTransport()
        with tempfile.TemporaryDirectory() as tmp:
            ok = report(
                "Daily run complete",
                "all good",
                severity=Severity.INFO,
                attachment=self._pdf(tmp),
                config=_enabled_config(),
                transport=transport,
            )
        self.assertTrue(ok)
        _url, headers, body = transport.calls[0]
        self.assertTrue(headers["Content-Type"].startswith("multipart/form-data"))
        self.assertIn(b'name="payload_json"', body)
        self.assertIn(b'name="files[0]"', body)
        self.assertIn(b'filename="run-analytics.pdf"', body)
        self.assertIn(b"application/pdf", body)
        self.assertIn(b"%PDF-1.4", body)
        # The boundary in the header must be the one used in the body.
        boundary = headers["Content-Type"].split("boundary=")[1]
        self.assertIn(boundary.encode(), body)
        self.assertTrue(body.rstrip().endswith(f"--{boundary}--".encode()))

    def test_embed_still_travels_with_the_file(self) -> None:
        transport = RawRecordingTransport()
        with tempfile.TemporaryDirectory() as tmp:
            report(
                "Daily run complete",
                "all good",
                attachment=self._pdf(tmp),
                config=_enabled_config(),
                transport=transport,
            )
        body = transport.calls[0][2]
        start = body.index(b"{")
        payload = json.loads(body[start : body.index(b"\r\n--", start)].decode())
        self.assertIn("Daily run complete", payload["embeds"][0]["title"])

    def test_missing_file_posts_the_message_without_it(self) -> None:
        transport = RawRecordingTransport()
        ok = report(
            "Daily run complete",
            attachment="/nonexistent/report.pdf",
            config=_enabled_config(),
            transport=transport,
        )
        self.assertTrue(ok)  # the summary is worth more than the file
        headers = transport.calls[0][1]
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_oversize_file_is_dropped_not_rejected_by_discord(self) -> None:
        transport = RawRecordingTransport()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.pdf"
            path.write_bytes(b"0" * (9 * 1024 * 1024))
            ok = report(
                "Daily run complete",
                attachment=str(path),
                config=_enabled_config(),
                transport=transport,
            )
        self.assertTrue(ok)
        self.assertEqual(transport.calls[0][1]["Content-Type"], "application/json")


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
