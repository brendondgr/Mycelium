"""The ledger has one door, and this test is the lock on it.

Plan 01 says ``content`` imports the ambient app only through ``read.py``. That
is not a style preference: the ledger owns the most sensitive thing Mycelium
touches, and an app that reaches past the read API is an app that can be
holding a message body, a consent row or a reconciliation path in a place
nobody is auditing.

The rule is checked by AST rather than by convention, because a convention is
only as good as the next person in a hurry.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

_APPS = Path(__file__).resolve().parent.parent.parent
_AMBIENT = _APPS / "ambient"

# The one module outside this app may import.
_PUBLIC = "apps.ambient.read"
# Apps that are allowed to name `apps.ambient` at all, and only through _PUBLIC.
# Everything else should not know it exists.
_MAY_READ = {"content", "integrations"}


def _ambient_imports(path: Path) -> list[str]:
    """Every ``apps.ambient…`` module a file imports, by dotted name."""
    hits: list[str] = []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "apps.ambient" or module.startswith("apps.ambient."):
                hits.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "apps.ambient" or alias.name.startswith(
                    "apps.ambient."
                ):
                    hits.append(alias.name)
    return hits


def _python_files_outside_ambient():
    for path in sorted(_APPS.rglob("*.py")):
        if _AMBIENT in path.parents or path == _AMBIENT:
            continue
        if "migrations" in path.parts:
            continue
        yield path


class AmbientImportBoundary(SimpleTestCase):
    def test_nothing_outside_the_app_reaches_past_the_read_api(self):
        offenders: list[str] = []
        for path in _python_files_outside_ambient():
            for module in _ambient_imports(path):
                if module != _PUBLIC:
                    offenders.append(f"{path.relative_to(_APPS)} imports {module}")
        assert not offenders, (
            "the ambient ledger is read through apps.ambient.read and nothing "
            "else:\n  " + "\n  ".join(offenders)
        )

    def test_only_the_named_apps_know_the_ledger_exists(self):
        strangers: list[str] = []
        for path in _python_files_outside_ambient():
            if not _ambient_imports(path):
                continue
            app = path.relative_to(_APPS).parts[0]
            if app not in _MAY_READ:
                strangers.append(str(path.relative_to(_APPS)))
        assert not strangers, (
            "these files read the ambient ledger but are not in an app that "
            f"should: {strangers}"
        )

    def test_the_ledger_does_not_import_the_matching_layer(self):
        """The dependency runs one way. Evidence does not depend on ranking."""
        offenders: list[str] = []
        for path in sorted(_AMBIENT.rglob("*.py")):
            if "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                for module in modules:
                    if module.startswith("apps.content"):
                        offenders.append(f"{path.relative_to(_AMBIENT)} -> {module}")
        assert not offenders, offenders

    def test_the_read_api_states_its_surface(self):
        """``__all__`` is the contract; a reader should not have to guess."""
        from apps.ambient import read

        assert read.__all__
        for name in read.__all__:
            assert hasattr(read, name), name
