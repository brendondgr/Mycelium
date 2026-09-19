"""The ledger has two doors, and this test is the lock on both.

``read.py`` is how the rest of the backend reads the ledger. ``service.py`` is
how the Mylo gateway writes to it — the same arrangement
``integrations/services/resolve.py`` already has, for the same reason: the
gateway runs Django in process, so "Mylo owns no data" is enforced by making
every Discord-originated database touch go through one module.

This is not a style preference. The ledger owns the most sensitive thing
Mycelium touches, and anything reaching past these two modules is something
that can be holding a message body, a consent row or a reconciliation path in a
place nobody is auditing. The rule is checked by AST rather than by convention,
because a convention is only as good as the next person in a hurry.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

_APPS = Path(__file__).resolve().parent.parent.parent
_AMBIENT = _APPS / "ambient"

#: The only modules anything outside this app may import.
_READ_DOOR = "apps.ambient.read"
_GATEWAY_DOOR = "apps.ambient.service"
_PUBLIC = {_READ_DOOR, _GATEWAY_DOOR}
#: Backend apps allowed to name `apps.ambient` at all, and only through a door.
#: Everything else should not know it exists.
_MAY_READ = {"content", "integrations"}
#: Platforms whose gateway is a backend endpoint rather than a process of its
#: own (Plan 11): these files are that gateway, and may use its door.
_BACKEND_GATEWAYS = {
    "integrations/slack_views.py",
    "integrations/services/slack_events.py",
    "integrations/teams_views.py",
    "integrations/services/teams_events.py",
}
#: The gateway, which lives outside `web/backend/apps` entirely.
_GATEWAY = Path(__file__).resolve().parents[4] / "mylo"


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


def _is_test(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def _python_files_outside_ambient(*, include_tests: bool = False):
    """Every backend module outside this app.

    Test modules are excluded by default. A test in another app may build
    ambient rows directly — that is what a fixture *is*, and routing fixture
    setup through a read API would test the read API rather than the thing
    under test. The rule this file exists to enforce is about the code that
    ships, which is what the default covers.
    """
    for path in sorted(_APPS.rglob("*.py")):
        if _AMBIENT in path.parents or path == _AMBIENT:
            continue
        if "migrations" in path.parts:
            continue
        if not include_tests and _is_test(path):
            continue
        yield path


class AmbientImportBoundary(SimpleTestCase):
    def test_nothing_outside_the_app_reaches_past_a_door(self):
        offenders: list[str] = []
        for path in _python_files_outside_ambient():
            for module in _ambient_imports(path):
                if module not in _PUBLIC:
                    offenders.append(f"{path.relative_to(_APPS)} imports {module}")
        assert not offenders, (
            "the ambient ledger is reached through apps.ambient.read (reads) and "
            "apps.ambient.service (the gateway) and nothing else:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_backend_never_uses_the_gateway_door(self):
        """service.py exists for Mylo. Backend code reads through read.py.

        One named exception (Plan 11): Slack has no gateway process — its
        events arrive at a backend endpoint, which therefore *is* Slack's
        gateway and writes through the same door Mylo's does.
        """
        offenders = [
            str(path.relative_to(_APPS))
            for path in _python_files_outside_ambient()
            if _GATEWAY_DOOR in _ambient_imports(path)
            and str(path.relative_to(_APPS)) not in _BACKEND_GATEWAYS
        ]
        assert not offenders, offenders

    def test_the_gateway_imports_no_model_of_its_own(self):
        """Mylo owns no data: every ambient touch goes through service.py."""
        if not _GATEWAY.exists():  # pragma: no cover - checkout without the bot
            return
        offenders: list[str] = []
        for path in sorted(_GATEWAY.rglob("*.py")):
            for module in _ambient_imports(path):
                if module != _GATEWAY_DOOR:
                    offenders.append(f"mylo/{path.relative_to(_GATEWAY)} -> {module}")
        assert not offenders, offenders

    def test_only_the_named_apps_know_the_ledger_exists(self):
        strangers: list[str] = []
        for path in _python_files_outside_ambient(include_tests=True):
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
