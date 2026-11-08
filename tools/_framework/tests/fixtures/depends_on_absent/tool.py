from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class DependsOnAbsentTool(Tool):
    name = "depends_on_absent"
    summary = "Fixture: depends on absent."
    depends_on = ("no_such_tool",)
