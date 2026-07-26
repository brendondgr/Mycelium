"""Every row of the temporary-vs-permanent table, plus the traps around it.

Pure: no database, no Django settings, no network. If this file ever needs a fixture,
the classifier has stopped being pure and the boundary has slipped.
"""

from __future__ import annotations

import pytest

from apps.integrations.services.discord_api import DiscordHTTPError
from apps.integrations.services.discord_failure import (
    Reason,
    Verdict,
    classify,
    classify_exception,
)


@pytest.mark.parametrize("status", [200, 201, 204])
def test_success_statuses_are_ok(status: int) -> None:
    result = classify(status=status)
    assert result.verdict is Verdict.OK
    assert result.ok
    assert not result.should_retry


def test_rate_limit_is_transient_and_carries_discords_own_wait() -> None:
    result = classify(status=429, retry_after=12.5)
    assert result.verdict is Verdict.TRANSIENT
    assert result.reason is Reason.RATE_LIMITED
    assert result.retry_after == 12.5  # honour it, never guess


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_are_transient(status: int) -> None:
    result = classify(status=status)
    assert result.should_retry
    assert result.reason is Reason.UPSTREAM


def test_transport_failure_with_no_http_status_is_transient() -> None:
    """status==0 is this codebase's marker for DNS/timeout/connection.

    It is the case the whole outbox exists for: the message never reached Discord,
    so retrying is both safe and correct.
    """
    result = classify(status=0)
    assert result.should_retry
    assert result.reason is Reason.NETWORK


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (403, 50007, Reason.DM_BLOCKED),  # user closed DMs / blocked the bot
        (403, 50013, Reason.NO_PERMISSION),  # an overwrite denies posting
        (403, 50001, Reason.NO_ACCESS),  # not in the guild / cannot see it
        (404, 10003, Reason.CHANNEL_GONE),
        (404, 10004, Reason.GUILD_GONE),
    ],
)
def test_known_error_codes_map_to_actionable_reasons(
    status: int, code: int, expected: Reason
) -> None:
    result = classify(status=status, error_code=code)
    assert result.verdict is Verdict.PERMANENT
    assert not result.should_retry
    assert result.reason is expected
    assert result.error_code == code


def test_the_json_code_beats_the_status() -> None:
    """A 403 alone cannot tell a closed DM from a denied channel.

    These need different messages to different people — the user's own DM setting
    versus the lab manager's channel permissions — so the code must win.
    """
    blocked = classify(status=403, error_code=50007)
    denied = classify(status=403, error_code=50013)
    assert blocked.reason is not denied.reason


def test_bare_403_does_not_accuse_the_user() -> None:
    """With no code we cannot know it was the person's DM setting. Don't imply it."""
    result = classify(status=403)
    assert result.verdict is Verdict.PERMANENT
    assert result.reason is Reason.NO_ACCESS
    assert result.reason is not Reason.DM_BLOCKED


def test_bare_404_is_a_missing_channel() -> None:
    assert classify(status=404).reason is Reason.CHANNEL_GONE


@pytest.mark.parametrize("status", [400, 401, 405, 413])
def test_other_client_errors_are_permanent_and_generic(status: int) -> None:
    result = classify(status=status)
    assert result.verdict is Verdict.PERMANENT
    assert result.reason is Reason.REJECTED


def test_missing_bot_token_is_permanent_not_a_network_blip() -> None:
    """No amount of retrying configures a token.

    discord_api raises DiscordHTTPError(0, ..., "bot token not configured"), which
    shares its status with a genuine network failure — so the body has to break the
    tie, or an unconfigured deployment would retry forever.
    """
    exc = DiscordHTTPError(0, None, "bot token not configured")
    result = classify_exception(exc)
    assert result.verdict is Verdict.PERMANENT
    assert result.reason is Reason.NOT_CONFIGURED


def test_network_exception_stays_transient() -> None:
    exc = DiscordHTTPError(0, None, "timed out")
    assert classify_exception(exc).should_retry


def test_raised_http_error_classifies_like_a_returned_one() -> None:
    """The two error surfaces of discord_api must reach the same judgment."""
    exc = DiscordHTTPError(403, 50007, "")
    assert classify_exception(exc).reason is Reason.DM_BLOCKED
