"""Semantic Scholar source scraper.

Uses the bulk search endpoint (``/paper/search/bulk``): up to 1000 results per
page, continuation-``token`` pagination, sortable by date. ``externalIds`` is
the de-dup goldmine (DOI / PMID / PMCID / ArXiv). Abstracts are frequently
null — that is expected, not an error.

Docs: https://api.semanticscholar.org/api-docs/graph
Ported from ``~/Tools/ResearchScraper/libs/semanticscholar/semanticscholar-scraper.py``.
"""

from __future__ import annotations

from .base import BaseScraper, ProgressCB, Window
from .record import Record

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

FIELDS = ",".join([
    "title", "abstract", "externalIds", "publicationDate", "year",
    "authors", "venue", "openAccessPdf", "url",
])


class SemanticScholarScraper(BaseScraper):
    name = "SemanticScholar"
    rate_per_sec = 1.0  # Authenticated bulk/search limit is ~1 req/s.

    async def search(
        self, query: str, window: Window, progress: ProgressCB
    ) -> list[Record]:
        records: list[Record] = []
        token: str | None = None
        page = 0

        headers = {}
        if self.config.semanticscholar_api_key:
            headers["x-api-key"] = self.config.semanticscholar_api_key

        progress("running", 0, 0, "querying…")
        while True:
            params = {
                "query": query,
                "fields": FIELDS,
                "publicationDateOrYear": f"{window.since_date}:{window.until_date}",
                "sort": "publicationDate:desc",
            }
            if token:
                params["token"] = token

            resp = await self._request("GET", BASE_URL, params=params, headers=headers)
            async with resp:
                if resp.status != 200:
                    body = (await resp.text())[:200]
                    raise RuntimeError(f"SemanticScholar HTTP {resp.status}: {body}")
                data = await resp.json()

            page += 1
            for paper in data.get("data") or []:
                records.append(self._parse(paper))
            token = data.get("token")
            progress("running", len(records), page, f"page {page}")
            if not token or not (data.get("data")):
                break

        progress("done", len(records), page, "complete")
        return records

    @staticmethod
    def _parse(paper: dict) -> Record:
        ext = paper.get("externalIds") or {}
        authors = [a.get("name", "") for a in (paper.get("authors") or [])]
        authors = [a for a in authors if a]
        oa = paper.get("openAccessPdf") or {}
        pub_date = paper.get("publicationDate")
        year = paper.get("year")
        if not year and pub_date:
            year = int(pub_date[:4]) if pub_date[:4].isdigit() else None

        return Record(
            source="SemanticScholar",
            source_id=str(paper.get("paperId") or ext.get("CorpusId") or ""),
            title=paper.get("title") or "",
            doi=ext.get("DOI"),
            pmid=ext.get("PubMed"),
            pmcid=ext.get("PubMedCentral"),
            arxiv=ext.get("ArXiv"),
            abstract=paper.get("abstract"),
            authors=authors,
            year=year,
            publication_date=pub_date,
            venue=paper.get("venue"),
            url=paper.get("url"),
            pdf_url=oa.get("url"),
        )
