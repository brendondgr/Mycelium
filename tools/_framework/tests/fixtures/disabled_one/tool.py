from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class DisabledOneTool(Tool):
    name = "disabled_one"
    summary = "Fixture: disabled one."
    pass
