"""dblp venue identity, in one SPARQL request.

**This source carries no deadlines and never will.** It exists to answer two
questions: *which canonical venue is this acronym?* and *has this venue actually
been running?* The venue key it returns is the closest thing to a universal
conference identifier that exists, and the indexed-proceedings-year count is the
longevity half of the trust signal.

**Why SPARQL and not the venue search API.** Two findings make this
non-negotiable rather than a preference:

1. ``dblp.org/robots.txt`` carries ``Disallow: /search``, ``Disallow:
   /search/venue`` and ``Disallow: /*.json``. Read literally, a robots-respecting
   client may not call the venue search API at all — it is under ``/search/venue``
   and it ends in ``format=json``.
2. The search host answers **429 on the fourth request inside 1.4 seconds** and
   then stops speaking TCP entirely, host-wide, for 80–130 seconds. Continued
   probing extends the ban.

One POST to the SPARQL endpoint returns the complete registry — 9,325 venues with
titles, former titles, homepage, Wikidata QID and the year counts already
aggregated — in about 8 MB and five seconds. Resolving a thousand acronyms
through the search API would be a thousand requests, roughly 67 minutes, and
would return strictly less.

Licence: **CC0 1.0**, covering all metadata and every export format. Attribution
requested, not required.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from apps.scraper.collect.conferences.registry.cache import DBLP_FILE, write_cache
from apps.scraper.collect.core.http import PoliteClient

SPARQL_ENDPOINT = "https://sparql.dblp.org/sparql"

#: One query for the whole registry. The GROUP BY collapses the year rows into a
#: count, so the longevity signal costs no extra request — it is not available
#: from the search API at any price.
REGISTRY_QUERY = """
PREFIX dblp: <https://dblp.org/rdf/schema#>
SELECT ?stream ?class ?primary ?title ?titleKind
       (COUNT(DISTINCT ?y) AS ?nYears) (MIN(?y) AS ?firstYear) (MAX(?y) AS ?lastYear)
       (SAMPLE(?w) AS ?webpage) (SAMPLE(?wd) AS ?wikidata)
WHERE {
  ?stream a dblp:Stream ; a ?class ; dblp:primaryStreamTitle ?primary .
  FILTER(?class != dblp:Stream)
  { ?stream dblp:streamTitle ?title .       BIND("current" AS ?titleKind) }
  UNION
  { ?stream dblp:formerStreamTitle ?title . BIND("former"  AS ?titleKind) }
  OPTIONAL { ?stream dblp:webpage ?w }
  OPTIONAL { ?stream dblp:wikidata ?wd }
  OPTIONAL { ?e dblp:publishedInStream ?stream ; dblp:yearOfPublication ?y }
}
GROUP BY ?stream ?class ?primary ?title ?titleKind
ORDER BY ?stream ?titleKind ?title
"""

#: dblp explicitly asserting two streams are *not* the same venue. A
#: hand-curated do-not-merge list, worth honouring before any heuristic runs.
DIFFERENT_FROM_QUERY = """
PREFIX dblp: <https://dblp.org/rdf/schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
SELECT ?a ?b WHERE { ?a a dblp:Conference ; owl:differentFrom ?b . }
"""

#: The response is ~8 MB. Anything tiny is an error page, not the registry.
MIN_REGISTRY_BYTES = 100_000

#: dblp publishes no acronym predicate at all, so it has to come out of the
#: trailing parenthetical of the curated title. This recovers ~77% of venues.
_TRAILING_ACRONYM = re.compile(r"\(([^()]{1,20})\)\s*$")
_STREAM_PREFIX = "https://dblp.org/streams/"

#: Search-API `type` strings map 1:1 onto these RDF classes.
_CLASS_NAMES = {
    "Conference": "Conference or Workshop",
    "Journal": "Journal",
    "Series": "Series",
    "Repository": "Repository",
}


def fetch_registry(client: PoliteClient, directory: Path) -> dict[str, Any]:
    """Pull the whole venue registry and cache it. One or two requests."""
    response = client.post_raw(
        SPARQL_ENDPOINT,
        REGISTRY_QUERY.encode("utf-8"),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json",
        },
        min_bytes=MIN_REGISTRY_BYTES,
    )
    payload = parse_registry(response.json())

    # Optional and never fatal: without it we lose a do-not-merge list, not
    # identity.
    try:
        edges = client.post_raw(
            SPARQL_ENDPOINT,
            DIFFERENT_FROM_QUERY.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        _attach_different_from(payload, edges.json())
    except Exception:  # noqa: BLE001
        pass

    write_cache(directory, DBLP_FILE, payload)
    return payload


def parse_registry(results: Any) -> dict[str, Any]:
    """SPARQL-results-JSON to the cache shape. Pure; no network.

    The query returns one row per (stream, title) pair, so rows must be grouped
    by stream — ``conf/sigmod`` carries both "ACM SIGMOD Conference (SIGMOD)" and
    "International Conference on Management of Data (SIGMOD)", and 840
    conferences carry a former title as well.
    """
    bindings = (results or {}).get("results", {}).get("bindings", [])
    grouped: dict[str, dict[str, Any]] = {}

    for row in bindings:
        stream = _value(row, "stream")
        if not stream.startswith(_STREAM_PREFIX):
            continue
        key = stream[len(_STREAM_PREFIX) :]
        venue = grouped.setdefault(
            key,
            {
                "key": key,
                "kind": key.split("/", 1)[0],
                "class": _CLASS_NAMES.get(_value(row, "class").rsplit("#", 1)[-1], ""),
                "primary_title": _value(row, "primary"),
                "titles": [],
                "former_titles": [],
                "acronyms": [],
                "n_years": 0,
                "first_year": None,
                "last_year": None,
                "webpage": _value(row, "webpage"),
                "wikidata": _value(row, "wikidata"),
                "different_from": [],
            },
        )

        title = _value(row, "title")
        kind = _value(row, "titleKind")
        if title:
            # Former titles are the ICS -> ITCS trap in one direction and the
            # only way to resolve a renamed venue in the other, so they are kept
            # but kept *separate*.
            bucket = "titles" if kind == "current" else "former_titles"
            if title not in venue[bucket]:
                venue[bucket].append(title)
            acronym = _acronym_of(title)
            if acronym and acronym not in venue["acronyms"]:
                venue["acronyms"].append(acronym)

        venue["n_years"] = max(venue["n_years"], _int(row, "nYears"))
        first, last = _int(row, "firstYear"), _int(row, "lastYear")
        if first:
            venue["first_year"] = min(venue["first_year"] or first, first)
        if last:
            venue["last_year"] = max(venue["last_year"] or last, last)

    return {"source": "dblp", "license": "CC0-1.0", "venues": list(grouped.values())}


def _attach_different_from(payload: dict[str, Any], results: Any) -> None:
    edges: dict[str, list[str]] = defaultdict(list)
    for row in (results or {}).get("results", {}).get("bindings", []):
        left, right = _value(row, "a"), _value(row, "b")
        if left.startswith(_STREAM_PREFIX) and right.startswith(_STREAM_PREFIX):
            edges[left[len(_STREAM_PREFIX) :]].append(right[len(_STREAM_PREFIX) :])
    for venue in payload["venues"]:
        if venue["key"] in edges:
            venue["different_from"] = edges[venue["key"]]


def _acronym_of(title: str) -> str:
    """The trailing parenthetical, which is where dblp keeps the acronym.

    Never derive a dblp *key* from an acronym: NeurIPS is ``conf/nips``, ITCS is
    ``conf/innovations``, ICSME is ``conf/icsm``. The slug and the acronym
    routinely disagree.
    """
    match = _TRAILING_ACRONYM.search(title or "")
    return match.group(1).strip() if match else ""


def _value(row: dict[str, Any], name: str) -> str:
    # Optional projections are *omitted keys* in SPARQL-results-JSON, not nulls.
    return str((row.get(name) or {}).get("value", "") or "")


def _int(row: dict[str, Any], name: str) -> int:
    raw = _value(row, name)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0
