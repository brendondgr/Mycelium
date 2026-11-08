"""Stage 4: canonical series keys and predatory red flags.

This stage does not exist in the funding pipeline, and it is the one that makes
the output safe to show anyone. Every grant source is a government agency, so a
record from one is legitimate by construction. Conference sources are not: a
large volume of predatory pay-to-present events is indistinguishable from real
venues by format alone, and a pipeline that ingests them without a quality layer
actively harms users by recommending venues that damage their publication record.

**It must run with no network access.** Red-flag thresholds get tuned constantly
and re-fetching seven sources to try a new threshold is not acceptable, so the
registry (dblp identity, CORE rankings) is read from a local cache that a
separate slow-schedule job populates.

**It refuses to guess.** 372 acronyms map to more than one dblp venue on current
titles alone, 420 including former titles. ``SAC`` is both the ACM Symposium on
Applied Computing and Selected Areas in Cryptography — both active, both typed
identically, both returned with the same relevance score. Picking the
longer-running one would silently delete a cryptography conference. Where the
evidence does not separate candidates, this stage resolves to *nothing* and
records the candidates for a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
)
from tools.retrieval.collect.core.text import (
    clean_text,
    dedupe_preserving_order,
    normalize_title,
)

_ORDINAL_PREFIX = re.compile(
    r"^\s*(?:the\s+)?\d+\s*(?:st|nd|rd|th)?\s+(?=[A-Za-z])", re.IGNORECASE
)
_ACRONYM_NOISE = re.compile(r"[^A-Z0-9]+")
_TRAILING_YEAR = re.compile(r"\s*'?\d{2,4}\s*$")


@dataclass
class ResolveReport:
    series_in: int = 0
    resolved: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    flagged: int = 0

    def summary(self) -> str:
        return (
            f"series={self.series_in} resolved={self.resolved} "
            f"ambiguous={self.ambiguous} unresolved={self.unresolved} | "
            f"red-flagged={self.flagged}"
        )


# --- acronym normalization ----------------------------------------------


def normalize_acronym(value: object) -> str:
    """Uppercase, strip punctuation, strip a trailing year.

    Used only to *generate candidates*. It is never an identity: the collisions
    above are exactly what happens when an acronym is treated as a key.
    """
    text = clean_text(value).upper()
    if not text:
        return ""
    text = _TRAILING_YEAR.sub("", text)
    return _ACRONYM_NOISE.sub("", text)


def strip_ordinal(title: object) -> str:
    """Drop a leading ordinal for matching, keeping the original for display.

    "32nd International Conference on X" and "International Conference on X" are
    the same series.
    """
    return _ORDINAL_PREFIX.sub("", clean_text(title)).strip()


def extract_ordinal(title: object) -> str:
    match = _ORDINAL_PREFIX.match(clean_text(title))
    return match.group(0).strip() if match else ""


# --- the stage -----------------------------------------------------------


def resolve_all(
    series: list[ConferenceSeries],
    instances: list[ConferenceInstance],
    *,
    registry_dir: Path | None = None,
    now=None,
) -> tuple[list[ConferenceSeries], list[ConferenceInstance], ResolveReport]:
    """Join to the registry, assign series keys, compute red flags.

    Reads only from the local registry cache. Never opens a socket.
    """
    from tools.retrieval.collect.conferences.registry.cache import RegistryCache

    report = ResolveReport(series_in=len(series))
    cache = RegistryCache(registry_dir) if registry_dir else None
    if cache is not None:
        cache.load()

    by_series: dict[str, list[ConferenceInstance]] = {}
    for record in instances:
        by_series.setdefault(record.series_key, []).append(record)

    for record in series:
        _resolve_one(record, cache, report)
        _apply_rankings(record, cache)
        record.red_flags = dedupe_preserving_order(
            compute_red_flags(record, by_series.get(record.series_key, []))
        )
        if record.red_flags:
            report.flagged += 1

    return series, instances, report


def _resolve_one(record: ConferenceSeries, cache, report: ResolveReport) -> None:
    """Attach a registry venue key, or record why we could not."""
    if cache is None or not cache.available:
        report.unresolved += 1
        return

    # The reliable path: a source that already publishes the venue key. All 353
    # ccf-deadlines venues do, so no matching is needed for them at all.
    if record.dblp_key:
        venue = cache.venue(record.dblp_key)
        if venue is not None:
            _attach_venue(record, venue)
            report.resolved += 1
            return

    candidates = cache.candidates_for_acronym(normalize_acronym(record.acronym))
    if not candidates:
        report.unresolved += 1
        return

    if len(candidates) == 1:
        _attach_venue(record, candidates[0])
        report.resolved += 1
        return

    # More than one venue claims this acronym. Score on title overlap and refuse
    # if the top two are close — a wrong pick deletes a real venue silently.
    scored = sorted(
        ((_title_overlap(record, c), c) for c in candidates), key=lambda p: -p[0]
    )
    best, runner_up = scored[0], scored[1]
    if best[0] >= 0.6 and best[0] - runner_up[0] >= 0.2:
        _attach_venue(record, best[1])
        report.resolved += 1
        return

    record.dblp_candidates = [c["key"] for c in candidates]
    report.ambiguous += 1


def _attach_venue(record: ConferenceSeries, venue: dict) -> None:
    record.dblp_key = venue["key"]
    record.dblp_found = True
    record.indexed_years = int(venue.get("n_years") or 0)
    record.first_year = venue.get("first_year")
    record.last_year = venue.get("last_year")
    record.name_variants = dedupe_preserving_order(
        [*record.name_variants, *(venue.get("titles") or [])]
    )
    # Former titles are how a venue that has since been renamed still resolves.
    record.acronym_variants = dedupe_preserving_order(
        [*record.acronym_variants, *(venue.get("acronyms") or [])]
    )


def _title_overlap(record: ConferenceSeries, venue: dict) -> float:
    ours = set(normalize_title(strip_ordinal(record.full_name)).split())
    if not ours:
        return 0.0
    best = 0.0
    for title in venue.get("titles") or []:
        theirs = set(normalize_title(strip_ordinal(title)).split())
        if not theirs:
            continue
        best = max(best, len(ours & theirs) / len(ours | theirs))
    return best


def _apply_rankings(record: ConferenceSeries, cache) -> None:
    """Overlay authoritative rankings. Registry sources always win identity."""
    if cache is None or not cache.available:
        return
    ranking = cache.ranking_for(record)
    if ranking:
        # Keyed by system so CORE cannot overwrite CCF and vice versa.
        record.rankings = {**record.rankings, **ranking}
        for code in ranking.get("core", {}).get("field_codes", "").split(","):
            if code.strip():
                record.field_codes = dedupe_preserving_order(
                    [*record.field_codes, code.strip()]
                )


# --- predatory red flags -------------------------------------------------

#: Broad, unrelated subject areas appearing together in one title is the single
#: most recognisable predatory signature.
_DISCIPLINE_WORDS = (
    "engineering",
    "medicine",
    "management",
    "education",
    "economics",
    "agriculture",
    "law",
    "humanities",
    "nursing",
    "tourism",
    "psychology",
    "chemistry",
    "physics",
)
_FEE_WORDS = re.compile(
    r"\b(registration fee|publication fee|processing charge|pay(?:ment)? (?:is )?required)\b",
    re.IGNORECASE,
)
_COMMITTEE_WORDS = re.compile(
    r"\b(program committee|programme committee|technical committee|general chair|"
    r"program chair|programme chair|editorial board)\b",
    re.IGNORECASE,
)
_PUBLISHER_WORDS = re.compile(
    r"\b(springer|ieee|acm|elsevier|proceedings|lncs|usenix|mit press|wiley|"
    r"pmlr|aaai press)\b",
    re.IGNORECASE,
)
#: Fewer days than this between a CFP appearing and its deadline is not enough
#: time to write a paper, which is the point of a predatory call.
SHORT_WINDOW_DAYS = 21
#: Extensions are normal. This many on one round is not.
EXTENSION_FLAG_THRESHOLD = 3


def compute_red_flags(
    record: ConferenceSeries, instances: list[ConferenceInstance]
) -> list[str]:
    """Signals worth storing. None is conclusive alone.

    Storing them rather than acting on them lets the threshold be tuned later
    against real data instead of hard-coded now against a guess.
    """
    flags: list[str] = []
    title = f"{record.full_name} {record.acronym}".lower()

    disciplines = {word for word in _DISCIPLINE_WORDS if word in title}
    if len(disciplines) >= 3:
        flags.append("multi_discipline_title")

    corpus = "\n".join(i.cfp_text for i in instances if i.cfp_text)
    if corpus:
        if _FEE_WORDS.search(corpus):
            flags.append("fees_prominent")
        if not _COMMITTEE_WORDS.search(corpus):
            flags.append("no_committee")
        if not _PUBLISHER_WORDS.search(corpus):
            flags.append("no_publisher")

    for instance in instances:
        for deadline in instance.deadlines:
            if deadline.extension_count >= EXTENSION_FLAG_THRESHOLD:
                flags.append("repeated_extensions")
                break

    for instance in instances:
        if _short_cfp_window(instance):
            flags.append("short_cfp_window")
            break

    return flags


def _short_cfp_window(instance: ConferenceInstance) -> bool:
    """True when a CFP first appeared implausibly close to its own deadline."""
    from datetime import datetime

    if not instance.first_seen:
        return False
    deadline = min(
        (d.instant for d in instance.submission_deadlines if d.instant), default=None
    )
    if not deadline:
        return False
    try:
        seen = datetime.fromisoformat(instance.first_seen.replace("Z", "+00:00"))
        due = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    except ValueError:
        return False
    return 0 <= (due - seen).days < SHORT_WINDOW_DAYS
