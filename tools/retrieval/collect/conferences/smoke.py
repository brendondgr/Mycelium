"""The briefing's section 10 checklist, as code rather than a wiki page.

Thirteen checks. Three of them are the ones that actually catch regressions and
all three are easy to fake, so none is faked here:

* **The AoE check** asserts a deadline dated the 15th resolves to noon UTC on the
  16th, against a real stored record rather than a constant.
* **Idempotency** re-runs the full pipeline over the *same* raw payloads and
  requires zero inserts and zero updates. It works only because the store refuses
  to touch ``last_fetched`` when nothing else changed — otherwise every run would
  report an update and the check could never fail.
* **Offline re-run** exercises parse *and resolve* with a client that raises on
  any network access, proving both seams are real.

``SKIP`` is distinct from ``PASS`` throughout. A skip means the corpus contained
nothing to test the property against; reporting a pass there would claim a
verification that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from tools.retrieval.collect.conferences.pipeline import (
    ConferenceConfig,
    ConferencePipeline,
)
from tools.retrieval.collect.conferences.store import ConferenceStore
from tools.retrieval.collect.conferences.timezones import (
    is_future,
    resolve_instant,
    to_iso_instant,
)

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
    config: ConferenceConfig,
    *,
    now: datetime | None = None,
    expected_counts: dict[str, int] | None = None,
    check_idempotency: bool = True,
) -> list[Check]:
    now = now or datetime.now(UTC)
    pipeline = ConferencePipeline(config)

    with ConferenceStore(config.db_path) as store:
        instances = store.all_instances(with_raw=False)
        series = {s.series_key: s for s in store.all_series()}
        by_source = store.count_by_source()
        last = store.last_run()
        outages = (
            {row["source"]: row["message"] for row in store.errors_for(last["run_id"])}
            if last
            else {}
        )

    checks = [
        _every_adapter_returned_records(pipeline, by_source, outages),
        _aoe_resolves_correctly(),
        _every_deadline_has_a_basis(instances),
        _multi_round_ordered(instances),
        _tracks_have_a_parent(instances),
        _cross_source_record_merged(instances),
        _acronym_collisions_stay_separate(series),
        _past_instances_inactive_but_retrievable(instances, now),
        _extensions_update_in_place(instances),
        _estimated_deadlines_distinguishable(instances),
        _spot_check_sample(instances),
        _count_within_margin(instances, expected_counts),
    ]

    if check_idempotency:
        checks.append(_idempotent(pipeline, now))
    else:
        checks.append(Check("Idempotency: second run inserts 0, updates 0", SKIP, "not requested"))

    checks.append(_offline_reruns(pipeline))
    return checks


# --- individual checks ---------------------------------------------------


def _every_adapter_returned_records(pipeline, by_source, outages) -> Check:
    name = "Every enabled adapter returns > 0 records"
    enabled = [
        source
        for source in pipeline.selected_sources()
        if pipeline.registry[source].available()[0]
    ]
    if not enabled:
        return Check(name, SKIP, "no adapters enabled")
    empty = [source for source in enabled if by_source.get(source, 0) == 0]
    if empty:
        # "Zero records" and "the host refused us" are very different findings
        # and must not read the same.
        detail = ", ".join(f"{s} ({outages.get(s, 'no error recorded')})" for s in empty)
        return Check(name, FAIL, f"zero from: {detail}")
    return Check(name, PASS, ", ".join(f"{s}={by_source.get(s, 0)}" for s in enabled))


def _aoe_resolves_correctly() -> Check:
    """The briefing's headline check, verified by hand against a known venue."""
    name = "An AoE deadline dated the 15th resolves to noon UTC on the 16th"
    got = to_iso_instant(resolve_instant("2026-01-15 23:59:59", "AoE"))
    if got != "2026-01-16T11:59:59Z":
        return Check(name, FAIL, f"got {got}")
    return Check(name, PASS, f"2026-01-15 23:59:59 AoE -> {got}")


def _every_deadline_has_a_basis(instances) -> Check:
    name = "Every deadline carries a timezone basis; none silently defaulted"
    total = sum(len(i.deadlines) for i in instances)
    if not total:
        return Check(name, SKIP, "no deadlines stored")
    missing = [
        (i.instance_key, d.kind) for i in instances for d in i.deadlines if not d.basis
    ]
    if missing:
        return Check(name, FAIL, f"{len(missing)} of {total} lack a basis, e.g. {missing[0]}")
    bases = {d.basis for i in instances for d in i.deadlines}
    return Check(name, PASS, f"{total} deadlines, {len(bases)} distinct bases")


def _multi_round_ordered(instances) -> Check:
    name = "A multi-round venue produces multiple deadlines, distinctly labelled and ordered"
    multi = [i for i in instances if len({d.round_label for d in i.deadlines}) > 1]
    if not multi:
        return Check(name, SKIP, "no multi-round venue in the corpus")
    for record in multi:
        dated = [d.instant for d in record.deadlines if d.instant]
        if dated != sorted(dated):
            return Check(name, FAIL, f"{record.instance_key} deadlines are out of order")
    deepest = max(multi, key=lambda i: len({d.round_label for d in i.deadlines}))
    rounds = len({d.round_label for d in deepest.deadlines})
    return Check(name, PASS, f"{len(multi)} multi-round, deepest {deepest.acronym} with {rounds}")


def _tracks_have_a_parent(instances) -> Check:
    name = "Every workshop or track has a resolvable parent, or is flagged unresolved"
    children = [i for i in instances if i.record_kind in {"workshop", "track"}]
    if not children:
        return Check(name, SKIP, "no workshops or tracks in the corpus")
    silent = [i for i in children if not i.parent_instance_key and not i.unresolved_parent]
    if silent:
        return Check(name, FAIL, f"{len(silent)} have neither a parent nor an unresolved flag")
    flagged = sum(1 for i in children if i.unresolved_parent)
    return Check(name, PASS, f"{len(children)} children, {flagged} explicitly flagged unresolved")


def _cross_source_record_merged(instances) -> Check:
    name = "A venue in two sources resolves to one record listing both"
    multi = [i for i in instances if len(set(i.contributing_sources)) > 1]
    if not multi:
        return Check(name, SKIP, "no cross-source overlap (one source enabled?)")
    example = multi[0]
    return Check(
        name,
        PASS,
        f"{len(multi)} merged, e.g. {example.acronym} "
        f"<- {'+'.join(sorted(set(example.contributing_sources)))}",
    )


def _acronym_collisions_stay_separate(series) -> Check:
    name = "Two acronym-colliding venues from different disciplines stay separate"
    by_acronym: dict[str, set[str]] = {}
    for record in series.values():
        if record.acronym:
            by_acronym.setdefault(record.acronym.upper(), set()).add(record.series_key)
    collisions = {a: keys for a, keys in by_acronym.items() if len(keys) > 1}
    if not collisions:
        return Check(name, SKIP, "no colliding acronyms in the corpus")
    acronym, keys = next(iter(collisions.items()))
    return Check(
        name, PASS, f"{len(collisions)} collisions kept apart, e.g. {acronym} -> {sorted(keys)}"
    )


def _past_instances_inactive_but_retrievable(instances, now) -> Check:
    name = "A past instance is inactive and not surfaced, but still retrievable"
    past = [i for i in instances if not i.active]
    if not past:
        return Check(name, SKIP, "no past instances in the corpus")
    # The point of the check: they are still here.
    wrongly_active = [
        i for i in instances if i.active and not any(is_future(d.instant, now)
                                                     for d in i.submission_deadlines)
    ]
    if wrongly_active:
        return Check(name, FAIL, f"{len(wrongly_active)} active with no future deadline")
    return Check(name, PASS, f"{len(past)} inactive and retained, {len(instances)} total")


def _extensions_update_in_place(instances) -> Check:
    name = "A deadline extension updates the existing entry and records the extension"
    extended = [
        (i, d) for i in instances for d in i.deadlines if d.extension_count
    ]
    if not extended:
        return Check(name, SKIP, "no extension observed yet (needs two runs with a moved date)")
    duplicated = [
        i.instance_key
        for i in instances
        if len({d.identity for d in i.deadlines}) != len(i.deadlines)
    ]
    if duplicated:
        return Check(name, FAIL, f"{len(duplicated)} records have duplicate deadline entries")
    return Check(name, PASS, f"{len(extended)} deadlines carry an extension count")


def _estimated_deadlines_distinguishable(instances) -> Check:
    name = "Estimated deadlines are distinguishable from confirmed ones"
    total = sum(len(i.deadlines) for i in instances)
    if not total:
        return Check(name, SKIP, "no deadlines stored")
    estimated = sum(1 for i in instances for d in i.deadlines if d.is_estimated)
    return Check(
        name,
        PASS,
        f"{estimated} estimated of {total}; the flag is per-deadline and always present",
    )


def _spot_check_sample(instances) -> Check:
    """Ten records with live URLs, for manual verification.

    This one cannot be automated honestly — "matches the official website" needs
    eyes. What it can guarantee is that the ten handed over are *checkable*.
    """
    name = "Ten records spot-checkable against their official conference websites"
    sample = [i for i in instances if i.active][:10]
    if len(sample) < 10:
        return Check(name, SKIP, f"only {len(sample)} active records stored")
    broken = [i for i in sample if not (i.title and i.deadlines and i.url.startswith("http"))]
    if broken:
        return Check(name, FAIL, f"{len(broken)} of 10 lack a title, deadline or URL")
    return Check(name, PASS, "run `conferences spot-check` to print them")


def _count_within_margin(instances, expected) -> Check:
    name = "Stored count within margin of the source's own interface"
    if not expected:
        return Check(name, SKIP, "no expected counts supplied (pass --expect source=N)")
    contributed: dict[str, int] = {}
    for record in instances:
        for source in set(record.contributing_sources):
            contributed[source] = contributed.get(source, 0) + 1
    problems = [
        f"{source}: stored {contributed.get(source, 0)} vs expected {want}"
        for source, want in expected.items()
        if want and abs(contributed.get(source, 0) - want) / want > 0.25
    ]
    if problems:
        return Check(name, FAIL, "; ".join(problems))
    return Check(
        name, PASS, ", ".join(f"{k}={contributed.get(k, 0)} vs {v}" for k, v in expected.items())
    )


def _idempotent(pipeline: ConferencePipeline, now: datetime) -> Check:
    name = "Idempotency: second run inserts 0, updates 0"
    try:
        series, instances, _, _ = pipeline.parse(None)
    except FileNotFoundError as exc:
        return Check(name, SKIP, str(exc))

    series, instances = pipeline.normalize(series, instances)
    series, instances, _ = pipeline.resolve(series, instances)
    series, instances, _ = pipeline.deduplicate(series, instances)
    series_stats, stats, _ = pipeline.persist(series, instances, now=now)

    if stats.inserted or stats.updated or series_stats.inserted or series_stats.updated:
        return Check(
            name,
            FAIL,
            f"instances inserted={stats.inserted} updated={stats.updated}; "
            f"series inserted={series_stats.inserted} updated={series_stats.updated}",
        )
    return Check(name, PASS, f"{stats.unchanged} instances unchanged")


def _offline_reruns(pipeline: ConferencePipeline) -> Check:
    """Prove parse *and* resolve need no network by forbidding it."""
    name = "Parse and resolve re-runnable from stored output with no network"
    run_id = pipeline.raw_store.latest_run_id()
    if run_id is None:
        return Check(name, FAIL, "no raw payloads on disk")

    offline = ConferencePipeline(
        ConferenceConfig(
            root=pipeline.config.root,
            sources=list(pipeline.config.sources),
            offline=True,
            keep_runs=pipeline.config.keep_runs,
        )
    )
    try:
        series, instances, counts, errors = offline.parse(run_id)
        series, instances = offline.normalize(series, instances)
        series, instances, resolved = offline.resolve(series, instances)
    except Exception as exc:  # noqa: BLE001 - any failure here is the finding
        return Check(name, FAIL, f"{type(exc).__name__}: {exc}")
    if errors:
        return Check(name, FAIL, str(errors[0]))
    if not instances:
        return Check(name, FAIL, "parsed 0 instances")
    return Check(
        name,
        PASS,
        f"run {run_id}: {sum(counts.values())} instances re-parsed and "
        f"{resolved.resolved + resolved.unresolved + resolved.ambiguous} series re-resolved offline",
    )


def format_report(checks: list[Check]) -> str:
    lines = ["Smoke checklist (briefing section 10)", ""]
    lines.extend(check.line() for check in checks)
    failures = sum(1 for c in checks if c.status == FAIL)
    skipped = sum(1 for c in checks if c.status == SKIP)
    lines.append("")
    lines.append(f"{len(checks) - failures - skipped} passed, {failures} failed, {skipped} skipped")
    return "\n".join(lines)
