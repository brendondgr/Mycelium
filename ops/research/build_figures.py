"""Regenerate every figure in the record, then check nothing drifted.

    make figures          # regenerate
    make figures-check    # regenerate and fail if git sees a diff

Walks `docs/research/experiments/*/figures/make_figures.py` and runs each one,
then re-copies promoted figures into `docs/research/figures/`. A promoted figure
is one named in `docs/research/figures/PROMOTED.md`; promotion copies the figure
and its generator, so the paper's figures are always rebuildable from the record.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys

from record import EXPERIMENTS, REPO_ROOT, RESEARCH

PROMOTED = RESEARCH / "figures" / "PROMOTED.md"
PROMOTION_RE = re.compile(
    r"^\|\s*`?(fig-[a-z0-9-]+)`?\s*\|\s*`?(EXP-\d{4}-\d{2}-\d{3})`?\s*\|", re.M
)


def run_generators() -> list[str]:
    """Run every experiment's make_figures.py. Returns the failures."""
    failures = []
    for generator in sorted(EXPERIMENTS.glob("*/figures/make_figures.py")):
        rel = generator.relative_to(REPO_ROOT).as_posix()
        print(f"→ {rel}")
        result = subprocess.run(
            [sys.executable, generator.name],
            cwd=generator.parent,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            print("  " + result.stdout.strip().replace("\n", "\n  "))
        if result.returncode != 0:
            print("  " + result.stderr.strip().replace("\n", "\n  "), file=sys.stderr)
            failures.append(rel)
    return failures


def promote() -> list[str]:
    """Copy promoted figures and their generators into docs/research/figures/."""
    if not PROMOTED.is_file():
        return []
    copied = []
    for slug, exp_id in PROMOTION_RE.findall(PROMOTED.read_text(encoding="utf-8")):
        source_dirs = [d for d in EXPERIMENTS.glob(f"{exp_id}-*/figures") if d.is_dir()]
        if not source_dirs:
            print(f"  promotion: no folder for {exp_id}", file=sys.stderr)
            continue
        source = source_dirs[0]
        for suffix in (".svg", ".pdf"):
            src = source / f"{slug}{suffix}"
            if src.is_file():
                shutil.copy2(src, RESEARCH / "figures" / src.name)
                copied.append(src.name)
        generator = source / "make_figures.py"
        if generator.is_file():
            destination = RESEARCH / "figures" / "sources" / f"{exp_id}-make_figures.py"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generator, destination)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if regeneration changes any tracked file. Used by CI.",
    )
    args = parser.parse_args()

    failures = run_generators()
    if failures:
        print(f"\n{len(failures)} generator(s) failed.", file=sys.stderr)
        return 1

    copied = promote()
    if copied:
        print(f"Promoted {len(copied)} file(s) into docs/research/figures/")

    if args.check:
        diff = subprocess.run(
            ["git", "status", "--porcelain", "--", "docs/research"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if diff:
            print(
                "Figures are stale — regeneration changed these files:\n" + diff,
                file=sys.stderr,
            )
            return 1
        print("Figures are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
