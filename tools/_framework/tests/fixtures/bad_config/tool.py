from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class BadConfigTool(Tool):
    name = "bad_config"
    summary = "Fixture: bad config."
    settings = (Setting("limit", "int", 5, "A number."),)
