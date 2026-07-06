"""Best-effort Pivot-RP refresh guard — vendored from the ProQuest tool.

Wraps :func:`~.grants.scrape_grants` and
:func:`~.conferences.scrape_conferences` in a single non-fatal, unattended-safe
call. If no session is saved, or optional deps (playwright / bs4) are absent,
or any scrape raises, the error is logged and whatever has been collected so far
is returned.

``playwright`` and ``bs4`` are optional extras — this module imports cleanly
when they are absent.
"""

from __future__ import annotations

from collections.abc import Callable


def refresh(
    areas: tuple[str, ...] = ("grants", "conferences"),
    *,
    topics: list[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[tuple[str, dict]]:
    """Run best-effort Pivot scrapes and return flat (area, record) pairs.

    Parameters
    ----------
    areas:
        Which areas to scrape. Subset of ``("grants", "conferences")``.
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

    # --- pre-flight checks (no exceptions must escape) ---
    try:
        from .common import state_exists  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        _log(f"pivot.scrape.refresh: cannot import common — {exc}")
        return []

    if not state_exists():
        _log(
            "pivot.scrape.refresh: no storage_state.json — "
            "run pivot.login.login() first, skipping scrape"
        )
        return []

    try:
        import playwright  # noqa: F401 — presence check only
        from bs4 import BeautifulSoup  # noqa: F401 — presence check only
    except ImportError as exc:
        _log(f"pivot.scrape.refresh: optional deps missing ({exc}), skipping scrape")
        return []

    pairs: list[tuple[str, dict]] = []
    grant_topics: list[str] = topics if topics is not None else []

    if "grants" in areas:
        try:
            from .grants import scrape_grants  # noqa: PLC0415

            records = scrape_grants(grant_topics, log=_log)
            pairs.extend(("grants", r) for r in records)
            _log(f"pivot.scrape.refresh: grants done — {len(records)} records")
        except Exception as exc:
            _log(f"pivot.scrape.refresh: grants scrape failed — {exc}")

    if "conferences" in areas:
        try:
            from .conferences import scrape_conferences  # noqa: PLC0415

            records = scrape_conferences(log=_log)
            pairs.extend(("conferences", r) for r in records)
            _log(f"pivot.scrape.refresh: conferences done — {len(records)} records")
        except Exception as exc:
            _log(f"pivot.scrape.refresh: conferences scrape failed — {exc}")

    return pairs
