"""Scaffold a new experiment folder from `docs/research/templates/experiment/`.

    make new-experiment SLUG=cluster-scoping-ablation

Allocates the next ID for the current month, copies the template, and pre-fills
the date, git commit, branch, and dirty-tree status so the reproducibility block
starts out true rather than starting out as placeholder text somebody forgets.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date

from record import DIR_RE, EXPERIMENTS, TEMPLATES, git_state

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def next_id(today: date) -> tuple[str, int]:
    """The next free `EXP-YYYY-MM-NNN` for this month.

    Numbering restarts each month, and gaps are never reused: the sequence is a
    handle, not a count.
    """
    prefix = f"EXP-{today.year:04d}-{today.month:02d}"
    used = []
    if EXPERIMENTS.is_dir():
        for entry in EXPERIMENTS.iterdir():
            match = DIR_RE.match(entry.name)
            if match and f"EXP-{match.group(1)}-{match.group(2)}" == prefix:
                used.append(int(match.group(3)))
    number = max(used, default=0) + 1
    return f"{prefix}-{number:03d}", number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="kebab-case slug, e.g. cluster-scoping-ablation")
    parser.add_argument("--title", default="", help="Human title for the manifest.")
    parser.add_argument("--author", default="", help="Author name for the manifest.")
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    if not SLUG_RE.match(slug):
        print(f"Slug must be kebab-case: got `{args.slug}`", file=sys.stderr)
        return 1

    template = TEMPLATES / "experiment"
    if not template.is_dir():
        print(f"Template missing: {template}", file=sys.stderr)
        return 1

    today = date.today()
    exp_id, _ = next_id(today)
    target = EXPERIMENTS / f"{exp_id}-{slug}"
    if target.exists():
        print(f"Already exists: {target}", file=sys.stderr)
        return 1

    shutil.copytree(template, target)

    sha, branch, dirty = git_state()
    manifest_path = target / "manifest.yaml"
    text = manifest_path.read_text(encoding="utf-8")
    replacements = {
        "EXP-YYYY-MM-NNN": exp_id,
        "<slug>": slug,
        "<title — one line, states the question>": (
            args.title or f"TODO: title for {slug}"
        ),
        "<YYYY-MM-DD>": today.isoformat(),
        "<commit-sha>": sha,
        "<branch>": branch,
        "dirty: false  # set true": f"dirty: {str(dirty).lower()}  # set true",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if args.author:
        text = text.replace("[<your name>]", f"[{args.author}]")
    manifest_path.write_text(text, encoding="utf-8")

    for doc in ("PROTOCOL.md", "RESULTS.md"):
        path = target / doc
        path.write_text(
            path.read_text(encoding="utf-8").replace("EXP-YYYY-MM-NNN", exp_id),
            encoding="utf-8",
        )

    rel = target.relative_to(EXPERIMENTS.parents[2]).as_posix()
    print(f"Created {rel}")
    if dirty:
        print(
            "NOTE: the working tree is dirty, so `code.dirty: true` was recorded."
            " Explain what was uncommitted in ISSUES.md, or commit first and"
            " correct the manifest."
        )
    print("Next: fill PROTOCOL.md BEFORE running anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
