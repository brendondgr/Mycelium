"""The instance's settings -> the engine's credentials, sources and health."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from tools.fulltext import config, health
from tools.fulltext.engine import sources as S
from tools.fulltext.tool import DEFAULT_SOURCES

NO_KEYS = dict(
    ELSEVIER_API_KEY="",
    ELSEVIER_INST_TOKEN="",
    SPRINGER_API_KEY="",
    WILEY_TDM_TOKEN="",
    CORE_API_KEY="",
)


def test_declared_default_order_is_the_engines():
    assert DEFAULT_SOURCES == S.DEFAULT_ORDER


@override_settings(
    FULLTEXT_CONTACT_EMAIL="",
    SCRAPER_CONTACT_EMAIL="scan@fsu.edu",
    PUBMED_API_KEY="ncbi",
    OPENALEX_API_KEY="oa",
    WILEY_TDM_TOKEN="w",
)
def test_credentials_reuse_the_scan_keys_and_contact_address():
    creds = config.credentials()
    assert creds["CONTACT_EMAIL"] == "scan@fsu.edu"
    assert creds["PUBMED_API_KEY"] == "ncbi" and creds["OPEN_ALEX_API_KEY"] == "oa"
    assert creds["WILEY_TDM_TOKEN"] == "w"


@override_settings(
    FULLTEXT_CONTACT_EMAIL="lab@fsu.edu", SCRAPER_CONTACT_EMAIL="scan@fsu.edu"
)
def test_the_tools_own_contact_address_wins():
    assert config.contact_email() == "lab@fsu.edu"


@override_settings(FULLTEXT_CONTACT_EMAIL="lab@fsu.edu", **NO_KEYS)
def test_without_keys_only_the_publisher_apis_are_off():
    live = {s["source"]: s["available"] for s in config.engine().sources()}
    assert {s for s, on in live.items() if not on} == {"elsevier", "springer", "wiley"}


@override_settings(FULLTEXT_SOURCES=["pmc", "scihub"])
def test_an_unknown_source_fails_the_health_check():
    with pytest.raises(RuntimeError, match="scihub"):
        health.check()


@override_settings(FULLTEXT_SOURCES=["arxiv", "pmc"])
def test_the_configured_order_is_used():
    assert config.engine().order == ["arxiv", "pmc"]
    health.check()


def test_data_lives_under_the_repository_not_the_working_directory():
    assert config.data_root().parts[-2:] == ("data", "fulltext")
    assert config.data_root().is_absolute()


@override_settings(FULLTEXT_CONTACT_EMAIL="lab@fsu.edu", **NO_KEYS)
def test_sources_command_lists_each_source_without_the_network():
    out = StringIO()
    call_command("fulltext_sources", stdout=out)
    text = out.getvalue()
    assert "contact email: lab@fsu.edu" in text
    assert "missing ELSEVIER_API_KEY" in text
    assert "arxiv" in text
