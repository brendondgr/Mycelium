"""Backfill richer text for records whose feed was too terse to rank on.

Retrieval partly measures how much text a record has, so a source with a terse
feed is systematically out-ranked by a verbose one regardless of fit. Measured
before this existed: NIH was 16.3% of the corpus and 4.4% of matches — 3.7x
under-represented — because its feed gives an 826-character ``Purpose`` abstract
against the EU's 8,482-character topic text. Worse, 372 NIH-numbered records had
no NIH data at all, only Grants.gov's thinner copy, because the active-FOA XML
does not list them.

Two properties this shares with the rest of the pipeline, both load-bearing:

* **Fetch and parse stay separate.** Enrichment fetches pages and writes them to
  the raw store. Applying them reads from disk and touches no network, so a
  parsing fix re-runs offline over pages already fetched.
* **A 404 is an answer.** Not every derived URL resolves — measured hit rate on
  the NIH Guide archive is about 1 in 4, because FY27 and FY28 numbers are
  posted to Grants.gov before they appear in the Guide. A miss is recorded and
  skipped, never retried in a loop and never confused with a fetch failure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from apps.scraper.collect.core.http import FetchError, PoliteClient
from apps.scraper.collect.grants.normalize import clean_text, html_to_text
from apps.scraper.collect.grants.record import Opportunity

#: Below this many characters a description is too thin to rank on. Chosen from
#: the corpus: NIH's Purpose abstracts average 826 and EU topic text 8,482, so
#: anything under this is losing to length rather than to fit.
THIN_DESCRIPTION = 1500

#: Where the NIH Guide publishes each document kind.
NIH_GUIDE_FOLDERS = {
    "PA": "pa-files",
    "PAR": "pa-files",
    "PAS": "pa-files",
    "NOFO": "pa-files",
    "RFA": "rfa-files",
    "NOT": "notice-files",
}
NIH_GUIDE_URL = "https://grants.nih.gov/grants/guide/{folder}/{number}.html"
NIH_NUMBER = re.compile(r"^(PA|PAR|PAS|RFA|NOT|NOFO)-", re.IGNORECASE)

#: Both sites wrap the real content in navigation and footer chrome, and both
#: emit the *same* chrome on every page. Left in, a few kilobytes of "Skip to
#: main content / An official website of the United States government / .gov"
#: would open every record's embedded text, so every record in that source would
#: look alike to the encoder — the exact opposite of what the vector is for.
#: These bounds are read off the real pages, not guessed.
NIH_BODY_START = re.compile(r"(Section\s+I\.|Purpose\b|Notice of (Funding|Special))", re.IGNORECASE)
NIH_BODY_END = re.compile(
    r"(Section\s+VIII\.|Weekly TOC for this Announcement|NIH Funding Opportunities and Notices)",
    re.IGNORECASE,
)

#: NSF programme pages run: masthead, site nav, breadcrumb, a standing
#: "Important information for proposers" block, then the programme summary and
#: Synopsis, then a global footer.
NSF_BODY_START = re.compile(
    r"(All proposals must be submitted in accordance[^\n]*\n|Print this Page\s*\n)",
    re.IGNORECASE,
)
NSF_BODY_END = re.compile(r"\n\s*Footer\s*\n", re.IGNORECASE)
#: The standing policy block sits between the breadcrumb and the real summary and
#: is byte-identical across programmes.
NSF_POLICY_BLOCK = re.compile(
    r"Important information for proposers and award recipients.*?"
    r"(?=Supports |Synopsis|The .{3,60} Program)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class EnrichmentPlan:
    """What is worth fetching, and why. Reported before anything is requested."""

    nih_pages: list[tuple[str, str]] = field(default_factory=list)  # (number, url)
    nsf_pages: list[tuple[str, str]] = field(default_factory=list)  # (key, url)

    @property
    def total(self) -> int:
        return len(self.nih_pages) + len(self.nsf_pages)

    def as_lines(self) -> list[str]:
        return [
            f"  nih_guide  {len(self.nih_pages):4} announcement pages "
            "(NIH-numbered records with no NIH-native text)",
            f"  nsf        {len(self.nsf_pages):4} programme pages (descriptions under "
            f"{THIN_DESCRIPTION} characters)",
        ]


def nih_guide_url(number: str) -> str:
    """The Guide URL for an announcement number, or "" if the prefix is unknown."""
    prefix = clean_text(number).split("-")[0].upper()
    folder = NIH_GUIDE_FOLDERS.get(prefix)
    return NIH_GUIDE_URL.format(folder=folder, number=clean_text(number).upper()) if folder else ""


def plan_enrichment(records: Iterable[Opportunity], *, limit: int | None = None) -> EnrichmentPlan:
    """Decide what to fetch without fetching anything.

    Separated so the cost is visible and arguable before a few hundred requests
    are sent to a public agency's web server.
    """
    plan = EnrichmentPlan()
    for record in records:
        number = record.opportunity_number or ""
        # Source first, then the number pattern. Keyed the other way round, an
        # NSF record that happened to carry an NIH-shaped number would be sent
        # to grants.nih.gov to be told, correctly, that it does not exist.
        if record.source == "nsf":
            if record.source_url and len(record.description) < THIN_DESCRIPTION:
                plan.nsf_pages.append((record.stable_key, record.source_url))
        elif NIH_NUMBER.match(number) and "nih_guide" not in record.contributing_sources:
            url = nih_guide_url(number)
            if url:
                plan.nih_pages.append((number, url))

    if limit is not None:
        plan.nih_pages = plan.nih_pages[:limit]
        plan.nsf_pages = plan.nsf_pages[:limit]
    return plan


def fetch_pages(client: PoliteClient, plan: EnrichmentPlan) -> dict[str, dict[str, str]]:
    """Fetch every planned page. Network only — nothing is parsed or applied here.

    Misses are recorded rather than dropped: "we looked and NIH does not publish
    this one" is a different fact from "we never looked", and only the first can
    stop a later run from asking again.
    """
    pages: dict[str, dict[str, str]] = {"nih_guide": {}, "nsf": {}, "misses": {}}

    for key, url in plan.nih_pages:
        try:
            pages["nih_guide"][key] = client.get(url).text()
        except FetchError as exc:
            pages["misses"][key] = str(exc)

    for key, url in plan.nsf_pages:
        try:
            pages["nsf"][key] = client.get(url).text()
        except FetchError as exc:
            pages["misses"][key] = str(exc)

    return pages


# --- applying, offline ----------------------------------------------------


def _between(text: str, start: re.Pattern[str], end: re.Pattern[str]) -> str:
    match = start.search(text)
    if match:
        text = text[match.end() :]
    match = end.search(text)
    if match:
        text = text[: match.start()]
    return text.strip()


def nih_announcement_text(html: str) -> str:
    """The announcement body, with the Guide's site chrome removed.

    A Guide page is ~150 KB, most of it navigation and boilerplate repeated
    verbatim on every announcement.
    """
    text = html_to_text(html)
    match = NIH_BODY_START.search(text)
    if match:
        text = text[match.start() :]
    match = NIH_BODY_END.search(text)
    if match:
        text = text[: match.start()]
    return text.strip()


def nsf_programme_text(html: str) -> str:
    """The programme summary and synopsis, with NSF's site chrome removed.

    Without this the first 700 characters of every enriched NSF record were
    "Skip to main content / An official website of the United States government
    / A lock (LockLocked padlock)" — identical across all 24, and the only part
    the encoder would have got to before its token limit.
    """
    text = html_to_text(html)
    text = _between(text, NSF_BODY_START, NSF_BODY_END)
    return NSF_POLICY_BLOCK.sub("", text).strip()


def apply_enrichment(
    records: list[Opportunity], pages: dict[str, dict[str, str]]
) -> tuple[int, int]:
    """Merge fetched page text into records. No network.

    Returns (records improved, records left alone). Text is only replaced when
    the fetched version is genuinely longer — a page that yields less than the
    feed already had is a parse miss, not an improvement, and overwriting would
    make things worse while reporting a success.
    """
    nih = pages.get("nih_guide") or {}
    nsf = pages.get("nsf") or {}
    improved = 0

    for record in records:
        html = nih.get(record.opportunity_number or "") or nsf.get(record.stable_key)
        if not html:
            continue
        body = (
            nih_announcement_text(html)
            if record.opportunity_number in nih
            else nsf_programme_text(html)
        )
        if len(body) <= len(record.description):
            continue
        record.description = body
        if record.opportunity_number in nih and "nih_guide" not in record.contributing_sources:
            # The text now comes from NIH even though the record was assembled
            # from Grants.gov, and merge precedence downstream needs to know.
            record.contributing_sources = [*record.contributing_sources, "nih_guide"]
        improved += 1

    return improved, len(records) - improved
