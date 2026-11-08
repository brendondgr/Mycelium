"""Fixtures for the conference collector tests.

Every fixture is a trimmed real payload, so the whole pipeline below stage 1 runs
with no network at all — the same property the smoke checklist asserts about
production.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.retrieval.collect.conferences.pipeline import (
    ConferenceConfig,
    ConferencePipeline,
)
from tools.retrieval.collect.core.rawstore import RawBundle

FIXTURES = Path(__file__).parent / "fixtures"

#: The date every recon probe was taken on, so fixture expectations are stable.
TODAY = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def bundle(source: str, records: list[dict], **meta) -> RawBundle:
    return RawBundle(
        source=source,
        run_id="20260816T000000Z",
        fetched_at="2026-08-16T00:00:00Z",
        records=records,
        meta=meta,
    )


@pytest.fixture
def ccf_venues() -> list[dict]:
    """Seven venues chosen to cover every trap the source actually contains.

    SIGMOD (4 rounds, AoE), VLDB (12 rounds, PT), AAAI (UTC-12 spelling),
    EuroVis (a deadline year that is wrong upstream), PODS (the venue nested one
    directory deeper than the rest), and both FSEs (a title collision across two
    unrelated fields).
    """
    from tools.retrieval.collect.conferences.adapters.ccf_deadlines import _load_yaml

    return _load_yaml(fixture_text("ccf_allconf_sample.yml"))


@pytest.fixture
def ccf_bundle(ccf_venues) -> RawBundle:
    return bundle("ccf_deadlines", ccf_venues)


@pytest.fixture
def config(tmp_path) -> ConferenceConfig:
    return ConferenceConfig(root=tmp_path / "collect", sources=["ccf_deadlines"])


@pytest.fixture
def pipeline(config) -> ConferencePipeline:
    return ConferencePipeline(config)


@pytest.fixture
def seeded_pipeline(pipeline, ccf_bundle) -> ConferencePipeline:
    """A pipeline with raw payloads already on disk, so parse runs offline."""
    pipeline.raw_store.write(ccf_bundle)
    return pipeline
