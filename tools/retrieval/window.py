"""The publication-date window a literature scan covers.

The product spec is "the last two months and the next month, relative to today":
on 2026-06-29 that is 2026-04-29 → 2026-07-29. The forward edge exists because
OpenAlex / Semantic Scholar carry ahead-of-print and early-access records dated
slightly in the future, and we want to catch those as they appear.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def shift_months(moment: datetime, months: int) -> datetime:
    """Return ``moment`` shifted by ``months`` (can be negative), clamping the day.

    Clamping keeps e.g. shifting Mar 31 back one month at Feb's last day instead
    of overflowing, and handles leap years via ``calendar.monthrange``.
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


@dataclass(frozen=True)
class ScanWindow:
    """An inclusive [since, until] publication-date window for a scan."""

    since: datetime
    until: datetime

    @classmethod
    def around_today(cls, months_back: int = 2, months_forward: int = 1) -> ScanWindow:
        now = datetime.now(UTC)
        return cls(
            since=shift_months(now, -abs(months_back)),
            until=shift_months(now, abs(months_forward)),
        )

    @classmethod
    def around_today_days(cls, days_back: int, days_forward: int) -> ScanWindow:
        """A tight day-level window — used by the daily run (e.g. 2 back, 7 ahead)."""
        now = datetime.now(UTC)
        return cls(
            since=now - timedelta(days=abs(days_back)),
            until=now + timedelta(days=abs(days_forward)),
        )

    @property
    def since_date(self) -> str:
        return self.since.strftime("%Y-%m-%d")

    @property
    def until_date(self) -> str:
        return self.until.strftime("%Y-%m-%d")

    def __str__(self) -> str:
        return f"{self.since_date} → {self.until_date}"
