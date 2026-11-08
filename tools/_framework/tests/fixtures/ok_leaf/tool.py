from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class OkLeafTool(Tool):
    name = "ok_leaf"
    summary = "Fixture: ok leaf."
    settings = (
        Setting(
            "greeting",
            "str",
            "hello",
            "What the fixture says.",
            env="FIXTURE_OK_LEAF_GREETING",
            django="FIXTURE_OK_LEAF_GREETING",
        ),
        Setting("depth", "int", 3, "A number.", django="FIXTURE_OK_LEAF_DEPTH"),
    )
    stages = (Stage("fixture_leaf_stage", "rank", "Leaf stage…"),)
    mounts = (Mount("api/", after="apps.research.urls"),)
    health = "tools._framework.tests.fixtures.ok_leaf.health:check"
