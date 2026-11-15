"""Exact and score intervals without scipy (shared by EXP-2026-11-016/-017)."""

from __future__ import annotations

import math


def _binom_cdf(k, n, p):
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    total, term = 0.0, (1 - p) ** n
    for i in range(0, k + 1):
        if i > 0:
            term *= (n - i + 1) / i * p / (1 - p)
        total += term
    return min(total, 1.0)


def _bisect(f, lo=0.0, hi=1.0):
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    if n == 0:
        return (None, None)
    lo = 0.0 if k == 0 else _bisect(lambda p: 1 - _binom_cdf(k - 1, n, p) < alpha / 2)
    hi = 1.0 if k == n else _bisect(lambda p: _binom_cdf(k, n, p) > alpha / 2)
    return (round(lo, 4), round(hi, 4))


def upper_one_sided(k, n, alpha=0.05):
    """One-sided 95% upper bound (for zero counts: 1 - alpha**(1/n))."""
    if n == 0:
        return None
    if k == 0:
        return round(1 - alpha ** (1 / n), 4)
    return round(_bisect(lambda p: _binom_cdf(k, n, p) > alpha), 4)


def wilson(k, n, z=1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def newcombe(k1, n1, k2, n2):
    """Hybrid-score 95% interval for p1 - p2 (Newcombe method 10)."""
    if not n1 or not n2:
        return (None, None, None)
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (round(d, 4), round(lo, 4), round(hi, 4))


def kappa(pairs):
    """Cohen's kappa over (a, b) boolean pairs."""
    n = len(pairs)
    if not n:
        return None
    agree = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((agree - pe) / (1 - pe), 4)
