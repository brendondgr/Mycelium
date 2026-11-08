"""The living docs still describe the code: cited paths exist, every tool is
documented, every skill is registered.

A claim that is no longer true of the code is worse than no claim. These checks
cover the docs agents and contributors navigate by; dated snapshots (the
research audit, the changelog, experiment records, the decision ledger) are
history and are left alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools._framework import discovery

ROOT = discovery.REPO_ROOT
LIVING = [
    ROOT / "CLAUDE.md",
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "tools" / "README.md",
    *sorted((ROOT / "tools").glob("*/README.md")),
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / "docs" / "skills").glob("*.md")),
]
HISTORY = {"changelog.md", "research-audit.md"}
_PATH = re.compile(r"`((?:tools|web|ops|mylo|eval|docs)/[A-Za-z0-9_./-]+)`")


def _cited_paths(path: Path):
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        for match in _PATH.finditer(line):
            token = match.group(1).rstrip(".,;:")
            if any(ch in token for ch in "*{}<>"):
                continue  # a pattern, not a path
            yield lineno, token


@pytest.mark.parametrize(
    "doc",
    [p for p in LIVING if p.name not in HISTORY],
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_every_cited_repository_path_exists(doc):
    missing = [
        f"{doc.relative_to(ROOT)}:{lineno}: {token}"
        for lineno, token in _cited_paths(doc)
        if not (ROOT / token).exists()
        and not (ROOT / "web" / "backend" / token).exists()
    ]
    assert missing == []


def test_every_tool_has_a_readme_and_a_repo_map_section():
    repo_map = (ROOT / "docs" / "repo-map.md").read_text()
    tools_readme = (ROOT / "tools" / "README.md").read_text()
    for name, item in discovery.discover().items():
        assert (item.path / "README.md").exists(), name
        assert f"(`tools/{name}/`)" in repo_map, f"repo-map has no section for {name}"
        assert f"({name}/README.md)" in tools_readme, f"tools/README.md lacks {name}"


def test_every_registered_skill_has_both_entrypoints():
    index = (ROOT / "docs" / "skills" / "index.md").read_text()
    folders = re.findall(r"\| `([a-z-]+)/` \|", index)
    assert folders
    for folder in folders:
        for entry in (".claude/skills", ".agents/skills"):
            assert (ROOT / entry / folder / "SKILL.md").exists(), f"{entry}/{folder}"
