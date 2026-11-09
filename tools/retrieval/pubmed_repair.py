"""One-shot repair of PubMed identifiers stored before the Q-057 scraper fix.

Until 2026-11-08 the PubMed scraper read ``.//ArticleIdList/ArticleId``, which
also matches every cited paper in ``PubmedData/ReferenceList``, and kept the
last DOI/PMCID it saw. So a PubMed-sourced paper usually carries a cited
paper's DOI and PMCID in ``metadata`` — and, because the canonical id is built
from the DOI, in ``external_id`` too.

This module re-fetches the PubMed record for every stored paper with a PMID
(efetch, 200 ids a request, at NCBI's rate) and, for PubMed-sourced rows:

- sets ``metadata.doi`` / ``metadata.pmcid`` to the article's own ids;
- when PubMed has no own id, clears the stored one **only if it is proven
  foreign**: one of the article's references, or (for a PMCID) one that PMC's
  ID converter says belongs to another PMID. A value that is neither may have
  come legitimately from another source, and is left alone;
- rebuilds ``external_id`` the way ingest does (``doi:`` > ``pmid:``).

It does not merge anything. A corrected DOI that another row already holds is a
duplicate the bad DOI was hiding; it is reported, and ``dedupe_content_papers``
merges it afterwards. An ``external_id`` that another PubMed row already holds
would break the unique key, so that row keeps its old ``external_id`` (metadata
is still fixed) and is reported; a re-run picks it up once the holder moved.

Rows from other sources that carry a PMID get one correction only: when their
DOI agrees with that PMID's record (so the PMID is theirs) but their PMCID is
proven foreign — they absorbed it from a bad PubMed record at ingest — the
PMCID is set to the PMID's own (or cleared). If instead the stored DOI is one of
that PMID's references, the row absorbed a citing paper's PMID; such rows are
counted for a decision, not changed.

Entry point: :func:`repair_pubmed_ids`; the ``repair_pubmed_ids`` command wraps
it (dry run by default, ``--apply`` to write).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields

from django.db import transaction

from tools.retrieval.models import ContentItem
from tools.retrieval.sources.pubmed import BASE, BATCH, article_own_ids
from tools.retrieval.sources.record import (
    normalize_doi,
    normalize_pmcid,
    normalize_pmid,
)
from tools.retrieval.sources.registry import ScraperConfig

EFETCH = f"{BASE}/efetch.fcgi"
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"


@dataclass(frozen=True)
class OwnIds:
    doi: str | None
    pmcid: str | None
    ref_dois: frozenset[str] = frozenset()
    ref_pmcids: frozenset[str] = frozenset()


def parse_own_ids(xml_text: str) -> dict[str, OwnIds]:
    """efetch XML -> ``{pmid: OwnIds}``, normalized like a stored row."""
    out: dict[str, OwnIds] = {}
    root = ET.fromstring(xml_text)
    for art in root.iter("PubmedArticle"):
        pmid = normalize_pmid(art.findtext("MedlineCitation/PMID"))
        if not pmid:
            continue
        doi, pmcid = article_own_ids(art)
        ref_dois, ref_pmcids = set(), set()
        for aid in art.findall("PubmedData/ReferenceList//ArticleId"):
            if aid.get("IdType") == "doi" and normalize_doi(aid.text):
                ref_dois.add(normalize_doi(aid.text))
            elif aid.get("IdType") == "pmc" and normalize_pmcid(aid.text):
                ref_pmcids.add(normalize_pmcid(aid.text))
        out[pmid] = OwnIds(
            normalize_doi(doi), normalize_pmcid(pmcid),
            frozenset(ref_dois), frozenset(ref_pmcids),
        )
    return out


Fetch = Callable[[list[str]], str]
# PMCIDs -> the PMID each belongs to (absent when PMC does not know the PMCID).
IdConv = Callable[[list[str]], dict[str, str]]


def _ncbi_post(config: ScraperConfig) -> Callable[[str, dict], str]:
    """One rate-limited, retrying request to an NCBI endpoint, shared clock.

    POST for E-utilities; GET (``get=True``) for PMC's ID converter, which
    rejects a POST and takes no ``api_key``.
    """
    interval = 1.0 / (9.0 if config.pubmed_api_key else 3.0)
    last = [0.0]

    def post(url: str, params: dict, get: bool = False) -> str:
        params = {**params, "tool": config.tool_name}
        if config.contact_email:
            params["email"] = config.contact_email
        if config.pubmed_api_key and not get:
            params["api_key"] = config.pubmed_api_key
        query = urllib.parse.urlencode(params)
        body = None if get else query.encode()
        if get:
            url = f"{url}?{query}"
        for attempt in range(5):
            wait = last[0] + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            last[0] = time.monotonic()
            try:
                with urllib.request.urlopen(url, body, timeout=120) as resp:
                    return resp.read().decode()
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt == 4:
                    raise RuntimeError(f"NCBI request failed: {url}: {exc}") from exc
                time.sleep(2 ** attempt)
        raise AssertionError("unreachable")

    return post


def efetch_client(config: ScraperConfig | None = None) -> Fetch:
    """A rate-limited, retrying efetch POST for one batch of PMIDs."""
    post = _ncbi_post(config or ScraperConfig.from_settings())
    return lambda pmids: post(EFETCH, {"db": "pubmed", "retmode": "xml",
                                       "id": ",".join(pmids)})


def idconv_client(config: ScraperConfig | None = None) -> IdConv:
    """PMC's ID converter: which PMID each PMCID of a batch belongs to."""
    post = _ncbi_post(config or ScraperConfig.from_settings())

    def convert(pmcids: list[str]) -> dict[str, str]:
        payload = json.loads(post(IDCONV, {"ids": ",".join(pmcids), "format": "json"},
                                  get=True))
        out = {}
        for rec in payload.get("records", []):
            pmc = normalize_pmcid(rec.get("pmcid"))
            pmid = normalize_pmid(rec.get("pmid"))
            if pmc and pmid and rec.get("status") != "error":
                out[pmc] = pmid
        return out

    return convert


@dataclass
class RepairStats:
    checked: int = 0              # paper rows with a PMID
    pubmed_rows: int = 0          # of which source == PubMed
    not_in_pubmed: int = 0        # PMID PubMed did not return
    doi_replaced: int = 0         # stored DOI swapped for the article's own
    doi_set: int = 0              # own DOI filled where none was stored
    doi_cleared: int = 0          # stored DOI was a reference's, no own DOI
    doi_unverified: int = 0       # no own DOI, stored one not a reference: kept
    pmcid_replaced: int = 0
    pmcid_set: int = 0
    pmcid_cleared: int = 0
    pmcid_unverified: int = 0     # no own PMCID, stored one not shown foreign: kept
    pmcid_foreign_by_idconv: int = 0  # PMC says the stored PMCID is another PMID's
    other_source_pmcid_fixed: int = 0  # other source, own PMID, another paper's PMCID
    rows_changed: int = 0
    external_id_changed: int = 0
    external_id_collisions: int = 0   # new external_id held elsewhere: old kept
    duplicates_exposed: int = 0       # corrected DOI already on another row
    foreign_pmid_rows: int = 0        # other source; DOI is a reference of the PMID
    other_source_doi_differs: int = 0  # other source; DOI not the PMID's own
    written: int = 0
    samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name)
                for f in fields(self) if f.name != "samples"}


def _batches(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _canonical(doi: str | None, pmid: str | None, pmcid: str | None) -> str:
    """The ingest canonical id (``Deduplicator.results``), truncated like ingest."""
    if doi:
        return f"doi:{doi}"[:255]
    if pmid:
        return f"pmid:{pmid}"[:255]
    return f"pmcid:{pmcid}"[:255] if pmcid else ""


def repair_pubmed_ids(
    *,
    apply: bool = False,
    fetch: Fetch | None = None,
    idconv: IdConv | None = None,
    batch: int = BATCH,
    limit: int | None = None,
    log: Callable[[str], None] | None = None,
) -> RepairStats:
    """Check (and with ``apply``, correct) the stored ids of PMID-bearing papers."""

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    stats = RepairStats()
    papers = ContentItem.objects.filter(type=ContentItem.Type.PAPER)
    rows = list(
        papers.filter(metadata__has_key="pmid")
        .exclude(metadata__pmid=None)
        .only("id", "source", "external_id", "metadata")
        .order_by("id")
    )
    rows = [r for r in rows if normalize_pmid((r.metadata or {}).get("pmid"))]
    if limit:
        rows = rows[:limit]
    stats.checked = len(rows)

    # Who holds which DOI / external_id now — for collision reporting.
    doi_owner: dict[str, set] = {}
    held = papers.exclude(metadata__doi=None).values_list("pk", "metadata__doi")
    for pk, doi in held:
        nd = normalize_doi(doi)
        if nd:
            doi_owner.setdefault(nd, set()).add(pk)
    ext_owner = dict(
        ContentItem.objects.filter(source="PubMed")
        .exclude(external_id="")
        .values_list("external_id", "pk")
    )

    pmids = sorted({normalize_pmid(r.metadata["pmid"]) for r in rows})
    fetch = fetch or efetch_client()
    own: dict[str, OwnIds] = {}
    total = (len(pmids) + batch - 1) // batch
    for n, chunk in enumerate(_batches(pmids, batch), 1):
        own.update(parse_own_ids(fetch(chunk)))
        if n % 10 == 0 or n == total:
            emit(f"fetched {n}/{total} batches ({len(own)} records)")

    # A stored PMCID that is not the article's own and not one of its
    # references may still be another paper's (a reference PubMed has since
    # dropped, or one absorbed from a PubMed record at ingest): ask PMC whose
    # it is. Only those PMCIDs are looked up.
    suspects: set[str] = set()
    for item in rows:
        md = item.metadata or {}
        ids = own.get(normalize_pmid(md.get("pmid")))
        pmc = normalize_pmcid(md.get("pmcid"))
        if ids and pmc and pmc != ids.pmcid and pmc not in ids.ref_pmcids:
            suspects.add(pmc)
    owner_of: dict[str, str] = {}
    if suspects:
        idconv = idconv or idconv_client()
        for chunk in _batches(sorted(suspects), batch):
            owner_of.update(idconv(chunk))
        emit(f"checked {len(suspects)} unexplained PMCIDs with PMC's id converter")

    changed: list[ContentItem] = []
    for item in rows:
        md = dict(item.metadata or {})
        pmid = normalize_pmid(md.get("pmid"))
        ids = own.get(pmid)
        if ids is None:
            stats.not_in_pubmed += 1
            continue
        stored_doi = normalize_doi(md.get("doi"))
        stored_pmc = normalize_pmcid(md.get("pmcid"))
        by_idconv = (stored_pmc and stored_pmc in owner_of
                     and owner_of[stored_pmc] != pmid)

        if item.source != "PubMed":
            if stored_doi and stored_doi in ids.ref_dois:
                stats.foreign_pmid_rows += 1
                _sample(stats, f"foreign pmid: {item.source} {item.pk} "
                               f"doi={stored_doi} pmid={pmid} "
                               f"(PubMed's own doi={ids.doi})")
            elif stored_doi and ids.doi and stored_doi != ids.doi:
                stats.other_source_doi_differs += 1
            elif stored_pmc and stored_pmc != ids.pmcid and (
                    stored_pmc in ids.ref_pmcids or by_idconv):
                # The PMID is this row's own; the PMCID is another paper's.
                stats.other_source_pmcid_fixed += 1
                stats.pmcid_foreign_by_idconv += bool(by_idconv)
                _sample(stats, f"other-source pmcid: {item.source} {item.pk} "
                               f"pmid={pmid} pmcid {stored_pmc} -> {ids.pmcid}")
                md["pmcid"] = ids.pmcid
                item.metadata = md
                stats.rows_changed += 1
                changed.append(item)
            continue

        stats.pubmed_rows += 1
        new_doi = _decide(stats, "doi", stored_doi, ids.doi, ids.ref_dois)
        new_pmc = _decide(stats, "pmcid", stored_pmc, ids.pmcid,
                          ids.ref_pmcids | ({stored_pmc} if by_idconv else set()))
        stats.pmcid_foreign_by_idconv += bool(by_idconv and not ids.pmcid)
        if new_doi == stored_doi and new_pmc == stored_pmc:
            continue

        md["doi"], md["pmcid"] = new_doi, new_pmc
        item.metadata = md
        stats.rows_changed += 1
        if new_doi and new_doi != stored_doi:
            others = doi_owner.get(new_doi, set()) - {item.pk}
            if others:
                stats.duplicates_exposed += 1
                _sample(stats, f"duplicate exposed: PubMed {item.pk} pmid={pmid} "
                               f"doi={new_doi} also on {len(others)} other row(s)")
            doi_owner.setdefault(new_doi, set()).add(item.pk)

        new_ext = _canonical(new_doi, pmid, new_pmc)
        if new_ext and new_ext != item.external_id:
            holder = ext_owner.get(new_ext)
            if holder is not None and holder != item.pk:
                stats.external_id_collisions += 1
                _sample(stats, f"external_id collision: {item.pk} wants {new_ext}, "
                               f"held by {holder}; kept {item.external_id}")
            else:
                ext_owner.pop(item.external_id, None)
                ext_owner[new_ext] = item.pk
                item.external_id = new_ext
                stats.external_id_changed += 1
        changed.append(item)

    for line in stats.samples:
        emit(line)
    if apply and changed:
        with transaction.atomic():
            ContentItem.objects.bulk_update(
                changed, ["metadata", "external_id"], batch_size=500
            )
        stats.written = len(changed)
    emit("tally: " + ", ".join(f"{k}={v}" for k, v in stats.as_dict().items()))
    return stats


def _decide(stats: RepairStats, kind: str, stored, own, refs) -> str | None:
    """The value a PubMed row should hold for one identifier, counting why."""
    if own:
        if stored == own:
            return stored
        setattr(stats, f"{kind}_{'replaced' if stored else 'set'}",
                getattr(stats, f"{kind}_{'replaced' if stored else 'set'}") + 1)
        return own
    if stored and stored in refs:
        setattr(stats, f"{kind}_cleared", getattr(stats, f"{kind}_cleared") + 1)
        return None
    if stored:
        setattr(stats, f"{kind}_unverified", getattr(stats, f"{kind}_unverified") + 1)
    return stored


def _sample(stats: RepairStats, line: str, keep: int = 8) -> None:
    """Keep the first few example lines of each kind for the log."""
    kind = line.split(":", 1)[0]
    if sum(s.startswith(kind + ":") for s in stats.samples) < keep:
        stats.samples.append(line)
