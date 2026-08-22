"""Paired significance testing — the one implementation both experiments call.

`scoring.py` carries the rule "never hand-roll a metric", and the same argument
applies with more force to an interval: two experiments each with their own
bootstrap is two chances to compute subtly different things and then compare them
as if they were the same. `EXP-2026-08-009` introduced this machinery and
`EXP-2026-08-010` needs it, so it lives here rather than in either folder.

**Why paired.** Arms answer the same queries, so the unit of resampling is the
query, not the run. Resampling queries with replacement and recomputing the mean
per-query delta preserves that pairing; treating the arms as independent samples
would discard it and inflate the interval.

**Why a sign test alongside.** A mean delta carried by three large wins and one
earned across two hundred queries are different findings with identical means.
The sign test is distribution-free and answers "does this help more queries than
it hurts", which is a separate question from "is the mean non-zero".
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

#: Fixed so an interval does not move between runs of the same analysis.
DEFAULT_SEED = 20260821
DEFAULT_RESAMPLES = 10_000


@dataclass(frozen=True)
class Paired:
    """One contrast: the mean difference, its interval, and its per-query record."""

    n: int
    mean: float
    ci_low: float
    ci_high: float
    wins: int
    losses: int
    ties: int
    sign_p: float

    @property
    def excludes_zero(self) -> bool:
        return self.ci_low > 0.0 or self.ci_high < 0.0

    def as_dict(self) -> dict:
        return {
            "n": self.n, "mean_delta": self.mean,
            "ci_low": self.ci_low, "ci_high": self.ci_high,
            "excludes_zero": self.excludes_zero,
            "wins": self.wins, "losses": self.losses, "ties": self.ties,
            "sign_p": self.sign_p,
        }


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact binomial p under p = 0.5, ties excluded."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def paired_bootstrap(
    deltas: Sequence[float],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    tolerance: float = 1e-12,
) -> Paired:
    """Percentile bootstrap over paired per-query differences.

    `tolerance` decides what counts as a tie: floating-point metric values that
    differ in the last bit are the same result, and calling them a win would
    inflate the win count without changing the mean.
    """
    values = list(deltas)
    n = len(values)
    if n == 0:
        raise ValueError("no paired differences to test")

    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()

    wins = sum(1 for d in values if d > tolerance)
    losses = sum(1 for d in values if d < -tolerance)
    return Paired(
        n=n,
        mean=sum(values) / n,
        ci_low=means[int(0.025 * resamples)],
        ci_high=means[int(0.975 * resamples) - 1],
        wins=wins,
        losses=losses,
        ties=n - wins - losses,
        sign_p=sign_test(wins, losses),
    )


def length_bucket(n_words: int) -> str:
    """The query-length strata `EXP-2026-08-009` established, kept identical.

    Shared so two experiments cannot silently draw their bucket edges differently
    and then have their tables compared.
    """
    if n_words <= 1:
        return "1 word"
    if n_words == 2:
        return "2 words"
    if n_words <= 4:
        return "3-4 words"
    return "5+ words"


BUCKET_ORDER = ("1 word", "2 words", "3-4 words", "5+ words")
