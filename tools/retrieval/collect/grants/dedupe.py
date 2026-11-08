"""Stage 4: three layers of deduplication, applied in order.

The ordering is not stylistic. Layer 2 is reliable and cheap; layer 3 is a
heuristic. Running layer 3 over records that layer 2 would have matched exactly
just gives the heuristic more chances to be wrong.

**The critical rule**: layer 3 never merges. It attaches a review flag and leaves
both records standing. A false merge silently deletes an opportunity a user should
have seen and leaves no trace of having done so — strictly worse than a duplicate,
which is merely annoying and visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from tools.retrieval.collect.grants.normalize import (
    dedupe_preserving_order,
    normalize_opportunity_number,
    normalize_title,
)
from tools.retrieval.collect.grants.record import Opportunity

#: Title similarity above which two records with no shared identifier are worth a
#: human look. Tuned to be permissive — this only raises a flag.
FUZZY_TITLE_THRESHOLD = 0.90


@dataclass
class DedupeReport:
    input_count: int = 0
    layer1_collapsed: int = 0
    layer2_merged: int = 0
    layer3_flagged: int = 0
    output_count: int = 0
    #: (stable_key_a, stable_key_b, similarity) for human review.
    review_pairs: list[tuple[str, str, float]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"in={self.input_count} L1_collapsed={self.layer1_collapsed} "
            f"L2_merged={self.layer2_merged} L3_flagged={self.layer3_flagged} "
            f"out={self.output_count}"
        )


def deduplicate(records: list[Opportunity]) -> tuple[list[Opportunity], DedupeReport]:
    report = DedupeReport(input_count=len(records))

    stage1 = _layer1_within_source(records, report)
    stage2 = _layer2_by_identifier(stage1, report)
    stage3 = _layer3_fuzzy_flag(stage2, report)

    report.output_count = len(stage3)
    return stage3, report


# --- layer 1 -------------------------------------------------------------


def _layer1_within_source(records: list[Opportunity], report: DedupeReport) -> list[Opportunity]:
    """Collapse the same source record arriving more than once.

    Legitimate whenever collection is driven by several queries. Tags and match
    reasons are merged rather than overwritten, so no query's contribution is lost.
    """
    by_key: dict[tuple[str, str], Opportunity] = {}
    for record in records:
        existing = by_key.get(record.source_key)
        if existing is None:
            by_key[record.source_key] = record
            continue
        report.layer1_collapsed += 1
        existing.categories = dedupe_preserving_order([*existing.categories, *record.categories])
        existing.additional_due_dates = dedupe_preserving_order(
            [*existing.additional_due_dates, *record.additional_due_dates]
        )
        # Prefer whichever copy actually carries description text.
        if len(record.description) > len(existing.description):
            existing.description = record.description
    return list(by_key.values())


# --- layer 2 -------------------------------------------------------------


def _layer2_by_identifier(records: list[Opportunity], report: DedupeReport) -> list[Opportunity]:
    """Merge across sources on the normalized funder-assigned number.

    This is the reliable layer, and it carries most of the weight: the NIH guide
    feed against Grants.gov is by far the largest overlap in the system.
    """
    merged: dict[str, Opportunity] = {}
    passthrough: list[Opportunity] = []

    for record in records:
        number = normalize_opportunity_number(record.opportunity_number)
        if not number:
            passthrough.append(record)
            continue
        # Kind is part of the key: an overlay that quotes its parent's number is
        # not the same record as the parent.
        key = f"{number}|{record.record_kind}"
        existing = merged.get(key)
        if existing is None:
            merged[key] = record
        else:
            merged[key] = merge_pair(existing, record)
            report.layer2_merged += 1

    return [*merged.values(), *passthrough]


def merge_pair(left: Opportunity, right: Opportunity) -> Opportunity:
    """Field-level precedence, per briefing section 5.

    Decided per field, not per record, because neither source is better at
    everything: the funder writes better prose, the aggregator types its dates.
    """
    native, other = (left, right) if _is_native(left) else (right, left)
    aggregator = other if _is_native(left) else left
    # Exactly one side being funder-native is what makes the precedence rule
    # meaningful. When both or neither are, there is no authority to defer to and
    # the helpers below fall back to "longer text wins" / "populated wins".
    decisive = _is_native(left) != _is_native(right)

    result = native.copy()

    # Descriptive: the funder-native source wins outright when it has text.
    #
    # Not "whichever is longer". The rationale for the rule is that funder text is
    # usually longer and richer, but the rule is the source, not the length —
    # encoding the rationale instead lets an aggregator win with worse text. A
    # real case from the corpus: NSF publishes PD 98-1670 as "The Chemical
    # Oceanography Program supports…" while Grants.gov's copy of the same
    # paragraph has lost its non-breaking spaces ("TheChemical
    # OceanographyProgram"). The mangled copy is longer, so a length rule picks it.
    result.description = _native_first(native.description, other.description, decisive)
    result.eligibility = _native_first(native.eligibility, other.eligibility, decisive)
    result.title = native.title or other.title
    result.funder = native.funder or other.funder
    result.funder_subunit = native.funder_subunit or other.funder_subunit
    result.categories = dedupe_preserving_order([*native.categories, *other.categories])

    # Structured dates and money: the aggregator wins where it has a value.
    result.posted_date = _prefer(aggregator.posted_date, native.posted_date)
    result.open_date = _prefer(aggregator.open_date, native.open_date)
    result.close_date = _prefer(aggregator.close_date, native.close_date)
    result.close_date_text = _prefer(aggregator.close_date_text, native.close_date_text) or ""
    result.expiration_date = _prefer(aggregator.expiration_date, native.expiration_date)
    result.additional_due_dates = dedupe_preserving_order(
        [*aggregator.additional_due_dates, *native.additional_due_dates]
    )
    # The letter-of-intent deadline only exists on the funder's own feed, so there
    # is nothing to weigh — take whichever side has it.
    result.original_close_date = _prefer(
        aggregator.original_close_date, native.original_close_date
    )
    result.intent_date = _prefer(native.intent_date, other.intent_date)
    result.intent_date_text = _prefer(native.intent_date_text, other.intent_date_text) or ""
    # Inference is contagious: if either side's rounds were derived, the merged
    # set contains derived dates and must say so.
    result.dates_inferred = native.dates_inferred or other.dates_inferred
    result.award_floor = _prefer(aggregator.award_floor, native.award_floor)
    result.award_ceiling = _prefer(aggregator.award_ceiling, native.award_ceiling)
    result.total_program_funding = _prefer(
        aggregator.total_program_funding, native.total_program_funding
    )
    result.expected_awards = _prefer(aggregator.expected_awards, native.expected_awards)
    result.currency = native.currency or aggregator.currency

    # Structured facets: union the lists. Unlike prose, where one source has to
    # win because two paragraphs cannot both be the description, a record really
    # can be both a grant and a cooperative agreement, and really can carry an
    # activity code from the funder and an applicant-type list from the
    # aggregator. Dropping either side would narrow a filter for no reason.
    result.applicant_types = dedupe_preserving_order(
        [*native.applicant_types, *other.applicant_types]
    )
    result.funding_instruments = dedupe_preserving_order(
        [*native.funding_instruments, *other.funding_instruments]
    )
    result.activity_codes = dedupe_preserving_order([*native.activity_codes, *other.activity_codes])
    result.assistance_listings = dedupe_preserving_order(
        [*native.assistance_listings, *other.assistance_listings]
    )
    result.action_types = dedupe_preserving_order([*native.action_types, *other.action_types])
    result.topic_keywords = dedupe_preserving_order([*native.topic_keywords, *other.topic_keywords])
    result.participating_units = dedupe_preserving_order(
        [*native.participating_units, *other.participating_units]
    )
    result.related_numbers = dedupe_preserving_order(
        [*native.related_numbers, *other.related_numbers]
    )
    # A stated requirement beats an omission either way round: whichever source
    # bothered to say is the one that knows.
    result.cost_sharing = (
        native.cost_sharing if native.cost_sharing is not None else other.cost_sharing
    )
    result.agency_code = _prefer(aggregator.agency_code, native.agency_code) or ""
    result.funder_canonical = _prefer(native.funder_canonical, other.funder_canonical) or ""
    result.opportunity_category = (
        _prefer(native.opportunity_category, other.opportunity_category) or ""
    )
    result.deadline_model = _prefer(native.deadline_model, other.deadline_model) or ""

    # Identity: keep whichever side actually knows the parent link.
    result.parent_opportunity_number = _prefer(
        native.parent_opportunity_number, other.parent_opportunity_number
    )
    result.unresolved_parent = native.unresolved_parent and other.unresolved_parent
    result.source_url = native.source_url or other.source_url

    # Contributing sources: union, always.
    result.contributing_sources = dedupe_preserving_order(
        [*native.contributing_sources, *other.contributing_sources]
    )
    result.review_candidates = dedupe_preserving_order(
        [*native.review_candidates, *other.review_candidates]
    )
    # Both raw payloads are kept. Discarding one would defeat the point of
    # retaining raw payloads at all.
    result.raw = {"merged": True, native.source: native.raw, other.source: other.raw}
    return result


def _is_native(record: Opportunity) -> bool:
    from tools.retrieval.collect.grants.adapters import funder_native_sources

    return record.source in funder_native_sources()


def _native_first(native: str, other: str, decisive: bool) -> str:
    """The funder's text when there is a funder side and it said something.

    Falls back to length only when neither side has precedence over the other.
    """
    if decisive and native.strip():
        return native
    return _longer(native, other)


def _longer(primary: str, fallback: str) -> str:
    if len(primary or "") >= len(fallback or ""):
        return primary or fallback or ""
    return fallback


def _prefer(primary, fallback):
    return primary if primary not in (None, "", 0) else fallback


# --- layer 3 -------------------------------------------------------------


def _layer3_fuzzy_flag(records: list[Opportunity], report: DedupeReport) -> list[Opportunity]:
    """Flag likely duplicates that share no identifier. Never merges.

    Compares **within a source as well as across sources**. The original version
    skipped same-source pairs on the reasoning that two records from one source
    with different ids are two records and layer 1 had already had its say. That
    reasoning was wrong in a measurable way: of 49 groups in the live corpus
    sharing a normalized title and deadline, 47 were within a single source and
    so were never examined at all. The EU portal publishes the same research
    topic under two call identifiers — ``HORIZON-EURATOM-2026-01-06`` and its
    ``-LS-`` lump-sum twin — and a reader saw two unrelated-looking results with
    identical text.

    Layer 1 does not cover this: it keys on the source's own record id, which by
    definition differs for two separately-published records.

    **Still never merges.** These variants are often genuinely distinct — the
    lump-sum and standard versions of a topic have different funding rules — so
    the outcome is a visible link, not a silent deletion.
    """
    candidates = [record for record in records if record.title]

    by_bucket: dict[str, list[Opportunity]] = {}
    for record in candidates:
        bucket = f"{normalize_title(record.title)[:24]}|{record.close_date or ''}"
        by_bucket.setdefault(bucket, []).append(record)

    for bucket_records in by_bucket.values():
        if len(bucket_records) < 2:
            continue
        for index, left in enumerate(bucket_records):
            for right in bucket_records[index + 1 :]:
                if normalize_opportunity_number(left.opportunity_number) and (
                    normalize_opportunity_number(left.opportunity_number)
                    == normalize_opportunity_number(right.opportunity_number)
                ):
                    continue  # layer 2 handled it
                if left.stable_key == right.stable_key:
                    continue
                if _is_parent_of(left, right) or _is_parent_of(right, left):
                    # A topic inherits its parent's title and dates. That pair is
                    # an already-recorded relationship, not a suspected duplicate,
                    # and flagging it would bury the real ones in noise.
                    continue
                score = _similarity(left, right)
                if score < FUZZY_TITLE_THRESHOLD:
                    continue
                left.review_candidates.append(right.stable_key)
                right.review_candidates.append(left.stable_key)
                report.review_pairs.append((left.stable_key, right.stable_key, round(score, 3)))
                report.layer3_flagged += 1

    return records


def _is_parent_of(parent: Opportunity, child: Opportunity) -> bool:
    if not child.parent_opportunity_number:
        return False
    return normalize_opportunity_number(
        child.parent_opportunity_number
    ) == normalize_opportunity_number(parent.opportunity_number)


def _similarity(left: Opportunity, right: Opportunity) -> float:
    if left.close_date and right.close_date and left.close_date != right.close_date:
        return 0.0
    title_score = SequenceMatcher(
        None, normalize_title(left.title), normalize_title(right.title)
    ).ratio()
    return 0.8 * title_score + 0.2 * _funder_agreement(left, right)


def _funder_agreement(left: Opportunity, right: Opportunity) -> float:
    """Corroboration, not a gate: the same opportunity is named differently by an
    aggregator and by the funder itself.

    Prefers the canonical identity over string similarity now that both exist.
    The case that forced this: DURIP is published as separate announcements by
    the Navy and the Army with an identical title and deadline. Comparing
    "Office of Naval Research" against "Dept of the Army -- Materiel Command" as
    strings scored 0.34 and dragged a genuine variant pair under the threshold,
    even though both records agree they are Department of Defense.
    """
    if left.agency_code and left.agency_code == right.agency_code:
        return 1.0
    if left.funder_canonical and left.funder_canonical == right.funder_canonical:
        return 1.0
    return SequenceMatcher(None, normalize_title(left.funder), normalize_title(right.funder)).ratio()


# --- overlay resolution --------------------------------------------------


def resolve_overlay_parents(records: list[Opportunity]) -> int:
    """Mark every overlay whose named parent is not present in the corpus.

    An unresolved parent is not an error to swallow — the record still carries
    real subject text — but it must be visibly flagged rather than quietly
    treated as if the link worked.
    """
    known = {
        normalize_opportunity_number(record.opportunity_number)
        for record in records
        if record.opportunity_number
    }
    unresolved = 0
    for record in records:
        if record.record_kind != "overlay":
            continue
        parent = normalize_opportunity_number(record.parent_opportunity_number or "")
        if not parent or parent not in known:
            record.unresolved_parent = True
            unresolved += 1
        else:
            record.unresolved_parent = False
    return unresolved
