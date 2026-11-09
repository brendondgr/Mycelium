"""Create full-text requests and run them through the engine.

A request is one identifier. :func:`run` takes any number of them, answers the
ones whose paper is already stored without touching a provider, fetches the
rest in one engine pass, stores what came back, and records the outcome on
each request row. It runs inline (the management command, tests) or on a
Celery worker (:mod:`.tasks`).
"""

from __future__ import annotations

import logging

from apps.accounts.services import record_audit_event
from django.db import transaction
from django.utils import timezone

from tools._framework.events import publish

from . import config, store
from .engine.pipeline import Engine
from .events import RETRIEVED
from .models import FulltextRequest
from .state import shared_state

log = logging.getLogger(__name__)

Status = FulltextRequest.Status


def create(
    identifiers: list, *, requester=None, content_item=None
) -> list[FulltextRequest]:
    """One queued request per identifier, sharing a batch id."""
    batch = None
    out = []
    with transaction.atomic():
        for ident in identifiers:
            req = FulltextRequest(
                identifier=ident, requester=requester, content_item=content_item
            )
            if batch is None:
                batch = req.batch
            req.batch = batch
            req.save()
            out.append(req)
    return out


def engine() -> Engine:
    return config.engine(state=shared_state())


def run(
    requests: list[FulltextRequest], *, engine_: Engine | None = None
) -> list[FulltextRequest]:
    """Run ``requests`` to a finished status. Returns them, refreshed."""
    if not requests:
        return []
    eng = engine_ or engine()
    now = timezone.now()
    FulltextRequest.objects.filter(pk__in=[r.pk for r in requests]).update(
        status=Status.RUNNING, started_at=now
    )
    try:
        _run(requests, eng)
    except Exception as exc:  # resolution itself failed: every request is retryable
        log.exception("full text: batch failed")
        for req in requests:
            if not FulltextRequest.objects.get(pk=req.pk).finished:
                _finish(
                    req,
                    {
                        "status": Status.ERROR,
                        "retryable": True,
                        "explanation": f"{type(exc).__name__}: {exc}",
                    },
                )
    for req in requests:
        req.refresh_from_db()
    return requests


def _run(requests: list[FulltextRequest], eng: Engine) -> None:
    # 1. Resolve everything (cheap, cached); a paper already stored is answered
    #    from the store without asking any provider.
    resolved = eng.resolve([r.identifier for r in requests])
    to_fetch = []
    for req, res in zip(requests, resolved, strict=True):
        if res["status"] != "resolved":
            _finish(req, res)  # invalid, not found, mismatch, needs an identifier
            continue
        doc = store.find_document(res["ids"])
        if doc is not None:
            _finish(
                req,
                {
                    **res,
                    "status": Status.FULL_TEXT,
                    "explanation": "Already retrieved; served from the store.",
                },
                document=doc,
            )
        else:
            to_fetch.append(req)
    # 2. Fetch the rest in one pass.
    if not to_fetch:
        return
    results = eng.fetch([r.identifier for r in to_fetch])
    for req, res in zip(to_fetch, results, strict=True):
        if res is None:  # never started (a cancelled pass)
            _finish(
                req,
                {
                    "status": Status.ERROR,
                    "retryable": True,
                    "explanation": "The fetch stopped before this paper.",
                },
            )
            continue
        doc = None
        if res["status"] == Status.FULL_TEXT:
            try:
                doc = store.save(res)
            except OSError as exc:
                log.exception("full text: could not store %s", res.get("key"))
                res = {
                    **res,
                    "status": Status.ERROR,
                    "retryable": True,
                    "explanation": f"Retrieved, but could not be stored: {exc}",
                }
        _finish(req, res, document=doc, fetched=True)


def _finish(req: FulltextRequest, res: dict, *, document=None, fetched=False) -> None:
    status = res["status"]
    if status not in Status.values:
        status = Status.ERROR
    fields = {
        "status": status,
        "ids": res.get("ids") or {},
        "explanation": res.get("explanation") or "",
        "retryable": bool(res.get("retryable")),
        "next_steps": res.get("next_steps") or [],
        "route": res.get("route") or [],
        "attempts": res.get("attempts") or {},
        "notes": res.get("notes") or [],
        "candidates": res.get("candidates") or [],
        "document": document,
        "finished_at": timezone.now(),
    }
    if document is not None and req.content_item_id is None:
        fields["content_item"] = document.content_item
    for name, value in fields.items():
        setattr(req, name, value)
    req.save(update_fields=list(fields))
    if document is not None and fetched:
        if document.licensed:
            record_audit_event(
                actor=req.requester,
                action="fulltext.licensed_fetch",
                target_type="fulltext_document",
                target_id=str(document.pk),
                metadata={
                    "source": document.source,
                    "doi": document.doi,
                    "request": str(req.pk),
                },
            )
        publish(RETRIEVED, document=document, content_item=document.content_item)


def retry(
    requests: list[FulltextRequest],
    *,
    only_retryable: bool = True,
    engine_: Engine | None = None,
) -> list[FulltextRequest]:
    """Run finished requests again (by default only the transient failures)."""
    todo = [
        r
        for r in requests
        if r.status != Status.FULL_TEXT and (r.retryable or not only_retryable)
    ]
    return run(todo, engine_=engine_)
