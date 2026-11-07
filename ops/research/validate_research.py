"""Validate the research record. Convention without enforcement decays.

    uv run --project scripts/research scripts/research/validate_research.py
    uv run --project scripts/research scripts/research/validate_research.py <dir>...

Fails on, in the order checked:

  1. a required file missing (`manifest.yaml`, `PROTOCOL.md`, `RESULTS.md`)
  2. a manifest that fails schema validation
  3. `status: complete` with empty `metrics.values`
  4. a figure listed in the manifest with no file, or a figure file not listed
  5. a figure without a generating script in the same folder
  6. a `data/` artifact pointer with no hash
  7. a `supports_claims` / `refutes_claims` ID absent from `CLAIMS.md`
  8. a stale `INDEX.md`

Every message names the file and says what to do about it. A validator that
prints "invalid" and stops is a validator people route around.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from record import (
    DIR_RE,
    HASH_RE,
    NOT_HASHED_RE,
    REPO_ROOT,
    REQUIRED_FILES,
    RESEARCH,
    SCHEMA_PATH,
    Experiment,
    iter_experiments,
    load_manifest,
)

CLAIM_ID_RE = re.compile(r"\bC-\d{3}\b")
FIGURE_FORMATS = (".svg", ".pdf")
GENERATOR_NAMES = ("make_figures.py", "make_figures.sh")
MAX_FILE_BYTES = 10 * 1024 * 1024


class Report:
    """Collected problems, printed once at the end."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def known_claim_ids() -> set[str]:
    path = RESEARCH / "CLAIMS.md"
    if not path.is_file():
        return set()
    return set(CLAIM_ID_RE.findall(path.read_text(encoding="utf-8")))


def check_required_files(exp: Experiment, report: Report) -> bool:
    """Check 1. Returns False when the folder is too broken to check further."""
    ok = True
    for name in REQUIRED_FILES:
        target = exp.path / name
        if not target.is_file():
            report.error(exp.rel(), f"missing required file `{name}`")
            ok = False
        elif target.stat().st_size == 0:
            report.error(exp.rel(), f"`{name}` is empty")
            ok = False
    return ok


def check_schema(
    exp: Experiment, validator: Draft202012Validator, report: Report
) -> None:
    """Check 2."""
    if not exp.manifest:
        report.error(exp.rel(), "manifest.yaml is empty or is not a mapping")
        return
    errors = sorted(validator.iter_errors(exp.manifest), key=lambda e: list(e.path))
    for error in errors:
        location = "/".join(str(p) for p in error.path) or "(root)"
        report.error(exp.rel(), f"manifest.yaml `{location}`: {error.message}")

    declared = exp.manifest.get("id")
    match = DIR_RE.match(exp.dir_name)
    if not match:
        report.error(
            exp.rel(),
            "directory name must be EXP-<YYYY>-<MM>-<NNN>-<kebab-slug>",
        )
    elif declared:
        expected = f"EXP-{match.group(1)}-{match.group(2)}-{match.group(3)}"
        if declared != expected:
            report.error(
                exp.rel(),
                f"manifest id `{declared}` does not match directory `{expected}`",
            )
        if exp.manifest.get("slug") != match.group(4):
            report.error(
                exp.rel(),
                f"manifest slug does not match directory slug `{match.group(4)}`",
            )


def check_metrics(exp: Experiment, report: Report) -> None:
    """Check 3."""
    status = exp.status
    values = ((exp.manifest.get("metrics") or {}).get("values")) or {}
    if status == "complete" and not values:
        report.error(
            exp.rel(),
            "status is `complete` but metrics.values is empty — either record the"
            " numbers or set status to running/failed",
        )
    if status == "failed" and not (exp.path / "ISSUES.md").is_file():
        report.error(
            exp.rel(),
            "status is `failed` but there is no ISSUES.md saying what broke",
        )


def check_figures(exp: Experiment, report: Report) -> None:
    """Checks 4 and 5."""
    listed = set(exp.manifest.get("figures") or [])
    figures_dir = exp.path / "figures"

    on_disk: set[str] = set()
    if figures_dir.is_dir():
        for entry in figures_dir.iterdir():
            if entry.suffix in FIGURE_FORMATS or entry.suffix == ".png":
                on_disk.add(entry.stem)

    for slug in sorted(listed - on_disk):
        report.error(
            exp.rel(),
            f"manifest lists figure `{slug}` but figures/ has no such file",
        )
    for slug in sorted(on_disk - listed):
        report.error(
            exp.rel(),
            f"figures/{slug}.* exists but is not in the manifest `figures:` list",
        )

    for slug in sorted(listed & on_disk):
        for suffix in FIGURE_FORMATS:
            if not (figures_dir / f"{slug}{suffix}").is_file():
                report.error(
                    exp.rel(),
                    f"figure `{slug}` has no {suffix} — emit both vector formats",
                )

    if (listed or on_disk) and not any(
        (figures_dir / name).is_file() for name in GENERATOR_NAMES
    ):
        report.error(
            exp.rel(),
            "figures/ has figures but no make_figures.py — a figure nobody can"
            " regenerate is a figure that rots",
        )


def check_pointers(exp: Experiment, report: Report) -> None:
    """Check 6."""
    pointers = exp.path / "data" / "POINTERS.md"
    if not pointers.is_file():
        return
    for lineno, line in enumerate(pointers.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|-: "):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and cells[0].lower() in {"artifact", "path", "pointer"}:
            continue
        if HASH_RE.search(stripped):
            continue
        if NOT_HASHED_RE.search(stripped):
            report.warn(
                exp.rel(),
                f"data/POINTERS.md:{lineno} declares `not-hashed:` — acceptable"
                " only for a regenerable artifact, and only in a back-filled"
                " experiment",
            )
            continue
        report.error(
            exp.rel(),
            f"data/POINTERS.md:{lineno} has a pointer with no hash — a pointer"
            " without a hash points at whatever is there today. Use"
            " `not-hashed: <reason>` if none was taken.",
        )


def check_claims(exp: Experiment, claims: set[str], report: Report) -> None:
    """Check 7."""
    referenced = list(exp.manifest.get("supports_claims") or []) + list(
        exp.manifest.get("refutes_claims") or []
    )
    for claim in referenced:
        if claim not in claims:
            report.error(
                exp.rel(),
                f"references claim `{claim}`, which is not in docs/research/CLAIMS.md",
            )


def check_size(exp: Experiment, report: Report) -> None:
    """Not one of the eight, but the rule that keeps the record cloneable."""
    for entry in exp.path.rglob("*"):
        if entry.is_file() and entry.stat().st_size > MAX_FILE_BYTES:
            report.error(
                entry.relative_to(REPO_ROOT).as_posix(),
                "larger than 10 MB — large artifacts live outside docs/research/,"
                " referenced by data/POINTERS.md",
            )


def check_index(report: Report) -> None:
    """Check 8."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from generate_index import render

    target = RESEARCH / "INDEX.md"
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    if current != render():
        report.error(
            "docs/research/INDEX.md",
            "stale — run `make research-index` and commit the result",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Experiment directories to check. Default: every experiment.",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip the INDEX.md staleness check (used while regenerating it).",
    )
    args = parser.parse_args()

    if not RESEARCH.is_dir():
        print("docs/research/ does not exist.", file=sys.stderr)
        return 1

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    claims = known_claim_ids()
    report = Report()

    if args.paths:
        experiments = []
        for raw in args.paths:
            path = Path(raw).resolve()
            if not path.is_dir():
                report.error(raw, "not a directory")
                continue
            experiments.append(Experiment(path, load_manifest(path / "manifest.yaml")))
    else:
        experiments = iter_experiments()

    if not experiments and not args.paths:
        print("No experiments to validate yet.")

    for exp in experiments:
        if not check_required_files(exp, report):
            continue
        check_schema(exp, validator, report)
        check_metrics(exp, report)
        check_figures(exp, report)
        check_pointers(exp, report)
        check_claims(exp, claims, report)
        check_size(exp, report)

    if not args.paths and not args.skip_index:
        check_index(report)

    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)

    if report.errors:
        print(
            f"\n{len(report.errors)} problem(s) across "
            f"{len(experiments)} experiment(s).",
            file=sys.stderr,
        )
        return 1

    print(f"Research record valid: {len(experiments)} experiment(s) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
