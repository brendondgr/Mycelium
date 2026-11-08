"""Golden snapshots of everything the tools refactor must leave unchanged.

``write`` records the current state; ``check`` compares against it and prints a
diff per surface. The surfaces are the ones a move can silently break without a
single test failing: the URL table, the Celery task names and Beat schedule, the
management commands, every model's database table, the nightly stage plan, and
the instance configuration keys.

Run from the repository root::

    uv run --no-sync --project web/backend python tools/_framework/golden.py check

Intended changes are made by re-running ``write`` and committing the diff, so a
reviewer sees exactly what moved.
"""

from __future__ import annotations

import difflib
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "golden"
# Run as a script, this folder would be sys.path[0] and its modules (config.py
# among them) would shadow real packages; drop it.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != GOLDEN.parent]
sys.path.insert(0, str(ROOT / "web" / "backend"))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# Resolve the instance with no file and no environment overrides, so a
# developer's own mycelium.toml never changes a snapshot.
os.environ.setdefault("MYCELIUM_CONFIG", "none")


def _urls() -> list[str]:
    from django.urls import get_resolver
    from django.urls.resolvers import URLPattern, URLResolver

    out: list[str] = []

    def walk(patterns, prefix: str) -> None:
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                cb = p.callback
                view = getattr(cb, "view_class", None) or getattr(cb, "cls", None) or cb
                out.append(f"{prefix}{p.pattern}\t{p.name or '-'}\t{view.__name__}")

    walk(get_resolver().url_patterns, "")
    return out


def _tasks() -> list[str]:
    from config.celery import app

    app.loader.import_default_modules()
    return sorted(t for t in app.tasks if not t.startswith("celery."))


def _beat() -> list[str]:
    from django.conf import settings

    sched = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    return [
        f"{k}\t{v.get('task')}\t{v.get('schedule')!r}" for k, v in sorted(sched.items())
    ]


def _commands() -> list[str]:
    from django.core.management import get_commands

    return sorted(get_commands())


def _tables() -> list[str]:
    from django.apps import apps

    rows = []
    for model in apps.get_models(include_auto_created=True):
        rows.append(f"{model._meta.db_table}\t{model.__name__}")
    return sorted(rows)


def _stages() -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "_golden_manual_all", ROOT / "ops" / "nightly" / "manual_all.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    stages = (
        module.planned_container_stages()
        if hasattr(module, "planned_container_stages")
        else module.CONTAINER_STAGES
    )
    return [f"{cmd}\t{' '.join(args)}" for cmd, args, _intro in stages]


def _config() -> list[str]:
    from config import instance

    return [
        f"{s.key}\t{s.kind}\t{s.default!r}\t{s.env or '-'}" for s in instance.SETTINGS
    ]


SURFACES = {
    "urls": _urls,
    "celery_tasks": _tasks,
    "beat": _beat,
    "commands": _commands,
    "tables": _tables,
    "nightly_stages": _stages,
    "config": _config,
}


def collect() -> dict[str, list[str]]:
    import django

    django.setup()
    return {name: fn() for name, fn in SURFACES.items()}


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "check"
    current = collect()
    if mode == "write":
        GOLDEN.mkdir(exist_ok=True)
        for name, lines in current.items():
            (GOLDEN / f"{name}.txt").write_text("\n".join(lines) + "\n")
        print(f"wrote {len(current)} golden files to {GOLDEN}")
        return 0
    failed = False
    for name, lines in current.items():
        path = GOLDEN / f"{name}.txt"
        expected = path.read_text().splitlines() if path.exists() else []
        if expected != lines:
            failed = True
            print(f"--- {name}: differs from golden")
            sys.stdout.writelines(
                line + "\n"
                for line in difflib.unified_diff(
                    expected, lines, "golden", "current", lineterm="", n=0
                )
            )
        else:
            print(f"ok  {name} ({len(lines)} lines)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
