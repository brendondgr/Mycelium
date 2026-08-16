"""CORE / ICORE conference rankings: one GET, 987 rows, no deadlines at all.

The quality half of the trust layer. It answers "how good is this venue?" and
nothing else — no dates, no description, no location — so it is a join target,
not a record source.

**Disabled by default.** ``portal.core.edu.au/robots.txt`` carries a 38-agent
group ending ``Disallow: /`` that names ``ClaudeBot``, ``anthropic-ai``,
``Claude-User``, ``GPTBot`` and ``CCBot`` among others. Our collector sends its
own identifying user agent and so falls under ``User-agent: *``, which permits
``/conf-ranks/`` — but the operator has opted out of AI crawling *by name*, and
this repository's ranking stage embeds text. That is a judgement for the
maintainer, not a default to slip past, so the adapter reports why it is off
until ``CONFERENCES_ENABLE_CORE=1`` is set. Never spoof a browser UA to get
around it.

There is also **no licence**: an asserted "© 2013 Computing Research & Education"
with no grant of reuse. Internal use and derived display are common practice, but
always show the edition tag ("ICORE2026 rank A*") with attribution, and never
offer the file for bulk download.
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any

from apps.scraper.collect.conferences.registry.cache import CORE_FILE, write_cache
from apps.scraper.collect.core.http import PoliteClient

PORTAL = "https://portal.core.edu.au/conf-ranks/"
CURRENT_EDITION = "ICORE2026"

#: Every edition the portal's own <form> offers.
EDITIONS = (
    "ICORE2026", "CORE2023", "CORE2021", "CORE2020", "CORE2018",
    "CORE2017", "CORE2014", "CORE2013", "ERA2010", "CORE2008",
)

ENABLE_FLAG = "CONFERENCES_ENABLE_CORE"

#: The export is ~99 KB for 987 rows.
MIN_EXPORT_BYTES = 20_000

#: The CSV has **no header row**, so column meaning is positional only. Each was
#: established by comparing against the portal's own labelled HTML listing and
#: its detail pages.
COLUMNS = (
    "id",            # 0 portal conference id, the only unique key
    "title",         # 1 full title, sometimes with a leading space
    "acronym",       # 2 not unique: 15 collide within one edition alone
    "edition",       # 3 which ranking round this row belongs to
    "rank",          # 4 free text, see BUCKETS
    "_unused",       # 5 a Yes/No flag that disagrees with the real DBLP link in
                     #   10 of 50 sampled rows, in both directions. Dropped.
    "for1",          # 6 primary Field of Research code
    "for2",          # 7 secondary, may be empty
    "for3",          # 8 tertiary, may be empty
)
EXPECTED_FIELDS = len(COLUMNS)

#: Ranks are uncontrolled free text — "National: USA", "National:USA",
#: "National Russia", "National: Czecholslovakia" [sic] all appear, and case
#: varies on the non-rank tags too. Normalise by case-folded prefix, never by
#: exact match.
BUCKETS: tuple[tuple[str, str], ...] = (
    ("a*", "a_star"),
    ("australasian b", "australasian_b"),
    ("australasian c", "australasian_c"),
    ("australasian", "australasian"),
    ("national", "national"),
    ("regional", "regional"),
    ("journal published", "journal_published"),
    ("multiconference", "multiconference"),
    ("unranked", "unranked"),
    ("tbr", "to_be_ranked"),
    ("a", "a"),
    ("b", "b"),
    ("c", "c"),
    ("l", "l"),
)

#: Field-of-Research names. Hardcoded rather than fetched: 13 current codes plus
#: the legacy ones, from the portal's own linked PDF. `CSE` is not numeric and
#: `0806` must not become `806`, so codes stay strings throughout.
FOR_CODES: dict[str, str] = {
    "46": "Information and Computing Sciences",
    "4601": "Applied computing",
    "4602": "Artificial intelligence",
    "4603": "Computer vision and multimedia computation",
    "4604": "Cybersecurity and privacy",
    "4605": "Data management and data science",
    "4606": "Distributed computing and systems software",
    "4607": "Graphics, augmented reality and games",
    "4608": "Human-centred computing",
    "4611": "Machine learning",
    "4612": "Software engineering",
    "4613": "Theory of computation",
    "CSE": "Computer Systems Engineering",
    # Legacy ANZSRC-2008, which the portal marks with a dagger as possibly out
    # of use. Kept so an old code renders as something rather than as a number.
    "08": "Information and Computing Sciences (2008)",
    "0801": "Artificial Intelligence and Image Processing (2008)",
    "0802": "Computation Theory and Mathematics (2008)",
    "0803": "Computer Software (2008)",
    "0804": "Data Format (2008)",
    "0805": "Distributed Computing (2008)",
    "0806": "Information Systems (2008)",
    "0807": "Library and Information Studies (2008)",
    "0899": "Other Information and Computing Sciences (2008)",
    "09": "Engineering (2008)",
    "0905": "Civil Engineering (2008)",
    "0906": "Electrical and Electronic Engineering (2008)",
    "1005": "Communications Technologies (2008)",
    "1201": "Architecture (2008)",
    "1503": "Business and Management (2008)",
}


def export_url(edition: str = CURRENT_EDITION) -> str:
    if edition not in EDITIONS:
        raise ValueError(f"unknown CORE edition: {edition!r} (known: {', '.join(EDITIONS)})")
    return (
        f"{PORTAL}?search=&by=all&source={edition}&sort=atitle&page=1&do=Export"
    )


def available() -> tuple[bool, str]:
    if os.environ.get(ENABLE_FLAG) == "1":
        return True, ""
    return False, (
        "CORE's robots.txt names ClaudeBot/anthropic-ai/GPTBot and disallows them. "
        "Our UA falls under 'User-agent: *' and is permitted, but the operator has "
        f"opted out of AI crawling by name. Set {ENABLE_FLAG}=1 to accept that "
        "trade-off deliberately."
    )


def fetch_rankings(
    client: PoliteClient, directory: Path, *, edition: str = CURRENT_EDITION
) -> dict[str, Any]:
    """One request. Rankings change every ~3 years, so this is a slow-schedule job."""
    url = export_url(edition)
    response = client.get(url, min_bytes=MIN_EXPORT_BYTES)
    payload = parse_export(response.text(), edition=edition)
    write_cache(directory, CORE_FILE, payload)
    return payload


def parse_export(text: str, *, edition: str = CURRENT_EDITION) -> dict[str, Any]:
    """Parse the export. Pure; no network.

    Must go through ``csv.reader``: the file has no header, and 100 of 987 titles
    contain commas inside quotes. Splitting on commas corrupts 65 rows while
    looking perfectly healthy.
    """
    rows: list[dict[str, Any]] = []
    problems: list[str] = []

    for line_number, fields in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not fields or not any(field.strip() for field in fields):
            continue
        if len(fields) != EXPECTED_FIELDS:
            # A column reorder or insert upstream would silently mis-assign FoR
            # codes to ranks. Refuse the row and say so.
            problems.append(f"line {line_number}: {len(fields)} fields, expected {EXPECTED_FIELDS}")
            continue

        record = dict(zip(COLUMNS, fields, strict=True))
        row_edition = record["edition"].strip()
        if row_edition != edition:
            problems.append(
                f"line {line_number}: edition {row_edition!r} != requested {edition!r}"
            )
            continue

        rank = record["rank"].strip()
        rows.append(
            {
                "id": record["id"].strip(),
                # Two titles begin with a leading space, which sorts them to the
                # top of an atitle export.
                "title": record["title"].strip(),
                "acronym": record["acronym"].strip(),
                "edition": row_edition,
                "rank": rank,  # verbatim, always
                "bucket": bucket_for(rank),
                "field_codes": [
                    code.strip()
                    for code in (record["for1"], record["for2"], record["for3"])
                    if code.strip()
                ],
                "dblp_key": "",  # HTML-only; a separate opt-in scrape supplies it
            }
        )

    return {
        "source": "core_rankings",
        "edition": edition,
        "license": "none stated; © Computing Research & Education",
        "rankings": rows,
        "problems": problems,
    }


def bucket_for(rank: str) -> str:
    """Normalise a free-text rank into a stable bucket, keeping the raw value.

    "Unranked" is deliberately its own bucket and not a synonym for absent. The
    ranking body describes it as assessed-with-no-decision, offering "an
    assurance that they are legitimate venues" — a weak positive. Absent from the
    export means nobody submitted it, it was de-listed, or it is not primarily
    computing, and the export cannot tell those apart.
    """
    text = (rank or "").strip().lower()
    if not text:
        return "unspecified"
    for prefix, bucket in BUCKETS:
        if text.startswith(prefix):
            return bucket
    return "other"


def for_code_name(code: str) -> str:
    return FOR_CODES.get(str(code).strip(), "")
