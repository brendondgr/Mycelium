"""Regenerate `docs/research/INDEX.md` from every experiment manifest.

Hand-maintained indexes go stale within three weeks, so this one is generated
and CI fails when the checked-in copy differs from what this script emits.

    uv run --project scripts/research scripts/research/generate_index.py
    uv run --project scripts/research scripts/research/generate_index.py --check
"""

from __future__ import annotations

import argparse
import sys

from record import RESEARCH, iter_experiments, primary_metric

HEADER = """<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: make research-index -->

# Experiment Index

Every experiment in the record, newest ID last. Status is the manifest's own
`status` field; a `failed` or `superseded` row stays here permanently, because a
deleted dead end is a dead end you walk into twice.

| ID | Date | Title | Status | Primary metric | Claims | Link |
|---|---|---|---|---|---|---|
"""

FOOTER = """
## Status counts

| Status | Count |
|---|---:|
"""


def render() -> str:
    experiments = iter_experiments()
    rows = []
    counts: dict[str, int] = {}
    for exp in experiments:
        m = exp.manifest
        claims = m.get("supports_claims") or []
        refutes = m.get("refutes_claims") or []
        claim_cell = ", ".join(claims) if claims else "—"
        if refutes:
            claim_cell += " (refutes " + ", ".join(refutes) + ")"
        counts[exp.status] = counts.get(exp.status, 0) + 1
        rows.append(
            "| `{id}` | {date} | {title} | {status} | {metric} | {claims} |"
            " [folder](experiments/{dirname}/RESULTS.md) |".format(
                id=exp.id,
                date=m.get("date_completed") or m.get("date_started") or "—",
                title=m.get("title", exp.dir_name),
                status=exp.status,
                metric=primary_metric(m),
                claims=claim_cell,
                dirname=exp.dir_name,
            )
        )

    empty = "| — | — | _no experiments yet_ | — | — | — | — |"
    body = HEADER + ("\n".join(rows) if rows else empty)
    body += "\n" + FOOTER
    for status in sorted(counts):
        body += f"| {status} | {counts[status]} |\n"
    body += f"| **total** | **{len(experiments)}** |\n"
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the checked-in INDEX.md is stale. Used by CI.",
    )
    args = parser.parse_args()

    target = RESEARCH / "INDEX.md"
    rendered = render()
    current = target.read_text(encoding="utf-8") if target.is_file() else ""

    if args.check:
        if current != rendered:
            print(
                "INDEX.md is stale. Run `make research-index` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("INDEX.md is current.")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"Wrote {target.relative_to(RESEARCH.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
