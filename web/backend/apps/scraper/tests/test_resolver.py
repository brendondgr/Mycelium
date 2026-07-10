"""Unit tests for the DOI/arXiv/URL resolver — no live network.

Every network call goes through the single ``resolver._get_text`` choke
point, so each test patches that (never the real ``urllib``). The embedder is
likewise patched at ``resolver.FastEmbedEmbedder`` so the suite never touches
fastembed.
"""

import json
from unittest.mock import patch

import pytest

from apps.content.models import ContentItem
from apps.scraper import resolver
from apps.scraper.resolver import ResolveError, resolve_external

ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <updated>2024-01-16T00:00:00Z</updated>
    <published>2024-01-15T18:00:00Z</published>
    <title>Mycelial Networks for Distributed Computing</title>
    <summary>
      We present a novel approach to distributed computing inspired by fungal networks.
    </summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
  </entry>
</feed>
"""

ARXIV_ATOM_NO_MATCH = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/api/errors#incorrect_id_format_for_9999.99999</id>
    <title>Error</title>
    <summary>incorrect id format</summary>
  </entry>
</feed>
"""


def _crossref_payload(*, abstract=None, doi="10.1038/s41586-021-03819-2"):
    return json.dumps({
        "status": "ok",
        "message": {
            "title": ["Fungal Computing Substrates"],
            "abstract": abstract,
            "author": [
                {"given": "Ada", "family": "Lovelace"},
                {"given": "Alan", "family": "Turing"},
            ],
            "container-title": ["Nature"],
            "published": {"date-parts": [[2021, 6, 1]]},
            "DOI": doi,
        },
    })


def _dispatch(responses: dict[str, str]):
    """A ``_get_text`` stand-in that routes by substring match on the URL."""

    def _fn(url, **kwargs):
        for needle, body in responses.items():
            if needle in url:
                return body
        raise AssertionError(f"unexpected URL in test: {url}")

    return _fn


def _fake_embedder_cls():
    """A stand-in for FastEmbedEmbedder: instantiating it returns a callable
    that maps each text to a fixed 384-length vector, mirroring the real
    (normalized) fastembed output shape without importing fastembed."""

    def _embed(texts):
        return [[0.01] * 384 for _ in texts]

    return _embed


# --------------------------------------------------------------------------- #
# Identifier detection.
# --------------------------------------------------------------------------- #


def test_detect_arxiv_url():
    assert resolver._detect("https://arxiv.org/abs/2401.12345") == (
        "arxiv",
        "2401.12345",
    )


def test_detect_arxiv_pdf_url_strips_version_and_extension():
    assert resolver._detect("arxiv.org/pdf/2401.12345v2.pdf") == (
        "arxiv",
        "2401.12345",
    )


def test_detect_bare_arxiv_id():
    assert resolver._detect("2401.12345") == ("arxiv", "2401.12345")
    assert resolver._detect("  2401.12345v3  ") == ("arxiv", "2401.12345")


def test_detect_doi():
    assert resolver._detect("10.1038/s41586-021-03819-2") == (
        "doi",
        "10.1038/s41586-021-03819-2",
    )


def test_detect_doi_url():
    assert resolver._detect("https://doi.org/10.1038/S41586-021-03819-2") == (
        "doi",
        "10.1038/s41586-021-03819-2",
    )


def test_detect_garbage_raises():
    with pytest.raises(ResolveError):
        resolver._detect("this is not an identifier at all")


def test_detect_empty_raises():
    with pytest.raises(ResolveError):
        resolver._detect("   ")


# --------------------------------------------------------------------------- #
# arXiv resolution + dedup.
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_bare_arxiv_id_resolves_and_creates_content_item():
    arxiv_get_text = _dispatch({"export.arxiv.org": ARXIV_ATOM})
    with (
        patch.object(resolver, "_get_text", side_effect=arxiv_get_text) as get_text,
        patch.object(
            resolver, "FastEmbedEmbedder", side_effect=_fake_embedder_cls
        ) as embedder_cls,
    ):
        result = resolve_external("2401.12345")

    assert result.created is True
    assert result.embed_status == "ok"
    assert result.content_item.source == "arxiv"
    assert result.content_item.external_id == "2401.12345"
    assert result.content_item.type == ContentItem.Type.PAPER
    assert result.content_item.source_url == "https://arxiv.org/abs/2401.12345"
    assert result.content_item.embedding is not None

    meta = result.content_item.metadata
    for key in (
        "title", "abstract", "authors", "first_author", "year",
        "publication_date", "venue", "doi", "pmid", "pmcid", "arxiv",
        "pdf_url", "sources", "primary_source",
    ):
        assert key in meta
    assert meta["title"] == "Mycelial Networks for Distributed Computing"
    assert "fungal networks" in meta["abstract"]
    assert meta["authors"] == ["Jane Doe", "John Smith"]
    assert meta["arxiv"] == "2401.12345"
    assert meta["primary_source"] == "arxiv"
    assert meta["year"] == 2024

    assert ContentItem.objects.count() == 1
    assert get_text.call_count == 1
    assert embedder_cls.call_count == 1


@pytest.mark.django_db
def test_resubmitting_same_arxiv_id_dedups_without_reembedding():
    arxiv_get_text = _dispatch({"export.arxiv.org": ARXIV_ATOM})
    with (
        patch.object(resolver, "_get_text", side_effect=arxiv_get_text) as get_text,
        patch.object(
            resolver, "FastEmbedEmbedder", side_effect=_fake_embedder_cls
        ) as embedder_cls,
    ):
        first = resolve_external("https://arxiv.org/abs/2401.12345")
        second = resolve_external("2401.12345")

    assert first.created is True
    assert second.created is False
    assert first.content_item.pk == second.content_item.pk
    assert ContentItem.objects.count() == 1
    # Only the first call should have hit the network or the embedder.
    assert get_text.call_count == 1
    assert embedder_cls.call_count == 1


@pytest.mark.django_db
def test_unknown_arxiv_id_raises_resolve_error():
    no_match_get_text = _dispatch({"export.arxiv.org": ARXIV_ATOM_NO_MATCH})
    with patch.object(resolver, "_get_text", side_effect=no_match_get_text):
        with pytest.raises(ResolveError):
            resolve_external("9999.99999")
    assert ContentItem.objects.count() == 0


# --------------------------------------------------------------------------- #
# DOI / Crossref resolution.
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_doi_resolves_via_crossref():
    payload = _crossref_payload(abstract="<jats:p>Spores compute quietly.</jats:p>")
    crossref_get_text = _dispatch({"api.crossref.org": payload})
    with (
        patch.object(resolver, "_get_text", side_effect=crossref_get_text) as get_text,
        patch.object(resolver, "FastEmbedEmbedder", side_effect=_fake_embedder_cls),
    ):
        result = resolve_external("10.1038/s41586-021-03819-2")

    assert result.created is True
    assert result.embed_status == "ok"
    assert result.content_item.source == "crossref"
    assert result.content_item.external_id == "10.1038/s41586-021-03819-2"
    assert (
        result.content_item.source_url == "https://doi.org/10.1038/s41586-021-03819-2"
    )

    meta = result.content_item.metadata
    assert meta["title"] == "Fungal Computing Substrates"
    # JATS tags stripped from the abstract.
    assert meta["abstract"] == "Spores compute quietly."
    assert meta["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert meta["venue"] == "Nature"
    assert meta["year"] == 2021
    assert meta["doi"] == "10.1038/s41586-021-03819-2"
    assert get_text.call_count == 1  # no OpenAlex enrichment needed


@pytest.mark.django_db
def test_doi_url_resolves_to_same_row_as_bare_doi():
    payload = _crossref_payload(abstract="Text.")
    crossref_get_text = _dispatch({"api.crossref.org": payload})
    with (
        patch.object(resolver, "_get_text", side_effect=crossref_get_text),
        patch.object(resolver, "FastEmbedEmbedder", side_effect=_fake_embedder_cls),
    ):
        resolve_external("https://doi.org/10.1038/s41586-021-03819-2")
    assert ContentItem.objects.count() == 1
    assert ContentItem.objects.get().external_id == "10.1038/s41586-021-03819-2"


# --------------------------------------------------------------------------- #
# No-abstract path.
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_no_abstract_sets_embed_status_and_leaves_embedding_null():
    payload = _crossref_payload(abstract=None)
    with (
        patch.object(
            resolver,
            "_get_text",
            side_effect=_dispatch({
                "api.crossref.org": payload,
                "api.openalex.org": json.dumps({"abstract_inverted_index": None}),
            }),
        ),
        patch.object(
            resolver, "FastEmbedEmbedder", side_effect=_fake_embedder_cls
        ) as embedder_cls,
    ):
        result = resolve_external("10.1038/s41586-021-03819-2")

    assert result.created is True
    assert result.embed_status == "no_abstract"
    assert result.content_item.embedding is None
    assert result.content_item.metadata["abstract"] == ""
    # No abstract to embed, so the embedder should never even be constructed.
    assert embedder_cls.call_count == 0


# --------------------------------------------------------------------------- #
# Garbage input.
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_garbage_string_raises_resolve_error():
    with pytest.raises(ResolveError):
        resolve_external("definitely not a paper reference")
    assert ContentItem.objects.count() == 0
