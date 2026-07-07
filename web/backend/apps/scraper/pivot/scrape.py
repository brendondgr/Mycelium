"""Best-effort Pivot-RP + fellowships refresh guard — vendored from the ProQuest tool.

Wraps :func:`~.grants.scrape_grants`, :func:`~.conferences.scrape_conferences`,
and :func:`~.fellowships.scrape_fellowships` in a single non-fatal, unattended-safe
call. Areas run **in parallel** — one thread per area via :class:`ThreadPoolExecutor`,
each owning its own asyncio event loop (``asyncio.run`` inside the thread, safe
because each loop is private).

Pre-flight logic:
- Missing ``storage_state.json`` skips grants + conferences only; fellowships are
  scraped from a public site (no Pivot SSO) and continue regardless.
- Missing playwright or bs4 skips everything.

``playwright`` and ``bs4`` are optional extras — this module imports cleanly
when they are absent.
"""

from __future__ import annotations

from collections.abc import Callable


def refresh(
    areas: tuple[str, ...] = ("grants", "conferences", "fellowships"),
    *,
    topics: list[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[tuple[str, dict]]:
    """Run best-effort scrapes for each area and return flat (area, record) pairs.

    Parameters
    ----------
    areas:
        Which areas to scrape. Subset of ``("grants", "conferences", "fellowships")``.
    topics:
        Topic/keyword strings fed to :func:`~.grants.scrape_grants`.
        When *None*, an empty list is passed (caller is expected to supply
        topics; an empty list skips the grants search gracefully).
    log:
        Optional callable for progress/error messages. Defaults to a no-op.

    Returns
    -------
    list[tuple[str, dict]]
        Flat list of ``(area, raw_record)`` pairs.  Returns ``[]`` on total
        failure.  Never raises.
    """
    _log = log or (lambda _: None)

    # --- pre-flight: optional deps check (no exceptions must escape) ----------
    try:
        import playwright  # noqa: F401 — presence check only
        from bs4 import BeautifulSoup  # noqa: F401 — presence check only
    except ImportError as exc:
        _log(f"pivot.scrape.refresh: optional deps missing ({exc}), skipping scrape")
        return []

    # --- check Pivot session (needed for grants + conferences only) -----------
    pivot_available = False
    try:
        from .common import state_exists  # noqa: PLC0415

        pivot_available = state_exists()
    except Exception as exc:  # pragma: no cover
        _log(f"pivot.scrape.refresh: cannot import common — {exc}")

    if not pivot_available:
        _log(
            "pivot.scrape.refresh: no storage_state.json — "
            "grants + conferences will be skipped; fellowships continue"
        )

    # --- build the work list --------------------------------------------------
    grant_topics: list[str] = topics if topics is not None else []

    import concurrent.futures

    pairs: list[tuple[str, dict]] = []

    def _scrape_grants_area() -> list[tuple[str, dict]]:
        if not pivot_available:
            return []
        try:
            from .grants import scrape_grants  # noqa: PLC0415

            records = scrape_grants(grant_topics, log=_log)
            _log(f"pivot.scrape.refresh: grants done — {len(records)} records")
            return [("grants", r) for r in records]
        except Exception as exc:
            _log(f"pivot.scrape.refresh: grants scrape failed — {exc}")
            return []

    def _scrape_conferences_area() -> list[tuple[str, dict]]:
        if not pivot_available:
            return []
        try:
            from .conferences import scrape_conferences  # noqa: PLC0415

            records = scrape_conferences(log=_log)
            _log(f"pivot.scrape.refresh: conferences done — {len(records)} records")
            return [("conferences", r) for r in records]
        except Exception as exc:
            _log(f"pivot.scrape.refresh: conferences scrape failed — {exc}")
            return []

    def _scrape_fellowships_area() -> list[tuple[str, dict]]:
        try:
            from .fellowships import scrape_fellowships  # noqa: PLC0415

            records = scrape_fellowships(log=_log)
            _log(f"pivot.scrape.refresh: fellowships done — {len(records)} records")
            return [("fellowships", r) for r in records]
        except Exception as exc:
            _log(f"pivot.scrape.refresh: fellowships scrape failed — {exc}")
            return []

    # Build the list of per-area callables to run in parallel.
    _AREA_FNS = {
        "grants": _scrape_grants_area,
        "conferences": _scrape_conferences_area,
        "fellowships": _scrape_fellowships_area,
    }
    work_fns = [_AREA_FNS[a] for a in areas if a in _AREA_FNS]
    if not work_fns:
        return []

    # Run areas in parallel — each function owns its own asyncio loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(work_fns)) as executor:
        futures = [executor.submit(fn) for fn in work_fns]
        for fut in concurrent.futures.as_completed(futures):
            try:
                pairs.extend(fut.result())
            except Exception as exc:
                _log(f"pivot.scrape.refresh: area thread raised — {exc}")

    return pairs
