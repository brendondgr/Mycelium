"""OpenAlex source scraper.

Single ``/works`` endpoint with a ``filter`` parameter and cursor pagination.
We filter on ``from_publication_date`` / ``to_publication_date`` (free tier)
combined with a full-text ``search``. Abstracts arrive as an inverted index and
are rebuilt into plain text.

Docs: https://docs.openalex.org/api-entities/works
Ported from ``~/Tools/ResearchScraper/libs/openalex/openalex-scraper.py``.
"""

from __future__ import annotations

from tools.retrieval.sources.base import BaseScraper, ProgressCB, Window
from tools.retrieval.sources.record import Record, rebuild_inverted_abstract

BASE_URL = "https://api.openalex.org/works"

SELECT_FIELDS = ",".join([
    "id", "ids", "doi", "title", "display_name",
    "abstract_inverted_index", "publication_date", "publication_year",
    "authorships", "primary_location", "best_oa_location",
])


class OpenAlexScraper(BaseScraper):
    name = "OpenAlex"
    rate_per_sec = 8.0  # API allows up to 100/s; stay polite.

    async def search(
        self, query: str, window: Window, progress: ProgressCB
    ) -> list[Record]:
        records: list[Record] = []
        cursor = "*"
        page = 0
        filt = (
            f"from_publication_date:{window.since_date},"
            f"to_publication_date:{window.until_date}"
        )

        progress("running", 0, 0, "querying…")
        while cursor:
            params = {
                "filter": filt,
                "search": query,
                "select": SELECT_FIELDS,
                "per-page": "200",
                "cursor": cursor,
            }
            if self.config.contact_email:
                params["mailto"] = self.config.contact_email
            if self.config.openalex_api_key:
                params["api_key"] = self.config.openalex_api_key

            resp = await self._request("GET", BASE_URL, params=params)
            async with resp:
                if resp.status != 200:
                    body = (await resp.text())[:200]
                    raise RuntimeError(f"OpenAlex HTTP {resp.status}: {body}")
                data = await resp.json()

            page += 1
            for work in data.get("results", []):
                records.append(self._parse(work))
            cursor = (data.get("meta") or {}).get("next_cursor")
            progress("running", len(records), page, f"page {page}")
            if not data.get("results"):
                break

        progress("done", len(records), page, "complete")
        return records

    @staticmethod
    def _parse(work: dict) -> Record:
        ids = work.get("ids") or {}
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])
        ]
        authors = [a for a in authors if a]

        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        oa = work.get("best_oa_location") or {}

        return Record(
            source="OpenAlex",
            source_id=work.get("id", ""),
            title=work.get("title") or work.get("display_name") or "",
            doi=work.get("doi") or ids.get("doi"),
            pmid=ids.get("pmid"),
            pmcid=ids.get("pmcid"),
            abstract=rebuild_inverted_abstract(work.get("abstract_inverted_index")),
            authors=authors,
            year=work.get("publication_year"),
            publication_date=work.get("publication_date"),
            venue=source.get("display_name"),
            url=primary.get("landing_page_url") or work.get("id"),
            pdf_url=oa.get("pdf_url"),
        )
