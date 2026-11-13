"""A link that leaves the building must never point at the operator's laptop.

The regression these pin: `PUBLIC_HOSTNAME` was left blank on a publicly-served
stack, so `PUBLIC_BASE_URL` stayed on its localhost default and every lab's daily
Discord post carried `http://localhost:11050/app/daily`. Nothing objected — the
value was well-formed, just useless to everyone but the operator. With no public
origin known at all, the answer is no link, not someone else's domain.
"""

from __future__ import annotations

import pytest

from config import settings as config_settings
from config.settings import is_loopback_origin, outbound_base_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11050",
        "http://LOCALHOST:11050/app/daily",
        "http://127.0.0.1:8000",
        "https://0.0.0.0",
        "http://[::1]:11050",
        "localhost:11050",
    ],
)
def test_loopback_origins_are_recognised(url: str) -> None:
    assert is_loopback_origin(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://lab.example.edu",
        "https://mycelium.example.com/app",
        "http://backend:8000",
        "",
    ],
)
def test_public_origins_are_left_alone(url: str) -> None:
    assert is_loopback_origin(url) is False


def test_a_loopback_origin_is_replaced_with_the_fallback(monkeypatch) -> None:
    monkeypatch.setattr(config_settings, "PUBLIC_FALLBACK_HOSTNAME", "lab.example.edu")
    assert outbound_base_url("http://localhost:11050") == "https://lab.example.edu"


def test_without_a_fallback_a_loopback_origin_becomes_no_origin(monkeypatch) -> None:
    monkeypatch.setattr(config_settings, "PUBLIC_FALLBACK_HOSTNAME", "")
    assert outbound_base_url("http://localhost:11050") == ""
    assert outbound_base_url("") == ""


def test_a_real_origin_wins_outright() -> None:
    """An explicitly configured origin is never second-guessed."""
    assert outbound_base_url("https://lab.example.edu/") == "https://lab.example.edu"


def test_the_digest_link_is_not_localhost(settings) -> None:
    """The end the bug was actually observed at."""
    assert not is_loopback_origin(settings.DISCORD_APP_BASE_URL)

