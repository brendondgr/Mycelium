"""The knowledge core has two doors, and this test is the lock on both.

``read.py`` is how anything outside the app reads the graph, and every function
in it bakes in the tiers it may return. ``service.py`` is how anything outside
writes. Reaching past them — importing the models, the linker, the projection —
would be a way to read a conversational edge without going through the one
module that promises never to hand one to collaboration search.

The collaboration app is held tighter still: it may import only the read
functions that cannot return conversation about anyone but the reader, and it
must name them explicitly, so the list of what it can see is greppable.

Checked by AST, as ``apps/ambient``'s boundary is, because a convention is only
as good as the next person in a hurry.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

_APPS = Path(__file__).resolve().parent.parent.parent
_KNOWLEDGE = _APPS / "knowledge"
_COLLAB = _APPS / "collab"

_READ_DOOR = "apps.knowledge.read"
_WRITE_DOOR = "apps.knowledge.service"
_PUBLIC = {_READ_DOOR, _WRITE_DOOR}

#: What collaboration search may know. Everything here is declared or
#: demonstrated about other people, or the reader's own record, or a project
#: the reader can already see.
_COLLAB_MAY_READ = {
    "EdgeView",
    "WorkView",
    "coauthor_distances",
    "concept_vectors",
    "discoverable_works",
    "discoverable_edges",
    "evidence_texts",
    "introduction_paths",
    "lab_declared_edges",
    "network_of",
    "own_edges",
    "privately_held_global_concepts",
    "project_edges",
}


def _imports(path: Path):
    """``(module, names)`` for every import in a file; ``names`` is None for
    ``import x`` and the imported names for ``from x import a, b``."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield node.module or "", [alias.name for alias in node.names]
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None


def _knowledge_modules(path: Path) -> list[tuple[str, list[str] | None]]:
    hits = []
    for module, names in _imports(path):
        if module == "apps.knowledge" or module.startswith("apps.knowledge."):
            hits.append((module, names))
    return hits


def _is_test(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def _outside(root: Path | None = None, *, include_tests: bool = False):
    for path in sorted((root or _APPS).rglob("*.py")):
        if _KNOWLEDGE in path.parents:
            continue
        if "migrations" in path.parts:
            continue
        if not include_tests and _is_test(path):
            continue
        yield path


class KnowledgeImportBoundary(SimpleTestCase):
    def test_nothing_outside_the_app_reaches_past_a_door(self):
        offenders = []
        for path in _outside():
            for module, names in _knowledge_modules(path):
                # ``from apps.knowledge import read`` names a door by attribute.
                named = {f"{module}.{name}" for name in names or []}
                if module == "apps.knowledge" and named <= _PUBLIC:
                    continue
                if module not in _PUBLIC:
                    offenders.append(f"{path.relative_to(_APPS)} imports {module}")
        assert not offenders, (
            "the knowledge core is read through apps.knowledge.read and written "
            "through apps.knowledge.service, and nothing else:\n  "
            + "\n  ".join(offenders)
        )

    def test_collaboration_reads_only_what_cannot_expose_conversation(self):
        if not _COLLAB.exists():  # the app arrives with plan CN-03
            return
        offenders = []
        for path in _outside(_COLLAB, include_tests=False):
            for module, names in _knowledge_modules(path):
                where = path.relative_to(_APPS)
                if module == _READ_DOOR and names is not None:
                    extra = set(names) - _COLLAB_MAY_READ
                    if extra:
                        offenders.append(f"{where} reads {sorted(extra)}")
                elif module == _WRITE_DOOR and names is not None:
                    continue
                else:
                    # ``import apps.knowledge.read`` or ``from apps.knowledge
                    # import read`` would reach every function by attribute.
                    offenders.append(f"{where} imports {module} as a module")
        assert not offenders, offenders

    def test_the_core_depends_on_nothing_above_it(self):
        """The graph sits below matching, ambient, and collaboration.

        The single exception is the shared embedder accessor, which is where
        the corpus embedder lives today.
        """
        allowed = {"apps.content.embeddings"}
        above = ("apps.content", "apps.ambient", "apps.collab", "apps.integrations")
        offenders = []
        for path in sorted(_KNOWLEDGE.rglob("*.py")):
            if "migrations" in path.parts or _is_test(path):
                continue
            for module, _ in _imports(path):
                if module.startswith(above) and module not in allowed:
                    offenders.append(f"{path.relative_to(_KNOWLEDGE)} -> {module}")
        assert not offenders, offenders

    def test_the_doors_state_their_surface(self):
        from apps.knowledge import read, service

        for door in (read, service):
            assert door.__all__
            for name in door.__all__:
                assert hasattr(door, name), f"{door.__name__}.{name}"
