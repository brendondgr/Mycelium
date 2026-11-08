"""Data-quality checks over the stored corpus.

Every hardening step claims to fix a measurable defect. Without a harness those
claims are unfalsifiable and regressions are invisible, so this module turns each
known defect into a named check that reports a count, a rate, and real examples.

Two design rules make the numbers trustworthy:

* **Checks are pure functions over records**, not queries. They run against a
  fixture list in a test exactly as they run against the live store, so a check
  can be proven to fire before it is trusted to stay silent.
* **A check that cannot be evaluated reports ``n/a``, never zero.** Zero means
  "looked and found nothing"; a corpus with no EU records has not proven anything
  about EU deadline selection, and saying "0 defects" there would be a lie that
  reads as a pass.

Severity is about the reader, not the code. ``error`` means a user would see a
wrong fact — a deadline that already passed, a duplicate presented as two
opportunities. ``warning`` means degraded quality that misleads no one on its
own. ``info`` is coverage worth watching.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

from tools.retrieval.collect.grants.normalize import normalize_title
from tools.retrieval.collect.grants.record import Opportunity

SEVERITIES = ("error", "warning", "info")

#: Beyond this a close date is not a deadline, it is a parse artifact.
FUTURE_HORIZON_YEARS = 12

#: Number prefixes that identify a funder-native source. A record whose number
#: matches one of these but which that source never contributed to is running on
#: an aggregator's thinner copy of the same announcement.
NATIVE_NUMBER_PATTERNS: dict[str, re.Pattern[str]] = {
    "nih_guide": re.compile(r"^(PA|PAR|PAS|RFA|NOT|NOFO)-", re.IGNORECASE),
    "nsf": re.compile(r"^(PD|NSF)-?\d|^\d{2}-\d{3}$", re.IGNORECASE),
}

#: Category values that are really eligibility prose, funding instruments, or
#: document-kind markers rather than subjects. Used to measure how mixed the
#: field is; step 5 routes them to typed homes.
_NOT_A_SUBJECT = re.compile(
    r"(501\(c\)|governments?\b|institutions of higher education|nonprofits?\b"
    r"|small businesses|school districts|housing authorities|see text field"
    r"|^(grant|cooperative agreement|procurement contract|other)$"
    r"|^(synopsis|forecast|pa|par|pas|rfa|not|nofo)$)",
    re.IGNORECASE,
)

#: A description that points somewhere else instead of describing anything.
_POINTER_ONLY = re.compile(r"^\s*(see |refer to |n/?a\b|none\b|tbd\b|click here)", re.IGNORECASE)

_HTML_RESIDUE = re.compile(r"<[a-zA-Z/][^>]{0,40}>|&(?:amp|nbsp|lt|gt|quot|#\d+);")

#: Two words fused where whitespace was lost ("OceanographyProgram"). Both halves
#: must be five characters or more, which is what keeps ordinary camel-case proper
#: nouns — JavaScript, PubMed — from reading as damage.
_GLUED = re.compile(r"\b[A-Za-z][a-z]{4,}[A-Z][a-z]{4,}\b")

#: Source text saying there are several deadlines, in any of the phrasings the
#: sources actually use.
_SAYS_MULTIPLE = re.compile(
    r"multiple dates|standard dates|see announcement|multiple deadlines|recurring", re.IGNORECASE
)


@dataclass
class Finding:
    """One check's result. ``total`` is the population it was evaluated over."""

    key: str
    label: str
    detail: str
    count: int
    total: int
    severity: str = "warning"
    examples: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        """False when nothing in the corpus could exercise this check."""
        return self.total > 0

    @property
    def rate(self) -> float:
        return (self.count / self.total) if self.total else 0.0

    def line(self) -> str:
        if not self.applicable:
            return f"  n/a   {self.key:<26} {self.label} (nothing to check)"
        mark = "ok  " if self.count == 0 else self.severity[:4].upper()
        return (
            f"  {mark:<5} {self.key:<26} {self.count:>5} / {self.total:<5} "
            f"({self.rate * 100:5.1f}%)  {self.label}"
        )


def _finding(
    key: str,
    label: str,
    detail: str,
    hits: Sequence[Opportunity],
    population: Sequence[Opportunity],
    severity: str = "warning",
    describe: Callable[[Opportunity], str] | None = None,
) -> Finding:
    describe = describe or (lambda r: f"{r.opportunity_number or r.source_record_id}")
    return Finding(
        key=key,
        label=label,
        detail=detail,
        count=len(hits),
        total=len(population),
        severity=severity,
        examples=[describe(record) for record in list(hits)[:5]],
    )


# --- individual checks ----------------------------------------------------
#
# Each takes the full record set plus today and returns exactly one Finding, so
# adding a check is adding one function and one registry entry.


def check_past_deadline(records: list[Opportunity], today: date) -> Finding:
    dated = [r for r in records if r.record_kind != "overlay" and r.effective_due_date]
    hits = [r for r in dated if r.effective_due_date < today.isoformat()]
    return _finding(
        "past_deadline",
        "records whose displayed deadline has already passed",
        "The headline date is the one thing this system must get right. A past date "
        "either means the prune missed it or the adapter picked the wrong element "
        "from a multi-round list.",
        hits,
        dated,
        "error",
        lambda r: f"{r.opportunity_number} shows {r.effective_due_date} ({r.source})",
    )


def check_wrong_round_selected(records: list[Opportunity], today: date) -> Finding:
    """Multi-round records whose ``close_date`` is not their final round.

    Checks the stored invariant rather than the displayed date. Display is derived
    by :meth:`Opportunity.due_on`, so comparing it against its own definition
    would be a tautology that passes however broken the data underneath is. What
    a regression *can* break is an adapter writing the wrong element of its
    deadline list into ``close_date`` — which is precisely what the EU portal did
    — so that is what gets asserted.
    """
    multi = [r for r in records if len(r.all_due_dates) > 1]
    hits = [r for r in multi if r.close_date != r.all_due_dates[-1]]
    return _finding(
        "wrong_round_selected",
        "multi-round records whose close date is not their final round",
        "close_date is the date after which an opportunity is finished, so pruning "
        "keys on it. An adapter storing the first round there instead makes a "
        "recurring call look expired while it is still running.",
        hits,
        multi,
        "error",
        lambda r: (f"{r.opportunity_number} close={r.close_date} of {r.all_due_dates[:4]}"),
    )


def check_future_posted_date(records: list[Opportunity], today: date) -> Finding:
    posted = [r for r in records if r.posted_date]
    hits = [r for r in posted if r.posted_date > today.isoformat()]
    return _finding(
        "future_posted_date",
        "records claiming to have been posted in the future",
        "'Posted' means when the funder published the notice. A future value means "
        "the adapter stored the opening date instead, which puts unpublished calls "
        "at the top of a recently-posted sort.",
        hits,
        posted,
        "error",
        lambda r: f"{r.opportunity_number} posted={r.posted_date}",
    )


def check_date_order(records: list[Opportunity], today: date) -> Finding:
    hits = [
        r
        for r in records
        if (r.open_date and r.close_date and r.open_date > r.close_date)
        or (r.close_date and r.expiration_date and r.expiration_date < r.close_date)
    ]
    return _finding(
        "date_order",
        "records whose dates contradict each other",
        "An opportunity cannot close before it opens, nor expire before its own "
        "deadline. Either is a parse error or a field read from the wrong place.",
        hits,
        records,
        "warning",
        lambda r: f"{r.opportunity_number} open={r.open_date} close={r.close_date} exp={r.expiration_date}",
    )


def check_implausible_deadline(records: list[Opportunity], today: date) -> Finding:
    dated = [r for r in records if r.close_date]
    horizon = today.replace(year=today.year + FUTURE_HORIZON_YEARS).isoformat()
    hits = [r for r in dated if r.close_date > horizon]
    return _finding(
        "implausible_deadline",
        f"deadlines more than {FUTURE_HORIZON_YEARS} years out",
        "Funders do not publish deadlines this far ahead. A date beyond the horizon "
        "is a misparsed field, not a long lead time.",
        hits,
        dated,
        "warning",
        lambda r: f"{r.opportunity_number} close={r.close_date}",
    )


def check_amount_order(records: list[Opportunity], today: date) -> Finding:
    priced = [r for r in records if r.award_ceiling is not None or r.award_floor is not None]
    hits = [
        r
        for r in priced
        if (r.award_floor is not None and r.award_ceiling is not None and r.award_floor > r.award_ceiling)
        or (
            r.award_ceiling is not None
            and r.total_program_funding is not None
            and r.award_ceiling > r.total_program_funding * 1.001
        )
    ]
    return _finding(
        "amount_order",
        "records whose award figures contradict each other",
        "A per-award ceiling above the whole programme's budget means two figures "
        "were read from fields that do not mean what the column says.",
        hits,
        priced,
        "warning",
        lambda r: f"{r.opportunity_number} floor={r.award_floor} ceil={r.award_ceiling} total={r.total_program_funding}",
    )


def check_unparsed_multi_date(records: list[Opportunity], today: date) -> Finding:
    says = [r for r in records if _SAYS_MULTIPLE.search(r.close_date_text or "")]
    hits = [r for r in says if len(r.all_due_dates) <= 1]
    return _finding(
        "unparsed_multi_date",
        "records that say they have several deadlines but store one",
        "The source told us there are multiple rounds and we kept a single date. "
        "Whichever one we kept, every other round is invisible.",
        hits,
        says,
        "error",
        lambda r: f"{r.opportunity_number} text={r.close_date_text[:40]!r}",
    )


def check_unflagged_duplicates(records: list[Opportunity], today: date) -> Finding:
    # Full title, not a prefix. Truncating manufactured false groups: NIH
    # publishes "…(Parent K23 Independent Clinical Trial Not Allowed)" alongside
    # "…(Parent K23 Independent Basic Experimental Studies with Humans
    # Required)", which agree for the first 70 characters and are different
    # announcements with different eligibility. A check that calls those
    # duplicates is asking dedupe to commit the exact error it exists to avoid.
    groups: dict[tuple[str, str | None], list[Opportunity]] = defaultdict(list)
    for record in records:
        if record.title:
            groups[(normalize_title(record.title), record.close_date)].append(record)

    duplicated = [group for group in groups.values() if len(group) > 1]
    population = [record for group in duplicated for record in group]
    hits = [
        record
        for group in duplicated
        if not any(r.review_candidates for r in group)
        for record in group
    ]
    return _finding(
        "unflagged_duplicates",
        "same-title same-deadline records not flagged as related",
        "Two records with an identical title and deadline are at minimum variants of "
        "one opportunity. They must never be merged automatically, but presenting "
        "them as unrelated results is its own error.",
        hits,
        population,
        "error",
        lambda r: f"{r.opportunity_number} ({r.source}) {r.title[:44]}",
    )


def check_missing_native_data(records: list[Opportunity], today: date) -> Finding:
    population: list[Opportunity] = []
    hits: list[Opportunity] = []
    for record in records:
        number = record.opportunity_number or ""
        for source, pattern in NATIVE_NUMBER_PATTERNS.items():
            if pattern.match(number):
                population.append(record)
                if source not in record.contributing_sources:
                    hits.append(record)
                break
    return _finding(
        "missing_native_data",
        "funder-numbered records carrying no funder-native data",
        "A record numbered by NIH or NSF but assembled only from an aggregator has "
        "the aggregator's thinner text and none of the funder's structured fields. "
        "It ranks worse and filters not at all.",
        hits,
        population,
        "warning",
        lambda r: f"{r.opportunity_number} from {sorted(set(r.contributing_sources))}",
    )


def check_missing_identifier(records: list[Opportunity], today: date) -> Finding:
    hits = [r for r in records if not (r.opportunity_number or "").strip()]
    return _finding(
        "missing_identifier",
        "records with no funder-assigned number",
        "Without a number a record falls back to a source-local key, so it can never "
        "merge with the same opportunity arriving from anywhere else.",
        hits,
        records,
        "warning",
        lambda r: f"{r.source}: {r.title[:56]}",
    )


def check_empty_description(records: list[Opportunity], today: date) -> Finding:
    hits = [r for r in records if not (r.description or "").strip()]
    return _finding(
        "empty_description",
        "records with no descriptive text at all",
        "Descriptive text is the payload. A record without it is embedded on its "
        "title alone and matches on noise.",
        hits,
        records,
        "error",
        lambda r: f"{r.opportunity_number} ({r.source}) {r.title[:44]}",
    )


def check_pointer_description(records: list[Opportunity], today: date) -> Finding:
    described = [r for r in records if (r.description or "").strip()]
    hits = [r for r in described if _POINTER_ONLY.match(r.description) and len(r.description) < 400]
    return _finding(
        "pointer_description",
        "descriptions that point elsewhere instead of describing",
        "'See the attached documents' carries no subject matter, so the record is "
        "effectively undescribed for retrieval purposes.",
        hits,
        described,
        "warning",
        lambda r: f"{r.opportunity_number} {r.description[:52]!r}",
    )


def check_thin_description(records: list[Opportunity], today: date) -> Finding:
    described = [r for r in records if (r.description or "").strip()]
    hits = [r for r in described if len(r.description) < 400]
    return _finding(
        "thin_description",
        "descriptions under 400 characters",
        "Retrieval partly measures how much text a record has. Sources with terse "
        "feeds are systematically out-ranked by verbose ones regardless of fit.",
        hits,
        described,
        "info",
        lambda r: f"{r.opportunity_number} ({r.source}) {len(r.description)} chars",
    )


def check_html_residue(records: list[Opportunity], today: date) -> Finding:
    described = [r for r in records if (r.description or "").strip()]
    hits = [r for r in described if _HTML_RESIDUE.search(r.description)]
    return _finding(
        "html_residue",
        "descriptions still carrying markup or entities",
        "Tags and entities that survived stripping end up in the embedded text and "
        "on screen.",
        hits,
        described,
        "warning",
        lambda r: f"{r.opportunity_number} {(_HTML_RESIDUE.search(r.description) or [''])[0]!r}",
    )


def check_glued_words(records: list[Opportunity], today: date) -> Finding:
    described = [r for r in records if (r.description or "").strip()]
    hits = [r for r in described if _GLUED.search(r.description[:4000])]
    return _finding(
        "glued_words",
        "descriptions with words fused by lost whitespace",
        "Usually upstream damage in the source's own data rather than our parsing, "
        "but it breaks tokenization, so it is worth knowing which source is worst "
        "and whether a native copy exists.",
        hits,
        described,
        "info",
        lambda r: f"{r.opportunity_number} ({r.source}) {(_GLUED.search(r.description[:4000]) or ['?'])[0]}",
    )


def check_mixed_categories(records: list[Opportunity], today: date) -> Finding:
    categorized = [r for r in records if r.categories]
    hits = [r for r in categorized if any(_NOT_A_SUBJECT.search(c) for c in r.categories)]
    return _finding(
        "mixed_categories",
        "records whose subject list holds non-subjects",
        "Eligibility prose, funding instruments and document-kind markers stored "
        "alongside subjects make the field unusable as a facet and inject "
        "boilerplate into the embedding.",
        hits,
        categorized,
        "warning",
        lambda r: f"{r.opportunity_number} {[c for c in r.categories if _NOT_A_SUBJECT.search(c)][:1]}",
    )


def check_unfilterable(records: list[Opportunity], today: date) -> Finding:
    """Records carrying no structured facet at all.

    A record with a deadline, a title and nothing else can only ever be found by
    searching its text. Every facet below was recoverable from a payload we
    already store, so this measures how much of the corpus is still opaque to a
    filter rather than how much the sources withheld.
    """
    hits = [
        record
        for record in records
        if not any(
            (
                record.applicant_types,
                record.funding_instruments,
                record.activity_codes,
                record.assistance_listings,
                record.action_types,
                record.opportunity_category,
                record.cost_sharing is not None,
            )
        )
    ]
    return _finding(
        "unfilterable",
        "records with no structured facet of any kind",
        "Such a record can only be reached by full-text search. Any filter the "
        "user applies excludes it, however well it actually fits.",
        hits,
        records,
        "warning",
        lambda r: f"{r.opportunity_number} ({r.source})",
    )


def check_unresolved_parent(records: list[Opportunity], today: date) -> Finding:
    children = [r for r in records if r.record_kind in {"topic", "overlay"}]
    hits = [r for r in children if r.unresolved_parent]
    return _finding(
        "unresolved_parent",
        "topics and overlays pointing at a parent we do not have",
        "A child record whose parent is missing cannot show its own deadline or "
        "eligibility, because those live on the parent.",
        hits,
        children,
        "info",
        lambda r: f"{r.opportunity_number} -> {r.parent_opportunity_number}",
    )


#: Every check, in report order. Errors first so the summary reads worst-first.
CHECKS: tuple[Callable[[list[Opportunity], date], Finding], ...] = (
    check_past_deadline,
    check_wrong_round_selected,
    check_future_posted_date,
    check_unparsed_multi_date,
    check_unflagged_duplicates,
    check_empty_description,
    check_missing_native_data,
    check_missing_identifier,
    check_date_order,
    check_amount_order,
    check_implausible_deadline,
    check_pointer_description,
    check_html_residue,
    check_mixed_categories,
    check_unfilterable,
    check_thin_description,
    check_glued_words,
    check_unresolved_parent,
)


def run_checks(records: list[Opportunity], today: date | None = None) -> list[Finding]:
    today = today or date.today()
    return [check(records, today) for check in CHECKS]


# --- reporting ------------------------------------------------------------


def format_report(findings: list[Finding], *, baseline: dict[str, int] | None = None) -> str:
    lines = ["data quality", ""]
    for severity in SEVERITIES:
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue
        lines.append(f"{severity}s")
        for finding in group:
            line = finding.line()
            if baseline is not None and finding.key in baseline and finding.applicable:
                delta = finding.count - baseline[finding.key]
                if delta:
                    line += f"   [{delta:+d} vs baseline]"
                else:
                    line += "   [unchanged]"
            lines.append(line)
        lines.append("")

    failures = [f for f in findings if f.severity == "error" and f.count]
    lines.append(
        f"{len(failures)} error-level check(s) failing, "
        f"{sum(f.count for f in failures)} affected records"
    )
    return "\n".join(lines)


def format_detail(findings: list[Finding]) -> str:
    lines = []
    for finding in findings:
        if not finding.count:
            continue
        lines.append(f"\n{finding.key}  [{finding.severity}]  {finding.count}/{finding.total}")
        lines.append(f"  {finding.detail}")
        for example in finding.examples:
            lines.append(f"    - {example}")
    return "\n".join(lines)


def as_baseline(findings: list[Finding]) -> dict[str, int]:
    """Counts only, for writing to disk and diffing a later run against."""
    return {finding.key: finding.count for finding in findings if finding.applicable}
