"""The import rules (see tools/_framework/boundaries.py) on the real tools,
the platform's allowlist ratchet, and the fixtures that must break them."""

from __future__ import annotations

from pathlib import Path

from tools._framework import boundaries

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_real_tools_follow_the_import_rules():
    assert boundaries.check_tools() == []


def test_platform_imports_of_tools_match_the_allowlist_exactly():
    assert boundaries.check_platform() == []


def test_the_rules_catch_what_they_claim_to():
    problems = "\n".join(boundaries.check_tools(FIXTURES))
    # forbidden_import reaches into ok_leaf's internals without depending on it.
    assert (
        "forbidden_import imports tools._framework.tests.fixtures.ok_leaf.internal"
        in problems
    )
    # ok_dependent declares ok_leaf and imports only its read module: clean.
    assert "ok_dependent" not in problems
    # Locating the repository by counting parents breaks when a tool moves.
    assert "forbidden_import/paths.py: locates the repository" in problems


def test_internal_module_of_a_dependency_is_rejected(tmp_path):
    pkg = tmp_path / "tools"
    for name, deps, src in (
        ("base", "()", ""),
        ("top", '("base",)', "from tools.base.internal import X  # noqa\n"),
    ):
        (pkg / name).mkdir(parents=True)
        (pkg / name / "__init__.py").write_text("")
        (pkg / name / "tool.py").write_text(
            "from tools._framework.spec import Tool\n\n\n"
            f"class T(Tool):\n    name = {name!r}\n    depends_on = {deps}\n"
        )
        (pkg / name / "read.py").write_text(src)
    (pkg / "__init__.py").write_text("")
    # Discovery imports these as the package ``tools`` from tmp_path; keep them
    # out of the real package's namespace by checking only the AST rule here.
    imports = list(boundaries.imports_of(pkg / "top" / "read.py", "tools.top"))
    assert imports[0].module == "tools.base.internal.X"
    assert boundaries._owner(imports[0].module, "tools") == ("base", "internal")


def test_tool_foreign_keys_point_only_into_platform_self_or_dependencies(settings):
    from django.apps import apps

    report = settings.TOOLS_REPORT
    tool_labels = {report.tools[n].label: n for n in report.order}
    problems = []
    for name in report.loaded():
        item = report.tools[name]
        allowed = {item.label, *(report.tools[d].label for d in item.depends_on)}
        for model in apps.get_app_config(item.label).get_models():
            for field in model._meta.get_fields():
                related = getattr(field, "related_model", None)
                if related is None or not getattr(field, "concrete", False):
                    continue
                target = related._meta.app_label
                if target in tool_labels and target not in allowed:
                    problems.append(f"{model.__name__}.{field.name} -> {target}")
    assert problems == []
