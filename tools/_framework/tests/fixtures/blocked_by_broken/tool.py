from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class BlockedByBrokenTool(Tool):
    name = "blocked_by_broken"
    summary = "Fixture: blocked by broken."
    depends_on = ("broken_import",)
    stages = (Stage("fixture_blocked_stage", "deliver", "Never runs…"),)
