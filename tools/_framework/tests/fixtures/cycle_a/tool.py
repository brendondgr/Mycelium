from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class CycleATool(Tool):
    name = "cycle_a"
    summary = "Fixture: cycle a."
    depends_on = ("cycle_b",)
