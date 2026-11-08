"""Resolve -> route -> fetch for any number of articles.

:class:`Engine` is the whole engine behind one object: give it identifiers,
get back one plain result dict per identifier, in request order. Writing files
anywhere other than the engine's own cache is the caller's business (the
Django side copies each original into the tool's store).

A result always has ``input``, ``status`` and ``explanation``. Statuses:

``resolved``             (``resolve`` only) identified and routed, nothing fetched
``full_text``            the body was retrieved: ``markdown``, ``document``,
                         ``original``, ``source``, ``licensed``
``abstract_only``        identified, but no source could provide full text;
                         ``next_steps`` says what could change that
``invalid_identifier``   the input could not be parsed as an identifier
``not_found``            the identifier does not exist
``identifier_mismatch``  identifiers or the expected title disagree; nothing fetched
``needs_identifier``     a title matched zero or several articles; see ``candidates``
``error``                an unexpected failure; usually safe to retry
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from . import sources as S
from .convert import jats_to_markdown
from .fetcher import DEFAULT_DISABLE_TTL, Fetcher, describe, is_licensed
from .identifiers import article_key, parse_item
from .resolver import Resolver
from .routing import explain, plan, publisher_of
from .state import State

log = logging.getLogger(__name__)

FULL, ABSTRACT, RESOLVED = "full_text", "abstract_only", "resolved"
STATUSES = {
    RESOLVED: "identified and routed; nothing fetched",
    FULL: "full text retrieved",
    ABSTRACT: "article identified, but no source could provide full text",
    "invalid_identifier": "the input could not be parsed as an identifier",
    "not_found": "the identifier does not exist (PubMed, PMC and doi.org lack it)",
    "identifier_mismatch": "identifiers or expected title disagree; nothing fetched",
    "needs_identifier": "a title matched zero or several articles; choose a candidate",
    "error": "an unexpected failure on this article; usually safe to retry",
}
ORIGINAL_EXT = {"pdf": "pdf", "xml": "xml", "html": "html", "text": "txt"}


class Engine:
    def __init__(
        self,
        env: Mapping[str, str] | None,
        cache_dir: Path | str,
        *,
        state: State | None = None,
        order: list[str] | None = None,
        min_chars: int = 500,
        workers: int = 4,
        retry: bool = False,
        disable_ttl: float = DEFAULT_DISABLE_TTL,
    ):
        self.order = [s for s in (order or S.DEFAULT_ORDER) if s in S.SOURCES]
        self.fetcher = Fetcher(
            env,
            cache_dir,
            state=state,
            order=self.order,
            min_chars=min_chars,
            retry=retry,
            disable_ttl=disable_ttl,
        )
        self.resolver = Resolver(self.fetcher)
        self.min_chars = min_chars
        self.workers = max(1, workers)

    # -- introspection ----------------------------------------------------- #
    def sources(self) -> list[dict]:
        """Each source, whether it is live on this instance, and why not."""
        return describe(self.fetcher)

    def route(self, pmid, doi, pmcid) -> list[dict]:
        return plan(self.fetcher.disabled, pmid, doi, pmcid, self.order)

    # -- resolution only --------------------------------------------------- #
    def resolve(self, raw_items: list) -> list[dict]:
        """Parse, resolve and route, but fetch nothing."""
        resolved = self.resolver.resolve([parse_item(x) for x in raw_items])
        out = []
        for r in resolved:
            res = self._base_result(r)
            if r["status"] is None:
                res["status"] = RESOLVED
                res["route"] = self.route(r["pmid"], r["doi"], r["pmcid"])
                res["will_try"] = [
                    s["source"] for s in res["route"] if s["action"] == "try"
                ]
            out.append(res)
        return out

    # -- the full pass ----------------------------------------------------- #
    def fetch(
        self,
        raw_items: list,
        *,
        workers: int | None = None,
        on_result: Callable[[int, dict], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[dict]:
        """Fetch full text for ``raw_items``. Returns results in input order.

        ``on_result(i, result)`` is called as each article finishes;
        ``cancelled()`` is polled between articles so a long run can stop.
        """
        results: list[dict | None] = [None] * len(raw_items)

        def done(i, res):
            results[i] = res
            if on_result:
                on_result(i, res)

        try:
            resolved = self.resolver.resolve([parse_item(x) for x in raw_items])
        except requests.RequestException as exc:
            for i, x in enumerate(raw_items):
                done(
                    i,
                    {
                        "input": x,
                        "status": "error",
                        "retryable": True,
                        "explanation": f"identifier resolution failed (NCBI/Crossref "
                        f"unreachable: {type(exc).__name__}); try again",
                    },
                )
            return results  # type: ignore[return-value]

        todo = []  # (i, resolved, base result, route)
        for i, r in enumerate(resolved):
            res = self._base_result(r)
            if r["status"] is not None:
                done(i, res)
                continue
            route = self.route(r["pmid"], r["doi"], r["pmcid"])
            res["route"] = route
            todo.append((i, r, res, route))

        # PMC first, batched: one efetch per 50 articles instead of one per article.
        pmc_md: dict[str, tuple[str, str]] = {}
        want = sorted({r["pmcid"] for _, r, _, route in todo if _tries(route, "pmc")})
        if want:
            try:
                for pmcid, (article, path) in self.resolver.pmc_articles(want).items():
                    md = jats_to_markdown(article, self.min_chars)
                    if md:
                        pmc_md[pmcid] = (md, path)
            except requests.RequestException as exc:
                log.info(
                    "full text: PMC batch failed, other sources still run: %s", exc
                )

        def work(entry):
            i, r, res, route = entry
            tried: dict[str, str] = {}
            if r["pmcid"] in pmc_md:
                md, path = pmc_md[r["pmcid"]]
                prov = {
                    "pmcid": r["pmcid"],
                    "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{r['pmcid']}/",
                    "kind": "xml",
                    "original": {"path": path, "kind": "xml"},
                }
                return md, "pmc", prov, {"pmc": "ok"}, None
            if _tries(route, "pmc"):
                tried["pmc"] = "no-body (PMC record has no full-text body)"
            order = [
                s["source"]
                for s in route
                if s["action"] == "try" and s["source"] != "pmc"
            ]
            md, source, prov, more, oa = self.fetcher.fetch(
                r["pmid"], r["doi"], r["pmcid"], order=order
            )
            tried.update(more)
            return md, source, prov, tried, oa

        n = max(1, workers or self.workers)
        with ThreadPoolExecutor(max_workers=n) as ex:
            pending = iter(todo)
            futures = {}

            def top_up():
                # Submit lazily, so a cancelled run stops after the articles in flight.
                while len(futures) < n * 2 and not (cancelled and cancelled()):
                    nxt = next(pending, None)
                    if nxt is None:
                        return
                    futures[ex.submit(work, nxt)] = nxt

            top_up()
            while futures:
                fut = next(as_completed(futures))
                i, r, res, _ = futures.pop(fut)
                try:
                    md, source, prov, tried, oa = fut.result()
                    res = self._finish(r, res, md, source, prov, tried, oa)
                except Exception as exc:  # one article never sinks the batch
                    log.exception("full text: article %s failed", res.get("key"))
                    res.update(
                        status="error",
                        retryable=True,
                        explanation=f"{type(exc).__name__}: {exc}",
                    )
                done(i, res)
                top_up()
        return results  # type: ignore[return-value]

    # -- pieces ------------------------------------------------------------ #
    def _base_result(self, r: dict) -> dict:
        it = r["item"]
        meta = r.get("meta") or {}
        res = {
            "input": it.input,
            "label": it.label,
            "key": article_key(r["pmid"], r["doi"], r["pmcid"]) or None,
            "status": r["status"],
            "ids": {
                "pmid": r["pmid"],
                "pmcid": r["pmcid"],
                "doi": r["doi"],
                "arxiv": S.arxiv_id(r["doi"]),
            },
            "metadata": {
                k: meta[k]
                for k in ("title", "journal", "year", "authors", "abstract")
                if meta.get(k)
            },
            "publisher": publisher_of(r["doi"])[0],
            "notes": r["notes"],
        }
        if r["status"]:
            res.update(explanation=r["explanation"], retryable=False)
        if r.get("candidates") is not None:
            res["candidates"] = r["candidates"]
        return res

    def _finish(self, r, res, md, source, prov, tried, oa) -> dict:
        publisher, owner = publisher_of(r["doi"])
        why, retryable, nxt = explain(
            publisher, owner, res["route"], tried, source, len(md or "")
        )
        res.update(attempts=tried, explanation=why, retryable=retryable)
        meta = r.get("meta") or {}
        if oa:
            res["open_access"] = oa
        if md:
            original = (prov or {}).get("original")
            if original and not Path(original["path"]).exists():
                original = None
            res.update(
                status=FULL,
                source=source,
                source_label=S.SOURCES[source]["label"],
                source_url=(prov or {}).get("url"),
                chars=len(md),
                markdown=md,
                document=render_document(r, meta, provenance_line(source, prov), md),
                original=original,
                licensed=is_licensed(source, prov),
            )
        else:
            res.update(status=ABSTRACT, next_steps=nxt)
        return res


def _tries(route: list[dict], source: str) -> bool:
    return any(s["source"] == source and s["action"] == "try" for s in route)


def provenance_line(source: str, prov: dict | None) -> str:
    label = S.SOURCES[source]["label"]
    url = (prov or {}).get("url") or ""
    kind = (prov or {}).get("kind")
    extra = f", {kind}" if kind else ""
    return f"**Full text source:** {label}{extra}" + (f" — <{url}>" if url else "")


def render_document(r: dict, meta: dict, header_line: str, full_md: str | None) -> str:
    """One article as markdown: title, identifiers, metadata, abstract, full text."""
    lines = [f"# {meta.get('title') or r['doi'] or r['pmid']}", ""]
    if r["pmid"]:
        lines.append(
            f"**PMID:** [{r['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/)"
        )
    if r["doi"]:
        lines.append(f"**DOI:** [{r['doi']}](https://doi.org/{r['doi']})")
    for label, k in (
        ("Journal", "journal"),
        ("Publication date", "year"),
        ("Authors", "authors"),
    ):
        if meta.get(k):
            lines.append(f"**{label}:** {meta[k]}")
    lines += ["", header_line, ""]
    if meta.get("abstract"):
        lines += ["## Abstract", "", meta["abstract"], ""]
    if full_md:
        lines += ["## Full text", "", full_md, ""]
    if meta.get("mesh_terms"):
        lines += ["## MeSH terms", ""] + [
            f"- {t}" for t in meta["mesh_terms"].split("; ")
        ]
        lines.append("")
    return "\n".join(lines)
