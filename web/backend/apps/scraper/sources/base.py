"""Base scraper machinery: rate limiting, retries, progress reporting.

Every source scraper subclasses :class:`BaseScraper` and implements ``search``.
The base class owns the shared aiohttp session, an async rate limiter
(token-bucket-ish min-interval lock) and a small retry/backoff helper, so the
concrete scrapers only contain source-specific request/parse logic.

Ported from ``~/Tools/ResearchScraper/utils/base.py``; the time ``Window`` now
lives in :mod:`apps.scraper.window` (``ScanWindow``) and is re-exported here so
the source scrapers keep importing ``Window`` from this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import aiohttp

from ..window import ScanWindow as Window
from .record import Record

__all__ = ["BaseScraper", "RateLimiter", "Window", "ProgressCB"]


# Callback used by scrapers to report live progress.
# (status, records_so_far, pages, detail)
ProgressCB = Callable[[str, int, int, str], None]


class RateLimiter:
    """Enforces a maximum request rate across all coroutines sharing it."""

    def __init__(self, rate_per_sec: float) -> None:
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            wait = self._last + self.min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = asyncio.get_event_loop().time()


class BaseScraper:
    name: str = "base"
    # Per-source request rate (req/sec). Conservative defaults.
    rate_per_sec: float = 3.0

    def __init__(
        self,
        session: aiohttp.ClientSession,
        config,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.session = session
        self.config = config
        self.limiter = rate_limiter or RateLimiter(self.rate_per_sec)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 4,
        timeout: int = 60,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Rate-limited request with exponential backoff on 429/5xx/network errors."""
        last_exc: Exception | None = None
        for attempt in range(retries):
            await self.limiter.acquire()
            try:
                resp = await self.session.request(
                    method, url, timeout=aiohttp.ClientTimeout(total=timeout), **kwargs
                )
                if resp.status in (429, 500, 502, 503, 504):
                    await resp.release()
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=resp.status,
                        message=f"retryable status {resp.status}",
                    )
                return resp
            except (TimeoutError, aiohttp.ClientError) as exc:
                last_exc = exc
                if attempt < retries - 1:
                    await asyncio.sleep(min(2 ** attempt, 30))
                continue
        raise last_exc or RuntimeError("request failed")

    async def search(
        self, query: str, window: Window, progress: ProgressCB
    ) -> list[Record]:
        raise NotImplementedError
