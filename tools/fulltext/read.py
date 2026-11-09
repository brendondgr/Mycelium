"""The fulltext read door: what other tools and the platform may read.

Every function takes a corpus ``ContentItem`` or a plain ``ids`` dict
(``{"doi": …, "pmid": …, "pmcid": …, "arxiv": …}``) and returns plain values,
never querysets. Nothing here fetches: to get a paper that is not stored yet,
call :func:`tools.fulltext.service.request`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import store
from .models import FulltextDocument, FulltextRequest


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    doi: str
    pmid: str
    pmcid: str
    arxiv_id: str
    source: str
    source_url: str
    licensed: bool
    chars: int
    markdown_path: Path
    original_path: Path | None
    original_kind: str
    content_item_id: str | None
    fetched_at: datetime


def _ids(item_or_ids) -> dict:
    if isinstance(item_or_ids, dict):
        return item_or_ids
    md = getattr(item_or_ids, "metadata", None) or {}
    return {k: md.get(k) for k in ("doi", "pmid", "pmcid", "arxiv")}


def _row(item_or_ids) -> FulltextDocument | None:
    if not isinstance(item_or_ids, dict) and getattr(item_or_ids, "pk", None):
        row = (
            FulltextDocument.objects.filter(content_item_id=item_or_ids.pk)
            .order_by("-fetched_at")
            .first()
        )
        if row is not None:
            return row
    return store.find_document(_ids(item_or_ids))


def _document(row: FulltextDocument) -> Document:
    return Document(
        id=str(row.pk),
        title=row.title,
        doi=row.doi,
        pmid=row.pmid,
        pmcid=row.pmcid,
        arxiv_id=row.arxiv_id,
        source=row.source,
        source_url=row.source_url,
        licensed=row.licensed,
        chars=row.chars,
        markdown_path=store.absolute(row.markdown_path),
        original_path=store.original_file(row),
        original_kind=row.original_kind,
        content_item_id=str(row.content_item_id) if row.content_item_id else None,
        fetched_at=row.fetched_at,
    )


def document(item_or_ids) -> Document | None:
    """The stored full text of a paper, if the tool has it."""
    row = _row(item_or_ids)
    return _document(row) if row else None


def document_by_id(document_id) -> Document | None:
    row = FulltextDocument.objects.filter(pk=document_id).first()
    return _document(row) if row else None


def full_text(item_or_ids) -> str | None:
    """The stored paper as markdown (metadata, abstract, full text), or None."""
    row = _row(item_or_ids)
    return store.read_markdown(row) if row else None


def has_full_text(item_or_ids) -> bool:
    return _row(item_or_ids) is not None


def availability(item_or_ids) -> dict:
    """Whether the paper is stored or within reach (see ``service.check``).

    A stored paper answers from the database; anything else asks the resolver
    and, for a DOI, one cached Unpaywall lookup. No full text is fetched.
    """
    from . import service

    if (row := _row(item_or_ids)) is not None:
        return {
            "availability": service.STORED,
            "document": str(row.pk),
            "explanation": f"Already retrieved from {row.source}.",
        }
    ids = {k: v for k, v in _ids(item_or_ids).items() if v}
    if not ids:
        return {
            "availability": "invalid_identifier",
            "explanation": "The paper has no DOI, PMID, PMCID or arXiv id.",
        }
    return service.check([ids])[0]


@dataclass(frozen=True)
class RequestState:
    id: str
    identifier: object
    status: str
    finished: bool
    explanation: str
    retryable: bool
    next_steps: list
    document_id: str | None


def request_state(request_id) -> RequestState | None:
    """Where one request stands."""
    r = FulltextRequest.objects.filter(pk=request_id).first()
    if r is None:
        return None
    return RequestState(
        id=str(r.pk),
        identifier=r.identifier,
        status=r.status,
        finished=r.finished,
        explanation=r.explanation,
        retryable=r.retryable,
        next_steps=list(r.next_steps),
        document_id=str(r.document_id) if r.document_id else None,
    )
