"""The start-up refusals and the HTTPS-driven security settings.

Two mistakes are easy to ship and expensive once public: DEBUG on a public
hostname, and a secret key anyone can read in the repository. Django must
refuse to start with either — outside the test suite, which runs with whatever
(or no) `.env` the checkout has. The subprocess tests import the real settings
module without pytest loaded, the way gunicorn and `manage.py` do.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from config.settings import startup_problems

BACKEND = Path(__file__).resolve().parents[2]
GOOD_KEY = "k" * 20 + "-not-a-placeholder-0123456789abcdef"


def test_debug_on_a_public_hostname_is_refused() -> None:
    problems = startup_problems(
        debug=True, public_hostname="lab.example.edu", secret_key=GOOD_KEY
    )
    assert len(problems) == 1 and "DJANGO_DEBUG" in problems[0]


@pytest.mark.parametrize(
    "key", ["", "   ", "change-me", "CHANGE-ME", "django-insecure-local-dev-only"]
)
def test_a_placeholder_secret_key_is_refused_with_debug_off(key: str) -> None:
    problems = startup_problems(debug=False, public_hostname="", secret_key=key)
    assert len(problems) == 1 and "DJANGO_SECRET_KEY" in problems[0]


def test_local_development_may_keep_a_throwaway_key() -> None:
    assert startup_problems(debug=True, public_hostname="", secret_key="") == []


def test_a_real_key_without_debug_starts() -> None:
    problems = startup_problems(
        debug=False, public_hostname="lab.example.edu", secret_key=GOOD_KEY
    )
    assert problems == []


def _import_settings(**env: str) -> subprocess.CompletedProcess:
    """Import config.settings in a fresh interpreter, with no pytest loaded."""
    environ = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "PUBLIC_", "PYTEST"))
    }
    # The checkout's own .env is read setdefault-style, so explicit values
    # here win over it.
    environ.update({
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_DEBUG": "False",
        "PUBLIC_HOSTNAME": "",
        **env,
    })
    code = (
        "from django.conf import settings\n"
        "print(settings.SESSION_COOKIE_SECURE, settings.SECURE_HSTS_SECONDS,"
        " ','.join(settings.CSRF_TRUSTED_ORIGINS))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=environ,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_settings_refuse_debug_with_a_public_hostname() -> None:
    result = _import_settings(
        DJANGO_DEBUG="True",
        PUBLIC_HOSTNAME="lab.example.edu",
        DJANGO_SECRET_KEY=GOOD_KEY,
    )
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "PUBLIC_HOSTNAME" in result.stderr


def test_settings_refuse_a_placeholder_key_outside_tests() -> None:
    result = _import_settings(DJANGO_SECRET_KEY="change-me")
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_a_public_hostname_turns_on_https_settings_and_drops_loopback_origins() -> None:
    result = _import_settings(
        DJANGO_SECRET_KEY=GOOD_KEY,
        PUBLIC_HOSTNAME="lab.example.edu",
        DJANGO_CSRF_TRUSTED_ORIGINS="http://localhost:11050,https://lab.example.edu",
    )
    assert result.returncode == 0, result.stderr
    secure, hsts, origins = result.stdout.split()
    assert secure == "True"
    assert int(hsts) >= 31536000
    assert origins == "https://lab.example.edu"


def test_a_local_instance_keeps_plain_http_cookies() -> None:
    result = _import_settings(DJANGO_SECRET_KEY=GOOD_KEY)
    assert result.returncode == 0, result.stderr
    secure, hsts, _origins = result.stdout.split()
    assert secure == "False"
    assert hsts == "0"
