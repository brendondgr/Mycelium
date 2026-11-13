"""Fellowships scraper.

Illinois Fellowship Finder (public, no login) is the single source. The public
entry point is :func:`scrape_fellowships`: best-effort, never raises out of a
refresh, owns its own asyncio event loop.

``playwright`` and ``bs4`` are optional extras — this package imports cleanly
when they are absent; the imports happen inside functions (see ``illinois.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

_DEFAULT_CONCURRENCY = 5
_DEFAULT_DELAY = 0.3  # seconds between detail renders


def scrape_fellowships(
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
    delay: float = _DEFAULT_DELAY,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    """Scrape the Illinois Fellowship Finder and return structured records.

    Best-effort: returns ``[]`` on any failure and never raises. Each record has
    exactly the shape produced by :func:`.illinois.build_record` (same as the
    tool's ``fellowships.json`` entries).

    Parameters
    ----------
    concurrency:
        Maximum parallel Blazor detail renders.
    delay:
        Seconds to sleep between detail renders.
    log:
        Optional callable for progress/error messages.
    """
    _log = log or (lambda _: None)

    # Pre-flight: optional deps check.
    try:
        import playwright  # noqa: F401
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError as exc:
        _log(f"fellowships.scrape: optional deps missing ({exc}), skipping")
        return []

    try:
        from tools.retrieval.fellowships.illinois import (  # noqa: PLC0415
            build_record,
            fetch_listing,
            parse_detail,
            parse_listing,
            render_detail,
        )
    except Exception as exc:  # pragma: no cover
        _log(f"fellowships.scrape: cannot import illinois adapter — {exc}")
        return []

    scraped_at = datetime.now(UTC).isoformat(timespec="seconds")

    async def _run() -> list[dict]:
        from playwright.async_api import async_playwright  # noqa: PLC0415 lazy

        from tools.retrieval.fellowships.illinois import (  # noqa: PLC0415
            CONTEXT_KWARGS,
            LAUNCH_ARGS,
        )

        records: list[dict] = []
        async with async_playwright() as p:
            # Listing: plain HTTP GET via APIRequestContext.
            req = await p.request.new_context()
            try:
                listing_html = await fetch_listing(req)
            except Exception as exc:
                _log(f"fellowships.scrape: listing fetch failed — {exc}")
                await req.dispose()
                return []
            await req.dispose()

            rows = parse_listing(listing_html)
            _log(f"fellowships.scrape: listing fetched — {len(rows)} fellowships")
            if not rows:
                return []

            # Detail pages: Blazor Server app, need a real browser.
            browser = await p.chromium.launch(headless=True, args=LAUNCH_ARGS)
            context = await browser.new_context(**CONTEXT_KWARGS)
            sem = asyncio.Semaphore(concurrency)
            done: dict = {"n": 0, "failed": 0}
            total = len(rows)

            async def _work(row: dict) -> None:
                async with sem:
                    page = await context.new_page()
                    try:
                        dhtml = await render_detail(page, row["id"])
                    except Exception:
                        dhtml = ""
                    finally:
                        await page.close()
                    if delay:
                        await asyncio.sleep(delay)
                detail = parse_detail(dhtml) if dhtml else {}
                records.append(build_record(row, detail, scraped_at))
                done["n"] += 1
                if not dhtml:
                    done["failed"] += 1
                if done["n"] % 25 == 0 or done["n"] == total:
                    fail_note = f" ({done['failed']} failed)" if done["failed"] else ""
                    _log(f"  fellowships detail {done['n']}/{total}{fail_note}")

            try:
                await asyncio.gather(*(_work(r) for r in rows))
            except Exception as exc:
                _log(f"fellowships.scrape: detail phase error — {exc}")
            finally:
                await context.close()
                await browser.close()

        return records

    try:
        records = asyncio.run(_run())
        _log(f"fellowships.scrape: done — {len(records)} records")
        return records
    except Exception as exc:
        _log(f"fellowships.scrape: run failed — {exc}")
        return []
