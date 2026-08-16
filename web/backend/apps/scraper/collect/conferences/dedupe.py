"""Stage 5: deduplication, in four layers applied in order.

The ordering is not stylistic. Layers 1–3 are reliable and cheap; layer 4 is a
heuristic. Running the heuristic over records the earlier layers would have
matched exactly just gives it more chances to be wrong.

**The critical rule**: layer 4 never merges. It attaches a review flag and leaves
both records standing. Acronym collisions across disciplines are common — ``SAC``
is both the ACM Symposium on Applied Computing and Selected Areas in Cryptography
— and a false merge silently deletes a real venue with no trace, which is
strictly worse than a duplicate. A duplicate is merely annoying and visible.

Layers 3 and 4 arrive in P5.5; layers 1 and 2 are here from the start because
without them the same venue from one source lands twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.scraper.collect.conferences.record import ConferenceInstance, ConferenceSeries
from apps.scraper.collect.conferences.store import merge_deadlines
from apps.scraper.collect.core.text import dedupe_preserving_order


@dataclass
class DedupeReport:
    series_in: int = 0
    instances_in: int = 0
    layer1_collapsed: int = 0
    layer2_merged: int = 0
    layer3_merged: int = 0
    layer4_flagged: int = 0
    series_out: int = 0
    instances_out: int = 0
    #: (key_a, key_b, similarity) for human review. Never merged.
    review_pairs: list[tuple[str, str, float]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"series in={self.series_in} out={self.series_out} | "
            f"instances in={self.instances_in} L1={self.layer1_collapsed} "
            f"L2={self.layer2_merged} L3={self.layer3_merged} "
            f"L4_flagged={self.layer4_flagged} out={self.instances_out}"
        )


def deduplicate(
    series: list[ConferenceSeries], instances: list[ConferenceInstance]
) -> tuple[list[ConferenceSeries], list[ConferenceInstance], DedupeReport]:
    report = DedupeReport(series_in=len(series), instances_in=len(instances))

    merged_series = _merge_series_by_key(series, report)
    stage1 = _layer1_within_source(instances, report)
    stage2 = _layer2_by_series_and_edition(stage1, report)
    stage3 = _layer3_by_event_dates(stage2, report)
    stage4 = _layer4_fuzzy_flag(stage3, merged_series, report)

    report.series_out = len(merged_series)
    report.instances_out = len(stage4)
    return merged_series, stage4, report


# --- series --------------------------------------------------------------


def _merge_series_by_key(
    series: list[ConferenceSeries], report: DedupeReport
) -> list[ConferenceSeries]:
    by_key: dict[str, ConferenceSeries] = {}
    for record in series:
        existing = by_key.get(record.series_key)
        if existing is None:
            by_key[record.series_key] = record
            continue
        by_key[record.series_key] = merge_series(existing, record)
    return list(by_key.values())


def merge_series(left: ConferenceSeries, right: ConferenceSeries) -> ConferenceSeries:
    """Registry facts always win; everything descriptive takes the fuller value.

    Rankings merge per system rather than wholesale: CCF, CORE and THCPL arrive
    from different places and overwriting the dict would drop two of three.
    """
    result = left.copy()
    result.acronym = left.acronym or right.acronym
    result.full_name = _longer(left.full_name, right.full_name)
    result.acronym_variants = dedupe_preserving_order(
        [*left.acronym_variants, *right.acronym_variants, right.acronym]
    )
    result.name_variants = dedupe_preserving_order(
        [*left.name_variants, *right.name_variants, right.full_name]
    )
    result.field_codes = dedupe_preserving_order([*left.field_codes, *right.field_codes])
    result.rankings = {**right.rankings, **left.rankings}

    # Registry identity is authoritative wherever it exists.
    result.dblp_key = left.dblp_key or right.dblp_key
    result.dblp_found = left.dblp_found or right.dblp_found
    result.indexed_years = max(left.indexed_years, right.indexed_years)
    result.first_year = _min_year(left.first_year, right.first_year)
    result.last_year = _max_year(left.last_year, right.last_year)
    result.dblp_candidates = dedupe_preserving_order(
        [*left.dblp_candidates, *right.dblp_candidates]
    )

    result.red_flags = dedupe_preserving_order([*left.red_flags, *right.red_flags])
    result.contributing_sources = dedupe_preserving_order(
        [*left.contributing_sources, *right.contributing_sources]
    )
    # Keep the more restrictive licence visible rather than losing it in a merge.
    result.license = "; ".join(
        dedupe_preserving_order([left.license, right.license])
    ).strip("; ")
    return result


# --- layer 1 -------------------------------------------------------------


def _layer1_within_source(
    instances: list[ConferenceInstance], report: DedupeReport
) -> list[ConferenceInstance]:
    """Collapse the same source record arriving more than once.

    Legitimate whenever collection is driven by several queries or several
    listing pages. Deadlines and topics are merged rather than overwritten.
    """
    by_key: dict[tuple[str, str], ConferenceInstance] = {}
    for record in instances:
        existing = by_key.get(record.source_key)
        if existing is None:
            by_key[record.source_key] = record
            continue
        report.layer1_collapsed += 1
        existing.deadlines, _ = merge_deadlines(existing.deadlines, record.deadlines)
        existing.topics = dedupe_preserving_order([*existing.topics, *record.topics])
        if len(record.cfp_text) > len(existing.cfp_text):
            existing.cfp_text = record.cfp_text
    return list(by_key.values())


# --- layer 2 -------------------------------------------------------------


def _layer2_by_series_and_edition(
    instances: list[ConferenceInstance], report: DedupeReport
) -> list[ConferenceInstance]:
    """Merge across sources on the canonical series key plus edition.

    The reliable layer. Only records that reached the resolve stage with a real
    series key participate; anything unresolved passes through untouched rather
    than being guessed at.
    """
    merged: dict[str, ConferenceInstance] = {}
    passthrough: list[ConferenceInstance] = []

    for record in instances:
        if not record.series_key or not record.year_label:
            passthrough.append(record)
            continue
        key = record.instance_key
        existing = merged.get(key)
        if existing is None:
            merged[key] = record
        else:
            merged[key] = merge_instance(existing, record)
            report.layer2_merged += 1

    return [*merged.values(), *passthrough]


def merge_instance(
    left: ConferenceInstance, right: ConferenceInstance
) -> ConferenceInstance:
    """Field-level precedence, decided per field because no source wins at all.

    The rules that matter:

    * **Deadlines** — the structured repository beats a scraped wiki, because it
      carries explicit timezones and the wiki carries none. Merged rather than
      replaced, so a source contributing only a notification date does not wipe
      out another's submission rounds.
    * **CFP text** — whoever has more of it. OpenReview must never win here: it
      has no description at all, only 601 copies of the same boilerplate.
    * **Contributing sources** — union, always.
    """
    native, other = (left, right) if _is_native(left) else (right, left)
    decisive = _is_native(left) != _is_native(right)

    result = native.copy()
    result.title = _longer(native.title, other.title)
    result.acronym = native.acronym or other.acronym
    result.cfp_text = _native_first(native.cfp_text, other.cfp_text, decisive)
    result.topics = dedupe_preserving_order([*native.topics, *other.topics])

    # Dates: take whichever side actually has one.
    result.event_start = native.event_start or other.event_start
    result.event_end = native.event_end or other.event_end
    result.event_dates_text = native.event_dates_text or other.event_dates_text

    result.city = native.city or other.city
    result.country_code = native.country_code or other.country_code
    result.place_text = native.place_text or other.place_text
    result.is_virtual = native.is_virtual or other.is_virtual
    result.is_hybrid = native.is_hybrid or other.is_hybrid
    result.url = native.url or other.url
    result.source_url = native.source_url or other.source_url

    # Deadlines from the source with an explicit timezone basis lead, so a
    # bare-date source cannot overwrite a properly-zoned instant.
    leading, following = _by_timezone_quality(native, other)
    result.deadlines, _ = merge_deadlines(list(leading.deadlines), list(following.deadlines))

    result.contributing_sources = dedupe_preserving_order(
        [*native.contributing_sources, *other.contributing_sources]
    )
    result.review_candidates = dedupe_preserving_order(
        [*native.review_candidates, *other.review_candidates]
    )
    result.quality_warnings = dedupe_preserving_order(
        [*native.quality_warnings, *other.quality_warnings]
    )
    result.license = "; ".join(
        dedupe_preserving_order([native.license, other.license])
    ).strip("; ")
    # Both raw payloads are kept. Discarding one defeats the point of keeping
    # raw payloads at all.
    result.raw = {"merged": True, native.source: native.raw, other.source: other.raw}
    return result


# --- layer 3 -------------------------------------------------------------


def _layer3_by_event_dates(
    instances: list[ConferenceInstance], report: DedupeReport
) -> list[ConferenceInstance]:
    """Match editions of one series whose year labels disagree.

    Year labels and event dates genuinely disagree: an edition labelled 2026 can
    be held in December 2025 or January 2027, and six instances in the structured
    corpus contradict their own date string. So two records sharing a series key
    and overlapping event dates are the same edition even when their labels
    differ by one.

    Only records that already carry a resolved series key participate. This is
    still an identity match, not a similarity guess.
    """
    by_series: dict[str, list[ConferenceInstance]] = {}
    passthrough: list[ConferenceInstance] = []
    for record in instances:
        if record.series_key and record.event_start:
            by_series.setdefault(record.series_key, []).append(record)
        else:
            passthrough.append(record)

    out: list[ConferenceInstance] = []
    for group in by_series.values():
        survivors: list[ConferenceInstance] = []
        for record in group:
            match = next(
                (
                    other
                    for other in survivors
                    if other.record_kind == record.record_kind
                    and _same_edition(other, record)
                ),
                None,
            )
            if match is None:
                survivors.append(record)
                continue
            survivors[survivors.index(match)] = merge_instance(match, record)
            report.layer3_merged += 1
        out.extend(survivors)

    return [*out, *passthrough]


def _same_edition(left: ConferenceInstance, right: ConferenceInstance) -> bool:
    """Same series, and event dates close enough to be one edition."""
    if left.year_label == right.year_label:
        return True
    if not (left.event_start and right.event_start):
        return False
    from datetime import date

    try:
        a = date.fromisoformat(left.event_start)
        b = date.fromisoformat(right.event_start)
    except ValueError:
        return False
    # An edition held once a year; anything inside a season is the same one.
    return abs((a - b).days) <= 45


# --- layer 4 -------------------------------------------------------------

#: Title similarity above which two records with no shared key are worth a human
#: look. Deliberately permissive — this only raises a flag.
FUZZY_TITLE_THRESHOLD = 0.90


def _layer4_fuzzy_flag(
    instances: list[ConferenceInstance],
    series: list[ConferenceSeries],
    report: DedupeReport,
) -> list[ConferenceInstance]:
    """Flag likely duplicates that share no key. **Never merges.**

    Acronym collisions across disciplines are common and a false merge silently
    destroys a real venue, leaving no trace of having done so. A duplicate is
    merely annoying and visible; a bad merge is invisible and permanent. So this
    layer records a pair for review and leaves both records standing.
    """
    from difflib import SequenceMatcher

    from apps.scraper.collect.core.text import normalize_title

    resolved = {s.series_key: s for s in series}
    candidates = [record for record in instances if record.title or record.acronym]

    # Bucket first so this is not quadratic over the whole corpus.
    buckets: dict[str, list[ConferenceInstance]] = {}
    for record in candidates:
        key = f"{normalize_title(record.title)[:18]}|{record.year_label}"
        buckets.setdefault(key, []).append(record)

    for group in buckets.values():
        if len(group) < 2:
            continue
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if left.source == right.source:
                    continue  # layer 1 already had its say
                if left.series_key and left.series_key == right.series_key:
                    continue  # layers 2 and 3 settled it
                if _registry_says_different(left, right, resolved):
                    continue  # dblp asserts these are not the same venue
                score = SequenceMatcher(
                    None, normalize_title(left.title), normalize_title(right.title)
                ).ratio()
                if score < FUZZY_TITLE_THRESHOLD:
                    continue
                left.review_candidates.append(right.instance_key)
                right.review_candidates.append(left.instance_key)
                report.review_pairs.append(
                    (left.instance_key, right.instance_key, round(score, 3))
                )
                report.layer4_flagged += 1

    return instances


def _registry_says_different(
    left: ConferenceInstance,
    right: ConferenceInstance,
    resolved: dict[str, ConferenceSeries],
) -> bool:
    """Honour dblp's hand-curated do-not-merge assertions before any heuristic."""
    a, b = resolved.get(left.series_key), resolved.get(right.series_key)
    if not a or not b or not a.dblp_key or not b.dblp_key:
        return False
    return a.dblp_key != b.dblp_key and bool(a.dblp_found and b.dblp_found)


def _by_timezone_quality(
    left: ConferenceInstance, right: ConferenceInstance
) -> tuple[ConferenceInstance, ConferenceInstance]:
    """Order two records by how trustworthy their deadline basis is."""

    def score(record: ConferenceInstance) -> int:
        bases = {d.basis for d in record.deadlines if d.basis}
        if not bases:
            return 0
        if all(b.startswith("inferred") for b in bases):
            return 1
        return 2

    return (left, right) if score(left) >= score(right) else (right, left)


def _is_native(record: ConferenceInstance) -> bool:
    from apps.scraper.collect.conferences.adapters import venue_native_sources

    return record.source in venue_native_sources()


def _native_first(native: str, other: str, decisive: bool) -> str:
    if decisive and native.strip():
        return native
    return _longer(native, other)


def _longer(primary: str, fallback: str) -> str:
    if len(primary or "") >= len(fallback or ""):
        return primary or fallback or ""
    return fallback


def _min_year(a: int | None, b: int | None) -> int | None:
    values = [v for v in (a, b) if v]
    return min(values) if values else None


def _max_year(a: int | None, b: int | None) -> int | None:
    values = [v for v in (a, b) if v]
    return max(values) if values else None
