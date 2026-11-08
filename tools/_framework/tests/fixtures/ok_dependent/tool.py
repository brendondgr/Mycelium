from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class OkDependentTool(Tool):
    name = "ok_dependent"
    summary = "Fixture: ok dependent."
    depends_on = ("ok_leaf",)
    stages = (
        Stage(
            "fixture_dependent_late",
            "rank",
            "Dependent stage, declared first…",
            after=("fixture_leaf_stage",),
        ),
        Stage("fixture_dependent_brief", "brief", "Dependent brief…"),
    )
    subscribes = {
        "ok_leaf.pinged": (
            "tools._framework.tests.fixtures.ok_dependent.handlers:on_ping"
        ),
    }
