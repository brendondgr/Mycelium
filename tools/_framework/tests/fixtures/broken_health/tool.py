from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class BrokenHealthTool(Tool):
    name = "broken_health"
    summary = "Fixture: broken health."
    health = "tools._framework.tests.fixtures.broken_health.health:check"
