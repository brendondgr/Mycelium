"""§12 regression: the Discord path touches the ORM only through resolve.py.

Every model access must funnel through ``services.resolve`` so the "Mylo accesses
Mycelium's data only when appropriate" boundary is enforceable at the application
layer. This asserts, by AST, that no orchestration module / view / task imports a
``*.models`` module. ``resolve.py`` (the boundary), ``models.py``, ``serializers.py``
and ``admin.py`` (framework glue) are exempt.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

_APP = Path(__file__).resolve().parent.parent
_APPS = _APP.parent

# Modules on the Discord action path that must NOT import a model.
#
# `apps/content/reminders_discord.py` is on that path too — it is the send surface
# every reminder and report goes through — but it lives in a different app, so the
# glob below would never have reached it. It has followed the rule by convention
# since it was written; naming it here is what makes that enforceable rather than
# merely intended.
_GUARDED = [
    _APP / "views.py",
    _APP / "tasks.py",
    # Slack (ambient Plan 11) keeps the same rule; its boundary module is
    # ``services/slack_resolve.py``.
    _APP / "slack_views.py",
    *sorted((_APP / "services").glob("*.py")),
    _APPS / "content" / "reminders_discord.py",
]
_EXEMPT_NAMES = {"resolve.py", "slack_resolve.py", "__init__.py"}


def _typechecking_import_lines(tree: ast.AST) -> set[int]:
    """Line numbers of imports guarded by ``if TYPE_CHECKING:`` (allowed)."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        guarded.add(child.lineno)
    return guarded


def _imports_a_model(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    guarded = _typechecking_import_lines(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.lineno not in guarded:
            mod = node.module or ""
            # `from ..models import X`, `from apps.x.models import Y`, `from .models`
            if mod == "models" or mod.endswith(".models") or mod.endswith("models"):
                if mod.split(".")[-1] == "models":
                    hits.append(f"{path.name}: from {mod}")
        if isinstance(node, ast.Import) and node.lineno not in guarded:
            for alias in node.names:
                if alias.name.split(".")[-1] == "models":
                    hits.append(f"{path.name}: import {alias.name}")
    return hits


class ImportGraphTests(SimpleTestCase):
    def test_discord_path_imports_no_models_outside_resolve_module(self):
        offenders: list[str] = []
        for path in _GUARDED:
            if path.name in _EXEMPT_NAMES:
                continue
            offenders.extend(_imports_a_model(path))
        self.assertEqual(
            offenders,
            [],
            f"Discord-path modules must reach the ORM only via resolve.py: "
            f"{offenders}",
        )
