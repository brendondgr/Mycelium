"""``make new-tool NAME=x`` — copy the template into tools/<x>/.

Standard library only.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template"
TOOLS = HERE.parent

sys.path.insert(0, str(TOOLS.parent))
from tools._framework.discovery import PLATFORM_LABELS  # noqa: E402
from tools._framework.spec import NAME_RE  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not NAME_RE.match(argv[1]):
        print(
            "usage: scaffold.py NAME   (NAME matches [a-z][a-z0-9_]*)", file=sys.stderr
        )
        return 2
    name = argv[1]
    target = TOOLS / name
    if target.exists() or name in PLATFORM_LABELS:
        print(
            f"tools/{name} exists or {name!r} is a platform app label", file=sys.stderr
        )
        return 1
    words = name.split("_")
    subs = {
        "{{name}}": name,
        "{{NAME}}": name.upper(),
        "{{Class}}": "".join(w.title() for w in words) + "Tool",
        "{{Title}}": " ".join(words).title(),
    }
    for src in sorted(TEMPLATE.rglob("*.tmpl")):
        rel = src.relative_to(TEMPLATE).with_suffix("")
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text()
        for key, value in subs.items():
            text = text.replace(key, value)
        dest.write_text(text)
    print(
        f"created tools/{name}/ — fill in tool.py and README.md, "
        "then `make tools-check`."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
