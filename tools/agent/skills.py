"""Skills: ``SKILL.md`` folders, listed by description, read with read_skill.

The agent ships ``tools/agent/skills/``; any loaded tool may ship its own
through ``SKILLS_DIR`` in its agent module. A tool's skills are listed only
while that tool is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .registry import registry


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    tool: str


def _front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip().strip('"')
    return out


def available() -> list[Skill]:
    out = []
    for tool, folder in registry().skill_dirs:
        if not folder.is_dir():
            continue
        for skill_md in sorted(folder.glob("*/SKILL.md")):
            meta = _front_matter(skill_md.read_text())
            out.append(
                Skill(
                    name=meta.get("name") or skill_md.parent.name,
                    description=meta.get("description", ""),
                    path=skill_md,
                    tool=tool,
                )
            )
    return out


def read(name: str) -> str | None:
    for skill in available():
        if skill.name == name:
            text = skill.path.read_text()
            if text.startswith("---"):
                end = text.find("\n---", 3)
                text = text[end + 4 :] if end >= 0 else text
            return text.strip()
    return None
