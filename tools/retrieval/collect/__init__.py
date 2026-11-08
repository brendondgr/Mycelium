"""The open-source grants + conferences collector, vendored into the backend.

This package is a near-verbatim port of the standalone ``research-collector``
project (see ``docs/plans/open-opportunity-collector.md``, Phase 1). It runs
in the backend container because, unlike Pivot-RP, it is pure HTTP — no
Playwright, no SSO session — so the host/container split that Pivot needed
does not apply here (plan decision D6).

Layout:

    core/          content-agnostic collection machinery shared by both
                   domains: a deliberately slow, robots-aware HTTP client,
                   run-scoped raw payload storage, and pure text/date helpers.
    grants/        the six funding-opportunity adapters, dedupe, and SQLite
                   store, vendored from ``utils/grants/collect/`` in the original prototype.
    conferences/   the conference CFP adapters (minus WikiCFP — plan D5),
                   the registry (dblp identity, CORE rankings), trust-tier
                   resolution, dedupe, and SQLite store, vendored from
                   ``utils/conferences/collect/``.
    runner.py      the cross-domain orchestration script, adapted from the
                   standalone project's root ``pipeline.py``.

What was deliberately left behind, and why, is recorded in each subpackage's
own module docstring rather than repeated here — see ``core/__init__.py``,
``grants/__init__.py`` and ``conferences/adapters/__init__.py`` in particular.
The one rule that applies everywhere in this package: everything here still
writes to its own SQLite stores under ``data/collect/``, exactly as the
standalone project did. Wiring that output into Mycelium's Postgres-backed
``ContentItem`` model is a later phase (Phase 3 of the plan above), not this
one — Phase 1's job is only to make every module here import cleanly on
Python 3.13 inside the Django process.
"""
