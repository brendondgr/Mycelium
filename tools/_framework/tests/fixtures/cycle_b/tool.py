from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class CycleBTool(Tool):
    name = "cycle_b"
    summary = "Fixture: cycle b."
    depends_on = ("cycle_a",)
