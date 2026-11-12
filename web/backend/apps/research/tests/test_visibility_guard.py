"""A project's scope is read in exactly one place: ``apps/research/visibility.py``.

Fails if application code (tests and migrations aside) names the removed
``share_in_lab_reports`` flag, or queries a lab's projects with a raw
``scope_lab=…`` filter — on ``Project.objects`` or through a relation such as
``project__scope_lab`` — anywhere but the visibility module. Every such query
used to be its own small visibility rule, which is how a project hidden on one
surface kept leaking through another.

The allowlist names code that must see every project of a lab whatever its
scope — counting against the cap, scoring, seeding demo data — and never shows
the result to the lab. Adding to it needs the same reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
ROOTS = (REPO / "web" / "backend", REPO / "tools")
MODULE = REPO / "web/backend/apps/research/visibility.py"

#: Path (relative to the repository) -> why it may query a lab's projects raw.
ALLOWED = {
    # Cap counting: every active project of the lab counts against its cap.
    "web/backend/apps/research/limits.py": "cap counting",
    # The lab's derived interest vector blends every project of the lab; the
    # vector is never shown, only scored against (Phase 4 revisits).
    "web/backend/apps/accounts/aggregates.py": "derived lab vector",
    # Seeds and inspects demo data an operator asked for.
    "web/backend/apps/demo/management/commands/demo.py": "demo seeding",
    # Operator command annotating member fit for a lab's projects.
    "tools/recommendation/management/commands/annotate_member_fit.py": "operator",
    # Knowledge coverage per lab (Phase 4 moves projection onto the scope).
    "tools/agent/functions/knowledge.py": "Phase 4: knowledge projection",
}

#: Keyword names that query by the owning lab.
LAB_KEYS = ("scope_lab", "scope_lab_id")


#: Query methods whose keywords are filters (``create`` and friends are not).
QUERY_METHODS = {"filter", "exclude", "get"}


def _is_lab_key(name: str | None) -> bool:
    """scope_lab=, scope_lab_id__in=, scope_lab__slug=, project__scope_lab=…"""
    return bool(name) and any(part in LAB_KEYS for part in name.split("__"))


def _is_query(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        # A bare Q() cannot say which model it filters; only its relation keys
        # (project__scope_lab=…) are known to be about projects.
        return func.id == "Q"
    return isinstance(func, ast.Attribute) and func.attr in QUERY_METHODS


def _rooted_at_project_manager(node: ast.AST) -> bool:
    """Whether a call chain starts at ``Project.objects``."""
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            if (
                node.attr == "objects"
                and isinstance(node.value, ast.Name)
                and node.value.id == "Project"
            ):
                return True
            node = node.value
        else:
            return False


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "share_in_lab_reports":
            out.append(f"{node.lineno}: names share_in_lab_reports")
        elif isinstance(node, ast.Attribute) and node.attr == "share_in_lab_reports":
            out.append(f"{node.lineno}: reads .share_in_lab_reports")
        elif isinstance(node, ast.Constant) and node.value == "share_in_lab_reports":
            out.append(f"{node.lineno}: string 'share_in_lab_reports'")
        elif isinstance(node, ast.keyword) and node.arg == "share_in_lab_reports":
            out.append(f"{node.lineno}: filters on share_in_lab_reports")
        elif isinstance(node, ast.Call) and _is_query(node):
            for kw in node.keywords:
                if not _is_lab_key(kw.arg):
                    continue
                relation = kw.arg.split("__")[0] not in LAB_KEYS
                if relation or _rooted_at_project_manager(node):
                    out.append(f"{node.lineno}: raw project query on {kw.arg}=")
    return out


def _app_files():
    for root in ROOTS:
        for path in root.rglob("*.py"):
            parts = set(path.relative_to(REPO).parts)
            if parts & {"tests", "migrations", "node_modules", ".venv", "sandbox"}:
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            yield path


def test_project_scope_is_read_only_through_the_visibility_module():
    found: list[str] = []
    for path in _app_files():
        rel = path.relative_to(REPO).as_posix()
        if path == MODULE or rel in ALLOWED:
            continue
        found.extend(f"{rel}:{v}" for v in _violations(path))
    assert not found, (
        "Project scope read outside apps/research/visibility.py:\n  "
        + "\n  ".join(found)
    )


def test_the_guard_catches_what_it_is_for(tmp_path):
    sample = tmp_path / "leak.py"
    sample.write_text(
        "Project.objects.filter(scope_lab=lab)\n"
        "Project.objects.active().filter(scope_lab_id__in=ids)\n"
        "Score.objects.filter(target_project__scope_lab=lab)\n"
        "Project.objects.filter(share_in_lab_reports=True)\n"
        "project.share_in_lab_reports\n"
        "Subscription.objects.filter(scope_lab=lab)\n"
        "Project.objects.create(scope_lab=lab)\n"
        "Q(scope_lab_id__in=ids)\n"
        "Q(project__scope_lab=lab)\n"
    )
    hits = _violations(sample)
    assert sorted({int(h.split(":")[0]) for h in hits}) == [1, 2, 3, 4, 5, 9]
