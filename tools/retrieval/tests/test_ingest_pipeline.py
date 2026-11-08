"""End-to-end scan tests — fully offline via injected search_fn + embedder."""

import pytest

from tools.retrieval import ingest
from tools.retrieval.ingest import scan
from tools.retrieval.models import ContentItem
from tools.retrieval.sources.record import Record


def _record(source, source_id, **kwargs):
    return Record(source=source, source_id=source_id, **kwargs)


def _search(records):
    """A search_fn that returns a fixed record list, ignoring queries/window."""

    def _fn(queries, window, sources):
        return list(records)

    return _fn


def _fake_embedder(texts):
    # Deterministic, dependency-free stand-in for fastembed.
    return [[float(len(t)), 1.0, 2.0] for t in texts]


@pytest.mark.django_db
def test_scan_emits_verbose_log_and_timings():
    records = [
        _record("OpenAlex", "W1", title="A", doi="10.1/a", abstract="x"),
        _record("PubMed", "2", title="B", pmid="2"),
    ]
    lines: list[str] = []
    summary = scan(
        ["q"], search_fn=_search(records), embedder=_fake_embedder, log=lines.append
    )

    joined = "\n".join(lines)
    assert "scan start" in joined
    assert "search done" in joined
    assert "cross-source dedup" in joined
    assert "embed:" in joined
    assert "tally:" in joined
    assert {"search", "dedup", "against_store", "embed", "upsert", "total"} <= set(
        summary.timings
    )


@pytest.mark.django_db
def test_scan_ingests_new_papers_with_embeddings():
    records = [
        _record(
            "OpenAlex", "W1", title="Mycelial Networks", doi="10.1/AAA", abstract="abc"
        ),
        _record("PubMed", "123", title="Quantum Cybersecurity", pmid="123"),
    ]
    summary = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)

    assert summary.raw == 2
    assert summary.unique == 2
    assert summary.new == 2
    assert summary.embedded == 2
    assert summary.upserted == 2
    assert summary.embedding_skipped_reason is None

    items = {i.external_id: i for i in ContentItem.objects.all()}
    assert set(items) == {"doi:10.1/aaa", "pmid:123"}
    paper = items["doi:10.1/aaa"]
    assert paper.type == ContentItem.Type.PAPER
    assert paper.source == "OpenAlex"
    assert paper.embedding is not None
    assert paper.metadata["title"] == "Mycelial Networks"
    assert paper.metadata["queries"] == ["q"]


@pytest.mark.django_db
def test_cross_source_duplicates_collapse_to_one_row():
    # Same DOI from two sources → merged into a single canonical record.
    records = [
        _record("OpenAlex", "W1", title="Shared Paper", doi="10.1/dup"),
        _record(
            "SemanticScholar", "S1", title="Shared Paper", doi="10.1/DUP", abstract="x"
        ),
    ]
    summary = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)

    assert summary.raw == 2
    assert summary.unique == 1
    assert summary.upserted == 1
    assert ContentItem.objects.count() == 1
    item = ContentItem.objects.get()
    # Merge filled the missing abstract and recorded both sources.
    assert item.metadata["abstract"] == "x"
    assert set(item.metadata["sources"]) == {"OpenAlex", "SemanticScholar"}


@pytest.mark.django_db
def test_already_stored_papers_are_skipped_not_reembedded():
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="OpenAlex", external_id="doi:10.1/known"
    )
    records = [
        _record("OpenAlex", "W1", title="Known", doi="10.1/known"),
        _record("OpenAlex", "W2", title="Novel", doi="10.1/novel"),
    ]
    summary = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)

    assert summary.unique == 2
    assert summary.already_present == 1
    assert summary.new == 1
    assert summary.embedded == 1
    assert ContentItem.objects.count() == 2


@pytest.mark.django_db
def test_stored_paper_matched_by_shared_arxiv_across_runs():
    # A previous run stored the OpenAlex copy under its DOI canonical id, with the
    # arXiv id recorded in metadata. A later run sees only the SemanticScholar copy
    # (no DOI, different canonical id) — it must resolve to the stored row via the
    # shared arXiv id instead of inserting a second row.
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="OpenAlex",
        external_id="doi:10.48550/arxiv.2607.12764",
        metadata={
            "title": "EvoGraph-R1",
            "doi": "10.48550/arxiv.2607.12764",
            "arxiv": "2607.12764",
            "sources": ["OpenAlex"],
        },
    )
    records = [
        _record(
            "SemanticScholar", "S1", title="EvoGraph-R1", arxiv="2607.12764",
            abstract="self-evolving hypergraphs",
        ),
    ]
    summary = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)

    assert summary.unique == 1
    assert summary.already_present == 1
    assert summary.new == 0
    assert ContentItem.objects.count() == 1
    # The stored row absorbed the second source and back-filled the abstract.
    item = ContentItem.objects.get()
    assert set(item.metadata["sources"]) == {"OpenAlex", "SemanticScholar"}
    assert item.metadata["abstract"] == "self-evolving hypergraphs"


@pytest.mark.django_db
def test_stored_paper_matched_by_shared_pmid_across_runs():
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="PubMed",
        external_id="pmid:999",
        metadata={"title": "Shared", "pmid": "999", "sources": ["PubMed"]},
    )
    # OpenAlex copy carries the same PMID but a DOI-based canonical id.
    records = [_record("OpenAlex", "W9", title="Shared", doi="10.1/x", pmid="999")]
    summary = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)

    assert summary.new == 0
    assert summary.already_present == 1
    assert ContentItem.objects.count() == 1


@pytest.mark.django_db
def test_scan_is_idempotent():
    records = [_record("OpenAlex", "W1", title="Once", doi="10.1/once")]
    first = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)
    second = scan(["q"], search_fn=_search(records), embedder=_fake_embedder)

    assert first.new == 1
    assert second.new == 0
    assert second.upserted == 0
    assert ContentItem.objects.count() == 1


@pytest.mark.django_db
def test_no_embed_stores_rows_with_null_embedding():
    records = [_record("OpenAlex", "W1", title="No Vec", doi="10.1/novec")]
    summary = scan(
        ["q"], search_fn=_search(records), embed=False, embedder=_fake_embedder
    )

    assert summary.new == 1
    assert summary.embedded == 0
    assert summary.upserted == 1
    assert ContentItem.objects.get().embedding is None


@pytest.mark.django_db
def test_missing_embedder_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(ingest, "get_default_embedder", lambda *a, **k: None)
    records = [_record("OpenAlex", "W1", title="Still Stored", doi="10.1/still")]
    # embed=True (default), no embedder injected → falls back to get_default_embedder
    summary = scan(["q"], search_fn=_search(records))

    assert summary.new == 1
    assert summary.embedded == 0
    assert summary.upserted == 1
    assert "fastembed" in summary.embedding_skipped_reason
    assert ContentItem.objects.get().embedding is None


@pytest.mark.django_db
def test_empty_queries_short_circuits():
    summary = scan([], search_fn=_search([_record("OpenAlex", "W1", title="x")]))
    assert summary.raw == 0
    assert summary.upserted == 0
    assert ContentItem.objects.count() == 0


@pytest.mark.django_db
def test_source_selection_is_passed_through():
    seen = {}

    def _fn(queries, window, sources):
        seen["sources"] = sources
        return []

    scan(["q"], sources=["openalex", "pubmed"], search_fn=_fn)
    assert seen["sources"] == ["openalex", "pubmed"]
