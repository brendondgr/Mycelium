"""Resolve parsed items to verified identifiers and bibliographic metadata.

Every article ends up with as many of PMID / PMCID / DOI as exist, plus the
title, journal and year from the authoritative record (PubMed, else the arXiv
API for preprints, Crossref, DataCite), so the caller can see exactly which
paper is about to be fetched. Identifiers that disagree with each other, or
with the title the caller expected, stop the item rather than fetching a
different paper.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from . import sources as S
from .convert import article_ids
from .fetcher import Fetcher
from .identifiers import Item, normalise_title, title_matches
from .sources import arxiv_id, cfg

log = logging.getLogger(__name__)

ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "into",
    "via",
    "its",
    "their",
    "be",
    "was",
    "were",
}


class Resolver:
    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher
        self.cache = fetcher.cache
        env = fetcher.env
        self.api_key = cfg(env, "PUBMED_API_KEY")
        self.email = cfg(env, "CONTACT_EMAIL") or ""
        self.common = {"tool": S.NCBI_TOOL, "email": self.email}
        if self.api_key:
            self.common["api_key"] = self.api_key
        self.session = fetcher.session
        self._interval = 0.11 if self.api_key else 0.34

    # -- NCBI plumbing ------------------------------------------------------ #
    def _ncbi(self, endpoint: str, data: dict, attempts: int = 4) -> requests.Response:
        """POST to an E-utility, sharing one throttle across every thread."""
        r = None
        for attempt in range(attempts):
            self.fetcher.state.wait_turn("ncbi", self._interval)
            try:
                r = self.session.post(
                    f"{S.EUTILS}/{endpoint}", data={**self.common, **data}, timeout=60
                )
            except requests.RequestException:
                if attempt == attempts - 1:
                    raise
                time.sleep(2**attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < attempts - 1:
                    time.sleep(2**attempt)
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()
        return r

    def pubmed_records(self, pmids) -> dict[str, dict]:
        """{pmid: record} for the PMIDs PubMed knows. Records are cached."""
        out, todo = {}, []
        for pm in dict.fromkeys(pmids):
            rec = self.cache.get_json("pubmed", pm)
            if rec:
                out[pm] = rec
            else:
                todo.append(pm)
        for i in range(0, len(todo), 200):
            chunk = todo[i : i + 200]
            r = self._ncbi(
                "efetch.fcgi",
                {
                    "db": "pubmed",
                    "id": ",".join(chunk),
                    "retmode": "xml",
                    "rettype": "abstract",
                },
            )
            for rec in parse_pubmed_xml(r.text):
                if rec["pmid"] in chunk:
                    rec["doi"] = (rec.get("doi") or "").lower()
                    out[rec["pmid"]] = rec
                    self.cache.put_json("pubmed", rec["pmid"], rec)
        return out

    def dois_to_pmids(self, dois) -> dict[str, str]:
        """{doi: pmid} for DOIs PubMed indexes. 50 DOIs per OR'd query, mapped back
        by reading each hit's DOI."""
        mapping, todo = {}, []
        for d in dict.fromkeys(dois):
            if self.cache.has_json("doi_pmid", d):
                if pm := self.cache.get_json("doi_pmid", d):
                    mapping[d] = pm
            else:
                todo.append(d)
        for i in range(0, len(todo), 50):
            chunk = todo[i : i + 50]
            term = " OR ".join(f'"{d}"[doi]' for d in chunk)
            r = self._ncbi(
                "esearch.fcgi",
                {"db": "pubmed", "term": term, "retmax": 500, "retmode": "json"},
            )
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            recs = self.pubmed_records(ids) if ids else {}
            by_doi = {rec["doi"]: pm for pm, rec in recs.items() if rec.get("doi")}
            for d in chunk:
                pm = by_doi.get(d)
                self.cache.put_json("doi_pmid", d, pm)
                if pm:
                    mapping[d] = pm
        return mapping

    def idconv(self, ids) -> dict[str, dict]:
        """{requested id: record} from the PMC ID converter (PMCIDs -> PMID / DOI)."""
        out = {}
        for i in range(0, len(ids), 200):
            chunk = ids[i : i + 200]
            self.fetcher.state.wait_turn("idconv", 0.5)
            r = self.session.get(
                S.IDCONV,
                params={
                    "ids": ",".join(chunk),
                    "format": "json",
                    "tool": S.NCBI_TOOL,
                    "email": self.email,
                },
                timeout=60,
            )
            r.raise_for_status()
            for rec in r.json().get("records", []):
                out[str(rec.get("requested-id", "")).upper()] = rec
        return out

    def pmcids_for(self, pmids) -> dict[str, str]:
        """PMID -> PMCID for the PubMed records with a PMC deposit. Cached per PMID;
        a failed batch is skipped (PMC is then simply not tried)."""
        mapping, todo = {}, []
        for pm in dict.fromkeys(pmids):
            if self.cache.has_json("pmcid", pm):
                if pmc := self.cache.get_json("pmcid", pm):
                    mapping[pm] = pmc
            else:
                todo.append(pm)
        for i in range(0, len(todo), 200):
            chunk = todo[i : i + 200]
            try:
                recs = self.idconv(chunk)
            except (requests.RequestException, ValueError) as exc:
                log.info("full text: PMC id conversion failed, continuing: %s", exc)
                continue
            for pm in chunk:
                pmc = (recs.get(pm.upper()) or {}).get("pmcid")
                self.cache.put_json("pmcid", pm, pmc)
                if pmc:
                    mapping[pm] = pmc
        return mapping

    def title_search(self, title: str, n: int = 5) -> list[dict]:
        """Top PubMed matches for a title, as metadata records.

        Every word must be in the title field (stopwords dropped: PubMed refuses
        them in a [ti] clause). If that finds nothing, a relevance-ranked search
        still offers candidates.
        """
        words = [
            w for w in re.findall(r"[A-Za-z0-9]+", title) if w.lower() not in STOPWORDS
        ][:25]
        ids: list[str] = []
        for term, sort in (
            (" AND ".join(f"{w}[ti]" for w in words), None),
            (" ".join(words), "relevance"),
        ):
            data = {"db": "pubmed", "term": term, "retmax": n, "retmode": "json"}
            if sort:
                data["sort"] = sort
            ids = (
                self._ncbi("esearch.fcgi", data)
                .json()
                .get("esearchresult", {})
                .get("idlist", [])
            )
            if ids:
                break
        recs = self.pubmed_records(ids)
        return [recs[i] for i in ids if i in recs]

    # -- PMC full text, batched -------------------------------------------- #
    def pmc_articles(self, pmcids) -> dict[str, tuple[ET.Element, str]]:
        """{pmcid: (<article>, path of the cached XML)} for the PMCIDs PMC serves.

        One efetch per 50 articles. NCBI answers 400 for a batch holding an id
        it will not serve, so a failing batch is bisected and the bad ids
        dropped rather than failing the rest.
        """
        out = {}
        todo = []
        for pmcid in dict.fromkeys(pmcids):
            xml = (
                None
                if self.fetcher.retry
                else self.cache.read_text("pmc_xml", pmcid, "xml")
            )
            if xml is not None:
                try:
                    out[pmcid] = (
                        ET.fromstring(xml),
                        str(self.cache.path("pmc_xml", pmcid, "xml")),
                    )
                    continue
                except ET.ParseError:
                    pass
            todo.append(pmcid)
        for i in range(0, len(todo), 50):
            root = self._efetch_pmc(todo[i : i + 50])
            if root is None:
                continue
            for article in root.iter("article"):
                pmcid, _ = article_ids(article)
                if not pmcid:
                    continue
                path = self.cache.write_text(
                    "pmc_xml", pmcid, "xml", ET.tostring(article, encoding="unicode")
                )
                out[pmcid] = (article, str(path))
        return out

    def _efetch_pmc(self, chunk, attempts: int = 3):
        data = {
            "db": "pmc",
            "retmode": "xml",
            "id": ",".join(c.replace("PMC", "") for c in chunk),
        }
        try:
            r = self._ncbi("efetch.fcgi", data, attempts=attempts)
            return ET.fromstring(r.text)
        except (requests.RequestException, ET.ParseError) as exc:
            if len(chunk) == 1:
                log.info("full text: PMC would not serve %s: %s", chunk[0], exc)
                return None
            mid = len(chunk) // 2
            merged = ET.Element("pmc-articleset")
            for half in (chunk[:mid], chunk[mid:]):
                sub = self._efetch_pmc(half, attempts)
                if sub is not None:
                    merged.extend(list(sub))
            return merged if len(merged) else None

    # -- Crossref / DOI registry ------------------------------------------- #
    def crossref(self, doi: str):
        """Crossref work: dict, {} when Crossref lacks the DOI, None on error."""
        f = self.fetcher
        return f.cached_json("crossref", doi, lambda: f.crossref_record(doi))

    def doi_registered(self, doi: str) -> bool | None:
        """True/False from the DOI handle system (covers DataCite DOIs too)."""
        try:
            r = self.session.get(
                f"https://doi.org/api/handles/{quote(doi, safe='/')}", timeout=20
            )
        except requests.RequestException:
            return None
        if r.status_code == 404:
            return False
        return r.status_code == 200 and r.json().get("responseCode") == 1

    def datacite(self, doi: str):
        """DataCite record attributes: dict, {} when unknown, None on error."""

        def fetch():
            try:
                r = self.session.get(S.DATACITE + quote(doi, safe="/"), timeout=30)
            except requests.RequestException:
                return None
            if r.status_code == 404:
                return {}
            if r.status_code != 200:
                return None
            return r.json().get("data", {}).get("attributes")

        return self.fetcher.cached_json("datacite", doi, fetch)

    def pii_to_doi(self, pii: str) -> str | None:
        """A ScienceDirect PII's DOI via Crossref ('' when not exactly one match)."""
        if self.cache.has_json("pii_doi", pii):
            return self.cache.get_json("pii_doi", pii)
        r = self.fetcher.get(
            "crossref",
            "https://api.crossref.org/works",
            params={"filter": f"alternative-id:{pii}", "rows": 2},
        )
        if r.status_code != 200:
            return None
        items = r.json().get("message", {}).get("items", [])
        doi = items[0]["DOI"].lower() if len(items) == 1 else ""
        self.cache.put_json("pii_doi", pii, doi)
        return doi

    # -- arXiv ------------------------------------------------------------- #
    def arxiv_records(self, ids):
        """{arxiv id: metadata} for the ids arXiv knows; None if arXiv is unreachable.

        Up to 100 ids per query, through the fetcher's 'arxiv' throttle (one
        request every 3 seconds, PDFs included). Found records are cached.
        """
        out, todo = {}, []
        for aid in dict.fromkeys(ids):
            rec = self.cache.get_json("arxiv", aid)
            if rec:
                out[aid] = rec
            else:
                todo.append(aid)
        for i in range(0, len(todo), 100):
            chunk = todo[i : i + 100]
            try:
                found = self._arxiv_query(chunk)
            except (requests.RequestException, ET.ParseError):
                return None
            if found is None:  # one bad id fails the batch: ask singly
                found = {}
                for aid in chunk:
                    try:
                        found.update(self._arxiv_query([aid]) or {})
                    except (requests.RequestException, ET.ParseError):
                        return None
            for aid, meta in found.items():
                self.cache.put_json("arxiv", aid, meta)
            out.update(found)
        return out

    def _arxiv_query(self, ids):
        r = self.fetcher.get(
            "arxiv",
            S.ARXIV_API,
            params={"id_list": ",".join(ids), "max_results": len(ids)},
        )
        r.raise_for_status()
        return parse_arxiv_feed(r.text, ids)

    # -- the whole pass ---------------------------------------------------- #
    def resolve(self, items: list[Item]) -> list[dict]:
        """Resolve a batch of parsed Items.

        Returns one dict per item with pmid / pmcid / doi / meta and, when the
        item cannot go on to fetching, status + explanation (+ candidates).
        """
        res = [
            dict(
                item=it,
                pmid=it.pmid,
                pmcid=it.pmcid,
                doi=it.doi,
                meta=None,
                status=None,
                explanation=None,
                notes=list(it.notes),
                candidates=None,
            )
            for it in items
        ]

        def stop(r, status, why, **extra):
            r["status"], r["explanation"] = status, why
            r.update(extra)

        for r in res:
            if r["item"].error:
                stop(r, "invalid_identifier", r["item"].error)

        # ScienceDirect PII -> DOI
        for r in res:
            if r["status"] is None and r["item"].pii and not r["doi"]:
                doi = self.pii_to_doi(r["item"].pii)
                if doi:
                    r["doi"] = doi
                    r["notes"].append(
                        f"ScienceDirect PII {r['item'].pii} resolved to DOI "
                        f"{doi} via Crossref"
                    )
                else:
                    stop(
                        r,
                        "not_found",
                        f"could not map ScienceDirect PII {r['item'].pii} "
                        f"to a DOI; send the DOI shown on the article page",
                    )

        # PMCID -> PMID / DOI
        want = sorted({r["pmcid"] for r in res if r["status"] is None and r["pmcid"]})
        conv = self.idconv(want) if want else {}
        for r in res:
            if r["status"] is not None or not r["pmcid"]:
                continue
            rec = conv.get(r["pmcid"], {})
            if rec.get("status") == "error" or not rec:
                stop(
                    r,
                    "not_found",
                    f"{r['pmcid']} is not a PubMed Central article "
                    f"({rec.get('errmsg', 'unknown to the PMC ID converter')})",
                )
                continue
            pm = str(rec.get("pmid") or "") or None
            d = (rec.get("doi") or "").lower() or None
            if r["pmid"] and pm and r["pmid"] != pm:
                stop(
                    r,
                    "identifier_mismatch",
                    f"{r['pmcid']} belongs to PMID {pm}, not PMID {r['pmid']}",
                )
            elif r["doi"] and d and r["doi"] != d:
                stop(
                    r,
                    "identifier_mismatch",
                    f"{r['pmcid']} has DOI {d}, not {r['doi']}",
                )
            else:
                r["pmid"] = r["pmid"] or pm
                r["doi"] = r["doi"] or d

        # DOI -> PMID (PubMed does not index arXiv)
        want = [
            r["doi"]
            for r in res
            if r["status"] is None
            and r["doi"]
            and not r["pmid"]
            and not arxiv_id(r["doi"])
        ]
        found = self.dois_to_pmids(want) if want else {}
        for r in res:
            if r["status"] is None and r["doi"] and not r["pmid"] and r["doi"] in found:
                r["pmid"] = found[r["doi"]]

        # Title only -> PubMed search
        for r in res:
            it = r["item"]
            if r["status"] is not None or not it.title_only:
                continue
            hits = self.title_search(it.title)
            exact = [
                h
                for h in hits
                if normalise_title(h["title"]) == normalise_title(it.title)
            ]
            cands = [
                dict(
                    pmid=h["pmid"],
                    doi=h.get("doi") or None,
                    title=h["title"],
                    journal=h.get("journal"),
                    year=h.get("pub_date"),
                )
                for h in hits
            ]
            if len(exact) == 1:
                r["pmid"] = exact[0]["pmid"]
                r["notes"].append(f"matched by exact title to PMID {r['pmid']}")
            else:
                stop(
                    r,
                    "needs_identifier",
                    (
                        "no PubMed article has this exact title; "
                        if not exact
                        else "several PubMed articles share this title; "
                    )
                    + "pick the right one from 'candidates' and resend its PMID or DOI",
                    candidates=cands,
                )

        # PubMed metadata for every PMID
        recs = self.pubmed_records(
            [r["pmid"] for r in res if r["status"] is None and r["pmid"]]
        )
        for r in res:
            if r["status"] is not None or not r["pmid"]:
                continue
            rec = recs.get(r["pmid"])
            if not rec:
                stop(r, "not_found", f"PMID {r['pmid']} does not exist in PubMed")
                continue
            if r["doi"] and rec.get("doi") and r["doi"] != rec["doi"]:
                stop(
                    r,
                    "identifier_mismatch",
                    f"PMID {r['pmid']} has DOI {rec['doi']}, but the request gave DOI "
                    f"{r['doi']}: they are different articles",
                    meta=meta_from_pubmed(rec),
                )
                continue
            r["doi"] = r["doi"] or rec.get("doi") or None
            r["meta"] = meta_from_pubmed(rec)

        # arXiv preprint -> arXiv API metadata
        want = [
            arxiv_id(r["doi"])
            for r in res
            if r["status"] is None and not r["meta"] and arxiv_id(r["doi"])
        ]
        ax = self.arxiv_records(want) if want else {}
        for r in res:
            aid = arxiv_id(r["doi"])
            if r["status"] is not None or r["meta"] or not aid:
                continue
            if ax is None:
                r["notes"].append(
                    "the arXiv API did not answer; metadata from DataCite"
                )
            elif aid in ax:
                r["meta"] = ax[aid]
                r["notes"].append("arXiv preprint; metadata from arXiv")
                if ax[aid].get("published_doi"):
                    r["notes"].append(
                        f"published version: DOI {ax[aid]['published_doi']} "
                        f"(send that DOI for the journal version)"
                    )
            else:
                stop(
                    r,
                    "not_found",
                    f"arXiv has no paper with id {aid}; check it against "
                    f"the abstract page (arxiv.org/abs/<id>)",
                )

        # DOI outside PubMed -> Crossref (else DataCite) metadata, or confirm it exists
        for r in res:
            if r["status"] is not None or r["meta"] or not r["doi"]:
                continue
            cr = (
                {} if arxiv_id(r["doi"]) else self.crossref(r["doi"])
            )  # arXiv: DataCite
            if cr:
                r["meta"] = meta_from_crossref(cr)
                r["notes"].append("not indexed in PubMed; metadata from Crossref")
                continue
            dc = self.datacite(r["doi"])
            if dc:
                r["meta"] = meta_from_datacite(dc)
                r["notes"].append(
                    "not indexed in PubMed or Crossref; metadata from DataCite"
                )
                published = next(
                    (
                        x["relatedIdentifier"].lower()
                        for x in dc.get("relatedIdentifiers") or []
                        if x.get("relationType") == "IsVersionOf"
                        and x.get("relatedIdentifierType") == "DOI"
                    ),
                    None,
                )
                if published:
                    r["notes"].append(f"published version: DOI {published}")
                continue
            registered = self.doi_registered(r["doi"])
            if cr == {} and dc == {} and registered is False:
                stop(
                    r,
                    "not_found",
                    f"DOI {r['doi']} is not registered (doi.org does not "
                    f"know it); check it for typos",
                )
            else:
                r["meta"] = {
                    "title": None,
                    "journal": None,
                    "year": None,
                    "source": "none",
                }
                r["notes"].append(
                    "DOI exists but neither PubMed, Crossref nor DataCite "
                    "has metadata for it"
                )

        # PMID -> PMCID (decides whether PMC is worth asking)
        want = [
            r["pmid"]
            for r in res
            if r["status"] is None and r["pmid"] and not r["pmcid"]
        ]
        pmc = self.pmcids_for(want) if want else {}
        for r in res:
            if r["status"] is None and r["pmid"] and not r["pmcid"]:
                r["pmcid"] = pmc.get(r["pmid"])

        # Expected title cross-check
        for r in res:
            it = r["item"]
            if (
                r["status"] is None
                and it.title
                and not it.title_only
                and r["meta"]
                and r["meta"].get("title")
                and not title_matches(it.title, r["meta"]["title"])
            ):
                stop(
                    r,
                    "identifier_mismatch",
                    f'the identifier points to "{r["meta"]["title"]}", which does not '
                    f'match the expected title "{it.title}"; the identifier is '
                    f"probably wrong",
                )
        return res


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    """PubMed efetch XML -> one plain record per article."""
    root = ET.fromstring(xml_text)
    records = []
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        doi = ""
        for aid in article.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
                break
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            last, fore = author.findtext("LastName"), author.findtext("ForeName")
            if last and fore:
                authors.append(f"{fore} {last}")
            elif last:
                authors.append(last)
            elif author.findtext("CollectiveName"):
                authors.append(author.findtext("CollectiveName"))
        year = article.findtext(".//JournalIssue/PubDate/Year")
        medline_date = article.findtext(".//JournalIssue/PubDate/MedlineDate")
        mesh = [
            m.text
            for m in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName")
            if m.text
        ]
        records.append(
            {
                "pmid": pmid,
                "doi": doi,
                "title": "".join(article.find(".//ArticleTitle").itertext())
                if article.find(".//ArticleTitle") is not None
                else "",
                "abstract": " ".join(
                    "".join(t.itertext()) for t in article.iter("AbstractText")
                ).strip(),
                "authors": "; ".join(authors),
                "journal": article.findtext(".//Journal/Title", default="") or "",
                "pub_date": year or medline_date or "",
                "mesh_terms": "; ".join(mesh),
            }
        )
    return records


def meta_from_pubmed(rec: dict) -> dict:
    return {
        "title": rec.get("title"),
        "journal": rec.get("journal"),
        "year": rec.get("pub_date"),
        "authors": rec.get("authors"),
        "abstract": rec.get("abstract"),
        "mesh_terms": rec.get("mesh_terms"),
        "source": "pubmed",
    }


def meta_from_crossref(cr: dict) -> dict:
    year = None
    for k in ("published-print", "published-online", "issued"):
        parts = ((cr.get(k) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            year = str(parts[0])
            break
    authors = "; ".join(
        " ".join(x for x in (a.get("given"), a.get("family")) if x)
        for a in cr.get("author", [])[:50]
    )
    abstract = re.sub(r"<[^>]+>", " ", cr.get("abstract") or "")
    return {
        "title": " ".join(cr.get("title") or []) or None,
        "journal": " ".join(cr.get("container-title") or []) or None,
        "year": year,
        "authors": authors or None,
        "abstract": re.sub(r"\s+", " ", abstract).strip() or None,
        "publisher": cr.get("publisher"),
        "type": cr.get("type"),
        "source": "crossref",
    }


def meta_from_datacite(dc: dict) -> dict:
    names = [
        " ".join(x for x in (c.get("givenName"), c.get("familyName")) if x)
        or c.get("name")
        for c in (dc.get("creators") or [])[:50]
    ]
    abstract = next(
        (
            d.get("description")
            for d in dc.get("descriptions") or []
            if d.get("descriptionType") == "Abstract"
        ),
        None,
    )
    publisher = dc.get("publisher")
    return {
        "title": next(
            (t.get("title") for t in dc.get("titles") or [] if t.get("title")), None
        ),
        "journal": publisher
        if isinstance(publisher, str)
        else (publisher or {}).get("name"),
        "year": str(dc["publicationYear"]) if dc.get("publicationYear") else None,
        "authors": "; ".join(n for n in names if n) or None,
        "abstract": re.sub(r"\s+", " ", abstract).strip() if abstract else None,
        "type": (dc.get("types") or {}).get("resourceTypeGeneral"),
        "source": "datacite",
    }


def parse_arxiv_feed(xml: str, ids) -> dict | None:
    """{requested id: metadata} from an arXiv API Atom feed; None if arXiv answered
    with an error entry (a malformed id, which fails the whole query)."""
    root = ET.fromstring(xml)
    out = {}
    wanted = {i.lower(): i for i in ids}
    for e in root.findall("a:entry", ATOM):

        def text(tag, e=e):
            return re.sub(r"\s+", " ", e.findtext(tag, "", ATOM)).strip()

        if text("a:title") == "Error":
            return None
        # <id>http://arxiv.org/abs/hep-th/9901001v3</id> -> hep-th/9901001
        aid = re.sub(r"v\d+$", "", text("a:id").split("/abs/", 1)[-1]).lower()
        if aid not in wanted:
            continue
        cat = e.find("arxiv:primary_category", ATOM)
        out[wanted[aid]] = {
            "title": text("a:title") or None,
            "journal": "arXiv" + (f" ({cat.get('term')})" if cat is not None else ""),
            "year": text("a:published")[:4] or None,
            "authors": "; ".join(
                re.sub(r"\s+", " ", a.findtext("a:name", "", ATOM)).strip()
                for a in e.findall("a:author", ATOM)[:50]
            )
            or None,
            "abstract": text("a:summary") or None,
            "journal_ref": text("arxiv:journal_ref") or None,
            "published_doi": text("arxiv:doi").lower() or None,
            "source": "arxiv",
        }
    return out


__all__ = ["Resolver", "parse_pubmed_xml", "parse_arxiv_feed"]
