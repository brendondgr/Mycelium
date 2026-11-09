"""The fulltext write door: everything another tool, the platform, or a later
API may call to make the tool do something.

    check(identifiers)                      can these papers be had? fetches nothing
    request(identifiers, requester=…)       get them (now, or on a worker)
    retry(requests)                         run transient failures again
    sources()                               which sources this instance can use

Identifiers are anything the engine parses: PMIDs, PMCIDs, DOIs, arXiv ids,
PubMed / PMC / doi.org / publisher / arXiv URLs, or dicts with explicit fields
(``{"pmid": …, "doi": …, "title": …}``).
"""

from __future__ import annotations

from . import jobs, store
from .engine.routing import publisher_of
from .engine.sources import KEYED_SOURCES
from .models import FulltextRequest

#: ``check`` verdicts.
STORED = "stored"  # already retrieved: read it now
OPEN = "open"  # a legal open copy is known (PMC deposit, arXiv, Unpaywall)
SUBSCRIPTION = "subscription"  # the instance's key for the publisher is live
UNAVAILABLE = "unavailable"  # no open copy known and no live publisher key
UNKNOWN = "unknown"  # could not tell (no DOI, or the locator did not answer)


def check(identifiers: list) -> list[dict]:
    """For each identifier: is a copy within reach? Fetches no full text.

    Returns one dict per identifier, in order, with ``availability`` (one of
    the verdicts above, or the resolver's stop status such as ``not_found``),
    ``explanation``, ``ids``, ``metadata`` and ``will_try`` (the sources a
    request would ask, in order). One Unpaywall lookup per DOI makes "open"
    a fact rather than a guess; its answer is cached.
    """
    engine = jobs.engine()
    out = []
    for res in engine.resolve(list(identifiers)):
        entry = {
            k: res.get(k) for k in ("input", "ids", "metadata", "notes", "publisher")
        }
        entry["will_try"] = res.get("will_try", [])
        if res["status"] != "resolved":
            entry.update(
                availability=res["status"],
                explanation=res.get("explanation", ""),
                candidates=res.get("candidates"),
            )
            out.append(entry)
            continue
        entry.update(_availability(engine, res))
        out.append(entry)
    return out


def _availability(engine, res: dict) -> dict:
    ids = res["ids"]
    doc = store.find_document(ids)
    if doc is not None:
        return {
            "availability": STORED,
            "document": str(doc.pk),
            "explanation": f"Already retrieved from {doc.source}.",
        }
    will_try = res["will_try"]
    if "pmc" in will_try:
        return {
            "availability": OPEN,
            "explanation": f"Deposited in PubMed Central as {ids['pmcid']}.",
        }
    if "arxiv" in will_try:
        return {"availability": OPEN, "explanation": "An arXiv preprint."}
    publisher, owner = publisher_of(ids.get("doi"))
    oa = None
    if ids.get("doi") and "unpaywall" in will_try:
        doi = ids["doi"]
        oa = engine.fetcher.cached_json(
            "unpaywall", doi, lambda: engine.fetcher.unpaywall_record(doi)
        )
        if oa and oa.get("is_oa"):
            host = (oa.get("best_oa_location") or {}).get("host_type") or "a repository"
            return {
                "availability": OPEN,
                "explanation": f"Unpaywall knows a legal open copy (at {host}).",
            }
    if owner in KEYED_SOURCES and owner in will_try:
        return {
            "availability": SUBSCRIPTION,
            "explanation": f"{publisher} owns it and the instance's {publisher} key "
            f"is live; whether this network is entitled shows on "
            f"fetching.",
        }
    if oa is not None:
        return {
            "availability": UNAVAILABLE,
            "explanation": "Unpaywall knows no legal open copy"
            + (
                f", and {publisher} cannot be asked on this instance."
                if owner in KEYED_SOURCES
                else "."
            )
            + " Other locators are still tried on request.",
        }
    return {
        "availability": UNKNOWN,
        "explanation": "No open-access lookup was possible; a request will try "
        + (", ".join(will_try) or "nothing")
        + ".",
    }


def request(
    identifiers: list, *, requester=None, content_item=None, background: bool = False
) -> list[FulltextRequest]:
    """Ask for the papers. Inline by default; ``background=True`` queues a
    Celery task and returns the queued rows at once."""
    reqs = jobs.create(
        list(identifiers), requester=requester, content_item=content_item
    )
    if background:
        from .tasks import run_requests

        run_requests.delay([str(r.pk) for r in reqs])
        return reqs
    return jobs.run(reqs)


def retry(
    requests: list[FulltextRequest],
    *,
    only_retryable: bool = True,
    background: bool = False,
) -> list[FulltextRequest]:
    """Run finished requests again; by default only transient failures."""
    if background:
        from .tasks import run_requests

        todo = [
            r
            for r in requests
            if r.status != FulltextRequest.Status.FULL_TEXT
            and (r.retryable or not only_retryable)
        ]
        FulltextRequest.objects.filter(pk__in=[r.pk for r in todo]).update(
            status=FulltextRequest.Status.QUEUED
        )
        run_requests.delay([str(r.pk) for r in todo])
        return todo
    return jobs.retry(requests, only_retryable=only_retryable)


def sources() -> list[dict]:
    """Each source, whether this instance can use it, and why not."""
    return jobs.engine().sources()
