"""External-link / DOI / arXiv resolver.

Turns a pasted identifier (arXiv URL or id, DOI or ``doi.org`` URL, or a plain
landing-page URL) into a deduplicated ``content.ContentItem`` row, so a user
can attach a paper to a project even when the literature scan hasn't picked it
up yet.

This mirrors the scan pipeline (:mod:`tools.retrieval.ingest`) as closely as
possible so a resolved item renders identically to an organically-scraped
one: it builds the same :class:`~tools.retrieval.sources.record.Record` shape,
stores the same ``metadata`` keys via ``Record.to_metadata()``, dedups on the
same ``(source, external_id)`` key, and embeds with the same
``FastEmbedEmbedder`` / ``build_article_text`` used by the scan.

Kept synchronous and dependency-light: network calls use the stdlib
``urllib.request`` (the same pattern already used for synchronous fetches in
``apps.accounts.intake.retrievers._http``), not the scraper's async
``aiohttp`` client, since ``resolve_external`` is a plain sync function meant
to be called from a request/view. Every network call is guarded so a bad
response degrades to :class:`ResolveError` instead of a 500.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from tools.retrieval.embedding import FastEmbedEmbedder, build_article_text
from tools.retrieval.models import ContentItem
from tools.retrieval.sources.openalex import OpenAlexScraper
from tools.retrieval.sources.record import (
    Record,
    normalize_doi,
    rebuild_inverted_abstract,
)

logger = logging.getLogger(__name__)

__all__ = ["ResolveError", "ResolveResult", "resolve_external"]

DEFAULT_TIMEOUT = 15
USER_AGENT = "Mycelium resolver (+https://mycelium.test)"

ARXIV_API_URL = "http://export.arxiv.org/api/query"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_WORK_URL = "https://api.openalex.org/works"

ATOM_NS = "{http://www.w3.org/2005/Atom}"

_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", re.IGNORECASE)
_ARXIV_BARE_RE = re.compile(r"^(\d{4}\.\d{4,5})(?:v\d+)?$")
_ARXIV_OLD_RE = re.compile(r"^([a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_JATS_TAG_RE = re.compile(r"<[^>]+>")


class ResolveError(Exception):
    """Raised when ``raw_input`` cannot be turned into a ``ContentItem``."""


@dataclass
class ResolveResult:
    content_item: ContentItem
    created: bool
    #: "ok" when the abstract was embedded, "no_abstract" when there was no
    #: abstract text to embed (or an existing row already carries this state).
    embed_status: str


# --------------------------------------------------------------------------- #
# Low-level HTTP. A single choke point so tests can mock one function.
# --------------------------------------------------------------------------- #


def _get_text(
    url: str, *, timeout: int = DEFAULT_TIMEOUT, accept: str = "application/json"
) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}, method="GET"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


# --------------------------------------------------------------------------- #
# Identifier detection.
# --------------------------------------------------------------------------- #


def _extract_arxiv_id(text: str) -> str | None:
    m = _ARXIV_URL_RE.search(text)
    if m:
        raw_id = m.group(1)
        if raw_id.lower().endswith(".pdf"):
            raw_id = raw_id[:-4]
        raw_id = re.sub(r"v\d+$", "", raw_id)
        return raw_id.strip("/") or None

    candidate = text
    if candidate.lower().startswith("arxiv:"):
        candidate = candidate[len("arxiv:"):].strip()

    m = _ARXIV_BARE_RE.match(candidate)
    if m:
        return m.group(1)
    m = _ARXIV_OLD_RE.match(candidate)
    if m:
        return m.group(1)
    return None


def _extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if not m:
        return None
    doi = m.group(0).rstrip(").,;'\"")
    return normalize_doi(doi)


def _detect(raw: str) -> tuple[str, str]:
    """Classify ``raw`` as ``("arxiv" | "doi" | "url", identifier)``."""
    text = (raw or "").strip()
    if not text:
        raise ResolveError("Input is empty.")

    arxiv_id = _extract_arxiv_id(text)
    if arxiv_id:
        return "arxiv", arxiv_id

    doi = _extract_doi(text)
    if doi:
        return "doi", doi

    if _URL_RE.match(text):
        return "url", text

    raise ResolveError(
        f"Could not find a DOI, arXiv id, or URL in {raw.strip()!r}."
    )


# --------------------------------------------------------------------------- #
# arXiv.
# --------------------------------------------------------------------------- #


def _fetch_arxiv_record(arxiv_id: str) -> Record:
    url = f"{ARXIV_API_URL}?id_list={quote(arxiv_id, safe='')}"
    try:
        xml_text = _get_text(url, accept="application/atom+xml")
    except (OSError, ValueError) as exc:
        raise ResolveError(f"Could not reach arXiv for id {arxiv_id!r}: {exc}") from exc
    return _parse_arxiv_atom(xml_text, arxiv_id)


def _parse_arxiv_atom(xml_text: str, arxiv_id: str) -> Record:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ResolveError(
            f"arXiv returned unparseable XML for {arxiv_id!r}: {exc}"
        ) from exc

    entry = root.find(f"{ATOM_NS}entry")
    if entry is None:
        raise ResolveError(f"arXiv has no entry for id {arxiv_id!r}.")

    entry_id = (entry.findtext(f"{ATOM_NS}id") or "").strip()
    if "arxiv.org/api/errors" in entry_id:
        raise ResolveError(f"arXiv id {arxiv_id!r} was not found.")

    title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM_NS}title") or "").strip()
    summary = re.sub(r"\s+", " ", entry.findtext(f"{ATOM_NS}summary") or "").strip()

    authors = [
        (a.findtext(f"{ATOM_NS}name") or "").strip()
        for a in entry.findall(f"{ATOM_NS}author")
    ]
    authors = [a for a in authors if a]

    published = (entry.findtext(f"{ATOM_NS}published") or "").strip()
    year = int(published[:4]) if published[:4].isdigit() else None

    return Record(
        source="arxiv",
        source_id=arxiv_id,
        title=title,
        arxiv=arxiv_id,
        abstract=summary or None,
        authors=authors,
        year=year,
        publication_date=published[:10] or None,
        url=f"https://arxiv.org/abs/{arxiv_id}",
    )


# --------------------------------------------------------------------------- #
# Crossref (DOI), with a best-effort OpenAlex abstract enrichment.
# --------------------------------------------------------------------------- #


def _strip_jats(text) -> str | None:
    if not text or not isinstance(text, str):
        return None
    cleaned = re.sub(r"\s+", " ", _JATS_TAG_RE.sub(" ", text)).strip()
    return cleaned or None


def _crossref_authors(msg: dict) -> list[str]:
    out: list[str] = []
    for a in msg.get("author") or []:
        if not isinstance(a, dict):
            continue
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        name = f"{given} {family}".strip() or (a.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _crossref_year(msg: dict) -> int | None:
    for key in ("published", "published-print", "published-online", "issued"):
        block = msg.get(key)
        if not isinstance(block, dict):
            continue
        parts = block.get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError, IndexError):
                continue
    return None


def _try_openalex_abstract_by_doi(doi: str) -> str | None:
    """Best-effort abstract enrichment; any failure just means no enrichment."""
    try:
        raw = _get_text(f"{OPENALEX_WORK_URL}/doi:{quote(doi, safe='/')}")
        payload = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return rebuild_inverted_abstract(payload.get("abstract_inverted_index"))


def _fetch_crossref_record(doi: str) -> Record:
    url = f"{CROSSREF_WORKS_URL}/{quote(doi, safe='/')}"
    try:
        payload = json.loads(_get_text(url))
    except (OSError, ValueError) as exc:
        raise ResolveError(f"Could not reach Crossref for DOI {doi!r}: {exc}") from exc

    msg = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(msg, dict):
        raise ResolveError(f"Crossref has no record for DOI {doi!r}.")

    titles = msg.get("title") or []
    title = (titles[0] if titles else "").strip()
    venues = msg.get("container-title") or []
    venue = (venues[0] or "").strip() if venues else None

    record = Record(
        source="crossref",
        source_id=doi,
        title=title,
        doi=doi,
        abstract=_strip_jats(msg.get("abstract")),
        authors=_crossref_authors(msg),
        year=_crossref_year(msg),
        venue=venue or None,
        url=f"https://doi.org/{doi}",
    )

    if not record.clean_abstract:
        enriched = _try_openalex_abstract_by_doi(doi)
        if enriched:
            record.abstract = enriched

    return record


# --------------------------------------------------------------------------- #
# Bare-URL fallback via OpenAlex.
# --------------------------------------------------------------------------- #


def _bare_openalex_id(value: str | None) -> str:
    if not value:
        return ""
    return str(value).rstrip("/").rsplit("/", 1)[-1]


def _fetch_openalex_by_url(url: str) -> Record:
    query = urlencode({
        "filter": f"primary_location.landing_page_url:{url}",
        "per-page": "1",
    })
    try:
        payload = json.loads(_get_text(f"{OPENALEX_WORKS_URL}?{query}"))
    except (OSError, ValueError) as exc:
        raise ResolveError(f"Could not look up {url!r} via OpenAlex: {exc}") from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    if not results:
        raise ResolveError(f"OpenAlex found no work for URL {url!r}.")

    # Reuse the live scraper's parser so a resolved OpenAlex item matches an
    # organically-scraped one exactly, then relabel to the resolver's
    # lowercase source name and a bare (non-URL) external id.
    record = OpenAlexScraper._parse(results[0])
    record.source = "openalex"
    record.source_id = _bare_openalex_id(record.source_id)
    record.sources = {"openalex"}
    if not record.url:
        record.url = url
    return record


# --------------------------------------------------------------------------- #
# Dedup + create + embed.
# --------------------------------------------------------------------------- #

_SOURCE_BY_KIND = {"arxiv": "arxiv", "doi": "crossref"}


def _existing_result(existing: ContentItem) -> ResolveResult:
    embed_status = "ok" if existing.embedding is not None else "no_abstract"
    return ResolveResult(
        content_item=existing, created=False, embed_status=embed_status
    )


def _create(record: Record) -> ResolveResult:
    external_id = (record.source_id or "")[:255]
    if not external_id:
        raise ResolveError("Resolved record has no usable identifier.")

    item = ContentItem(
        type=ContentItem.Type.PAPER,
        source=record.source,
        external_id=external_id,
        source_url=(record.url or "")[:500],
        metadata=record.to_metadata(),
    )

    embed_status = "no_abstract"
    if record.clean_abstract:
        try:
            vectors = FastEmbedEmbedder()([build_article_text(record)])
            if vectors and vectors[0]:
                item.embedding = vectors[0]
                embed_status = "ok"
        except Exception as exc:  # noqa: BLE001 - never let embedding infra crash a resolve.
            logger.warning(
                "resolver: embedding failed for %s:%s: %s",
                record.source,
                external_id,
                exc,
            )

    item.save()
    return ResolveResult(content_item=item, created=True, embed_status=embed_status)


def resolve_external(raw_input: str) -> ResolveResult:
    """Resolve a pasted DOI / arXiv id / URL into a deduplicated ``ContentItem``."""
    kind, ident = _detect(raw_input)

    # arXiv/DOI: the external id is known without any network call, so a
    # duplicate short-circuits before touching the network or the embedder.
    if kind in _SOURCE_BY_KIND:
        source = _SOURCE_BY_KIND[kind]
        external_id = ident[:255]
        existing = ContentItem.objects.filter(
            source=source, external_id=external_id
        ).first()
        if existing is not None:
            return _existing_result(existing)

        record = (
            _fetch_arxiv_record(ident)
            if kind == "arxiv"
            else _fetch_crossref_record(ident)
        )
        return _create(record)

    # Bare URL: the external id is only known after the OpenAlex lookup.
    record = _fetch_openalex_by_url(ident)
    external_id = (record.source_id or "")[:255]
    existing = ContentItem.objects.filter(
        source=record.source, external_id=external_id
    ).first()
    if existing is not None:
        return _existing_result(existing)
    return _create(record)
