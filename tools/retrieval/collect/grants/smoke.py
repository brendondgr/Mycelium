"""The section 9 smoke checklist, as code rather than a wiki page.

Ten checks, run after every phase. Two of them are the ones that actually catch
regressions and both are easy to fake, so neither is faked here:

* **Idempotency** re-runs the full pipeline over the *same* raw payloads and
  requires zero inserts and zero updates. It works because the store refuses to
  touch ``last_fetched`` when nothing else changed — otherwise every run would
  report an update and the check would be unfalsifiable.
* **Offline parse** re-runs stage 2 with an HTTP client that raises on any network
  access, proving the fetch/parse seam is real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from tools.retrieval.collect.grants.dedupe import DedupeReport
from tools.retrieval.collect.grants.normalize import is_past
from tools.retrieval.collect.grants.pipeline import CollectConfig, Pipeline
from tools.retrieval.collect.grants.record import Opportunity
from tools.retrieval.collect.grants.store import Store

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    def line(self) -> str:
        mark = {PASS: "[x]", FAIL: "[!]", SKIP: "[-]"}[self.status]
        return f"{mark} {self.name}" + (f" — {self.detail}" if self.detail else "")


def run_checklist(
    config: CollectConfig,
    *,
    today: date | None = None,
    expected_counts: dict[str, int] | None = None,
    check_idempotency: bool = True,
) -> list[Check]:
    today = today or date.today()
    pipeline = Pipeline(config)
    checks: list[Check] = []

    with Store(config.db_path) as store:
        records = store.all_records()
        by_source = store.count_by_source()
        last = store.last_run()
        outages = (
            {row["source"]: row["message"] for row in store.errors_for(last["run_id"])}
            if last
            else {}
        )

    checks.append(_every_adapter_returned_records(pipeline, by_source, outages))
    checks.append(_no_past_close_dates(records, today))
    checks.append(_rolling_survives(records))
    checks.append(_cross_source_record_merged(records))
    checks.append(_spot_check_sample(records))
    checks.append(_count_within_margin(records, expected_counts))
    checks.append(_parents_produced_children(records))
    checks.append(_overlays_resolved_or_flagged(records))

    if check_idempotency:
        checks.append(_idempotent(pipeline, today))
    else:
        checks.append(Check("Idempotency: second run inserts 0, updates 0", SKIP, "not requested"))

    checks.append(_offline_parse(pipeline))
    return checks


# --- individual checks ---------------------------------------------------


def _every_adapter_returned_records(
    pipeline: Pipeline, by_source: dict[str, int], outages: dict[str, str] | None = None
) -> Check:
    outages = outages or {}
    enabled = []
    for name in pipeline.selected_sources():
        available, _ = pipeline.registry[name].available()
        if available:
            enabled.append(name)

    empty = [name for name in enabled if by_source.get(name, 0) == 0]
    if not enabled:
        return Check("Every enabled adapter returns > 0 records", SKIP, "no adapters enabled")
    if empty:
        # Name the recorded reason. "Zero records" and "the host refused us" are
        # very different findings and must not read the same.
        detail = ", ".join(f"{name} ({outages.get(name, 'no error recorded')})" for name in empty)
        return Check("Every enabled adapter returns > 0 records", FAIL, f"zero from: {detail}")
    counts = ", ".join(f"{name}={by_source.get(name, 0)}" for name in enabled)
    return Check("Every enabled adapter returns > 0 records", PASS, counts)


def _no_past_close_dates(records: list[Opportunity], today: date) -> Check:
    stale = [
        record
        for record in records
        if record.record_kind != "overlay"
        and record.close_date
        and is_past(record.close_date, today)
        and not any(not is_past(d, today) for d in record.additional_due_dates)
    ]
    if stale:
        return Check(
            "No stored record has a past close date after prune",
            FAIL,
            f"{len(stale)} stale, e.g. {stale[0].opportunity_number or stale[0].source_record_id}",
        )
    return Check("No stored record has a past close date after prune", PASS, f"{len(records)} checked")


def _rolling_survives(records: list[Opportunity]) -> Check:
    rolling = [
        record
        for record in records
        if record.record_kind != "overlay" and not record.close_date and not record.additional_due_dates
    ]
    if not rolling:
        # Not a failure — it means no rolling opportunity happened to be in this
        # corpus. Saying PASS here would claim we verified something we did not.
        return Check("Rolling opportunities (null close date) survive prune", SKIP, "none in corpus")
    return Check(
        "Rolling opportunities (null close date) survive prune", PASS, f"{len(rolling)} survived"
    )


def _cross_source_record_merged(records: list[Opportunity]) -> Check:
    multi = [record for record in records if len(set(record.contributing_sources)) > 1]
    if not multi:
        return Check(
            "A two-source record appears once with both sources listed",
            SKIP,
            "no cross-source overlap in this corpus (single source enabled?)",
        )
    example = multi[0]
    return Check(
        "A two-source record appears once with both sources listed",
        PASS,
        f"{len(multi)} merged, e.g. {example.opportunity_number} "
        f"<- {'+'.join(sorted(set(example.contributing_sources)))}",
    )


def _spot_check_sample(records: list[Opportunity]) -> Check:
    """Emit ten records with their live URLs for manual verification.

    This one cannot be automated honestly — "matches the live page" needs eyes.
    What it can do is guarantee the ten records it hands over are *checkable*:
    each has a title, a funder, and a resolvable source URL.
    """
    sample = records[:10]
    if len(sample) < 10:
        return Check("Ten records spot-checkable against live source pages", SKIP, f"only {len(sample)} stored")
    broken = [r for r in sample if not (r.title and r.funder and r.source_url.startswith("http"))]
    if broken:
        return Check(
            "Ten records spot-checkable against live source pages",
            FAIL,
            f"{len(broken)} of 10 lack title/funder/URL",
        )
    return Check(
        "Ten records spot-checkable against live source pages",
        PASS,
        "run `collect spot-check` to print them",
    )


def _count_within_margin(records: list[Opportunity], expected: dict[str, int] | None) -> Check:
    """Compare stored counts against what the source's own web interface shows.

    Counts **contributions**, not the ``source`` column. After a cross-source
    merge the surviving row is attributed to whichever side won, so counting the
    column would undercount every source that lost a merge and report a phantom
    shortfall. A genuine shortfall is still expected and allowed for: records
    whose deadline has already passed are dropped before they are stored.
    """
    if not expected:
        return Check(
            "Total open count within margin of the source's own web interface",
            SKIP,
            "no expected counts supplied (pass --expect source=N)",
        )

    contributed: dict[str, int] = {}
    for record in records:
        for source in set(record.contributing_sources):
            contributed[source] = contributed.get(source, 0) + 1

    problems = []
    for source, want in expected.items():
        got = contributed.get(source, 0)
        if want and abs(got - want) / want > 0.25:
            problems.append(f"{source}: stored {got} vs expected {want}")
    if problems:
        return Check(
            "Total open count within margin of the source's own web interface",
            FAIL,
            "; ".join(problems)
            + " — check whether the source's status flags are stale before assuming a bug",
        )
    return Check(
        "Total open count within margin of the source's own web interface",
        PASS,
        ", ".join(f"{k}={contributed.get(k, 0)} vs {v} live" for k, v in expected.items()),
    )


def _parents_produced_children(records: list[Opportunity]) -> Check:
    """Catch the failure this check exists for: storing an umbrella and dropping its topics.

    A standalone record only counts as a parent-plus-topic solicitation if its own
    raw payload declares nested topics. Judging by source instead would flag every
    ordinary standalone record from a source that *also* happens to emit topics —
    the EU portal publishes both bare calls and call-plus-topic pairs, so that
    reading produces dozens of false failures and says nothing about flattening.
    """
    topics = [record for record in records if record.record_kind == "topic"]
    umbrellas = [
        record
        for record in records
        if record.record_kind == "standalone" and _declares_topics(record.raw)
    ]
    if not umbrellas:
        return Check(
            "Every parent-plus-topic solicitation produced more than one record",
            SKIP,
            "no solicitation in the corpus declares nested topics",
        )

    parents = {record.parent_opportunity_number for record in topics}
    childless = [record for record in umbrellas if record.opportunity_number not in parents]
    if childless:
        return Check(
            "Every parent-plus-topic solicitation produced more than one record",
            FAIL,
            f"{len(childless)} of {len(umbrellas)} declared topics but produced no topic records, "
            f"e.g. {childless[0].opportunity_number}",
        )
    return Check(
        "Every parent-plus-topic solicitation produced more than one record",
        PASS,
        f"{len(umbrellas)} solicitations produced {len(topics)} topic records",
    )


def _declares_topics(raw: dict) -> bool:
    """True when a raw payload carries a non-empty nested topic list."""
    for key, value in (raw or {}).items():
        if "topic" in key.lower() and isinstance(value, list) and value:
            return True
    return False


def _overlays_resolved_or_flagged(records: list[Opportunity]) -> Check:
    overlays = [record for record in records if record.record_kind == "overlay"]
    if not overlays:
        return Check("Every overlay has a resolvable parent or is flagged", SKIP, "no overlays")
    silent = [
        record
        for record in overlays
        if not record.parent_opportunity_number and not record.unresolved_parent
    ]
    if silent:
        return Check(
            "Every overlay has a resolvable parent or is flagged",
            FAIL,
            f"{len(silent)} overlays have neither a parent nor an unresolved flag",
        )
    flagged = sum(1 for record in overlays if record.unresolved_parent)
    return Check(
        "Every overlay has a resolvable parent or is flagged",
        PASS,
        f"{len(overlays)} overlays, {flagged} explicitly flagged unresolved",
    )


def _idempotent(pipeline: Pipeline, today: date) -> Check:
    """Re-run stages 2-5 over the same raw payloads and require no writes."""
    try:
        records, _, _ = pipeline.parse(None)
    except FileNotFoundError as exc:
        return Check("Idempotency: second run inserts 0, updates 0", SKIP, str(exc))

    records = pipeline.normalize(records, today)
    records, _, _ = pipeline.deduplicate(records)
    # Every stage the real run applies, in the same order. Leaving one out makes
    # the check fail on a corpus that is in fact idempotent — which is worse than
    # not checking, because it reports a defect that is not there.
    pipeline.apply_enrichment(records)
    stats, _, _ = pipeline.persist(records, today=today)

    if stats.inserted or stats.updated:
        return Check(
            "Idempotency: second run inserts 0, updates 0",
            FAIL,
            f"inserted={stats.inserted} updated={stats.updated}",
        )
    return Check(
        "Idempotency: second run inserts 0, updates 0", PASS, f"{stats.unchanged} unchanged"
    )


def _offline_parse(pipeline: Pipeline) -> Check:
    """Prove stage 2 needs no network by running it with the network forbidden."""
    run_id = pipeline.raw_store.latest_run_id()
    if run_id is None:
        return Check("Raw payloads on disk; parse re-runnable offline", FAIL, "no raw payloads")

    offline = Pipeline(
        CollectConfig(
            root=pipeline.config.root,
            sources=list(pipeline.config.sources),
            offline=True,
            keep_runs=pipeline.config.keep_runs,
        )
    )
    try:
        records, counts, errors = offline.parse(run_id)
    except Exception as exc:  # noqa: BLE001 - any failure here is the finding
        return Check("Raw payloads on disk; parse re-runnable offline", FAIL, str(exc))
    if errors:
        return Check("Raw payloads on disk; parse re-runnable offline", FAIL, str(errors[0]))
    if not records:
        return Check("Raw payloads on disk; parse re-runnable offline", FAIL, "parsed 0 records")
    return Check(
        "Raw payloads on disk; parse re-runnable offline",
        PASS,
        f"run {run_id}: {sum(counts.values())} records, no network",
    )


def format_report(checks: list[Check], dedupe: DedupeReport | None = None) -> str:
    lines = ["Smoke checklist (briefing section 9)", ""]
    lines.extend(check.line() for check in checks)
    failures = sum(1 for check in checks if check.status == FAIL)
    skipped = sum(1 for check in checks if check.status == SKIP)
    lines.append("")
    lines.append(f"{len(checks) - failures - skipped} passed, {failures} failed, {skipped} skipped")
    if dedupe and dedupe.review_pairs:
        lines.append("")
        lines.append(f"{len(dedupe.review_pairs)} fuzzy pairs flagged for review (not merged):")
        for left, right, score in dedupe.review_pairs[:10]:
            lines.append(f"  {score}  {left}  <>  {right}")
    return "\n".join(lines)
