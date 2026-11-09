"""PubMed source scraper (NCBI E-utilities).

Two-step dance: ``esearch`` returns matching PMIDs (parked on the History
server), then ``efetch`` retrieves full XML records in batches. We key on the
Entrez date (``edat``) so we catch records — including ahead-of-print — as they
are added.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Ported from ``~/Tools/ResearchScraper/libs/pubmed/pubmed-scraper.py``.
"""

from __future__ import annotations

import asyncio
import json
import xml.etree.ElementTree as ET

from tools.retrieval.sources.base import BaseScraper, ProgressCB, Window
from tools.retrieval.sources.record import Record

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH = 200


def article_own_ids(art: ET.Element) -> tuple[str | None, str | None]:
    """The ``(doi, pmcid)`` of one ``PubmedArticle`` — its own, never a citation's.

    ``PubmedData`` also carries a ``ReferenceList`` whose cited papers each have
    an ``ArticleIdList`` of their own, so a ``.//ArticleIdList/ArticleId`` search
    picks up every reference's DOI and PMCID (and keeping the last one stored a
    cited paper's ids on most rows, Q-057). Read only the article's own list,
    falling back to the ``ELocationID`` DOI when PubMed's list has none.
    """
    doi = pmcid = None
    for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
        idtype = aid.get("IdType")
        text = (aid.text or "").strip() or None
        if idtype == "doi" and doi is None:
            doi = text
        elif idtype == "pmc" and pmcid is None:
            pmcid = text
    if doi is None:
        for el in art.findall("MedlineCitation/Article/ELocationID"):
            if el.get("EIdType") == "doi" and (el.text or "").strip():
                doi = el.text.strip()
                break
    return doi, pmcid


class PubMedScraper(BaseScraper):
    name = "PubMed"
    rate_per_sec = 3.0  # 3/s without key, 10/s with key.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.config.pubmed_api_key:
            self.rate_per_sec = 9.0
            self.limiter.min_interval = 1.0 / self.rate_per_sec

    def _common(self) -> dict:
        params = {
            "db": "pubmed",
            "tool": self.config.tool_name,
            "email": self.config.contact_email,
        }
        if self.config.pubmed_api_key:
            params["api_key"] = self.config.pubmed_api_key
        return params

    async def search(
        self, query: str, window: Window, progress: ProgressCB
    ) -> list[Record]:
        progress("running", 0, 0, "esearch…")

        # Step 1: esearch -> PMIDs on the history server.
        search_params = {
            **self._common(),
            "term": query,
            "datetype": "edat",
            "mindate": window.since_date,
            "maxdate": window.until_date,
            "retmax": "10000",
            "usehistory": "y",
            "retmode": "json",
        }
        # NCBI occasionally returns a non-JSON throttle/error body even with a
        # 200; retry the parse a few times before giving up.
        payload = {}
        for attempt in range(4):
            resp = await self._request(
                "GET", f"{BASE}/esearch.fcgi", params=search_params
            )
            async with resp:
                if resp.status != 200:
                    raise RuntimeError(f"PubMed esearch HTTP {resp.status}")
                text = await resp.text()
            try:
                payload = json.loads(text).get("esearchresult", {})
                break
            except (json.JSONDecodeError, ValueError) as exc:
                if attempt == 3:
                    raise RuntimeError(
                        f"PubMed esearch returned non-JSON: {text[:120]!r}"
                    ) from exc
                await asyncio.sleep(2 ** attempt)

        idlist = payload.get("idlist", [])
        webenv = payload.get("webenv")
        query_key = payload.get("querykey")
        total = int(payload.get("count", len(idlist)) or 0)

        records: list[Record] = []
        if not idlist or not webenv:
            progress("done", 0, 0, "no results")
            return records

        # Step 2: efetch full records in batches via the history server.
        page = 0
        for retstart in range(0, len(idlist), BATCH):
            fetch_params = {
                **self._common(),
                "WebEnv": webenv,
                "query_key": query_key,
                "retmode": "xml",
                "retstart": str(retstart),
                "retmax": str(BATCH),
            }
            resp = await self._request(
                "GET", f"{BASE}/efetch.fcgi", params=fetch_params
            )
            async with resp:
                if resp.status != 200:
                    raise RuntimeError(f"PubMed efetch HTTP {resp.status}")
                xml_text = await resp.text()

            page += 1
            records.extend(self._parse_xml(xml_text))
            progress("running", len(records), page, f"fetched {len(records)}/{total}")

        progress("done", len(records), page, "complete")
        return records

    @staticmethod
    def _parse_xml(xml_text: str) -> list[Record]:
        out: list[Record] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return out

        for art in root.findall(".//PubmedArticle"):
            medline = art.find("MedlineCitation")
            if medline is None:
                continue
            article = medline.find("Article")
            pmid = (medline.findtext("PMID") or "").strip()

            title = ""
            if article is not None:
                title = article.findtext("ArticleTitle") or ""

            # Abstract may contain several labeled sections.
            abstract_parts = []
            if article is not None:
                for ab in article.findall(".//Abstract/AbstractText"):
                    label = ab.get("Label")
                    text = "".join(ab.itertext()).strip()
                    if text:
                        abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = "\n".join(abstract_parts) or None

            authors = []
            if article is not None:
                for a in article.findall(".//AuthorList/Author"):
                    last = a.findtext("LastName")
                    fore = a.findtext("ForeName") or a.findtext("Initials")
                    coll = a.findtext("CollectiveName")
                    if last:
                        authors.append(f"{last}, {fore}" if fore else last)
                    elif coll:
                        authors.append(coll)

            doi, pmcid = article_own_ids(art)

            # Year / date.
            year = None
            pub_date = None
            if article is not None:
                ad = article.find("ArticleDate")
                jd = article.find(".//Journal/JournalIssue/PubDate")
                ystr = None
                if ad is not None:
                    y = ad.findtext("Year")
                    m = ad.findtext("Month") or "01"
                    d = ad.findtext("Day") or "01"
                    if y:
                        ystr = y
                        if m.isdigit() and d.isdigit():
                            pub_date = f"{y}-{int(m):02d}-{int(d):02d}"
                        else:
                            pub_date = y
                elif jd is not None:
                    ystr = jd.findtext("Year")
                    pub_date = ystr
                if ystr and ystr.isdigit():
                    year = int(ystr)

            venue = None
            if article is not None:
                venue = article.findtext(".//Journal/Title") or article.findtext(
                    ".//Journal/ISOAbbreviation"
                )

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

            out.append(Record(
                source="PubMed",
                source_id=pmid,
                title=title,
                doi=doi,
                pmid=pmid,
                pmcid=pmcid,
                abstract=abstract,
                authors=authors,
                year=year,
                publication_date=pub_date,
                venue=venue,
                url=url,
            ))
        return out
