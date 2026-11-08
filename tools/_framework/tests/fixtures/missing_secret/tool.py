from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class MissingSecretTool(Tool):
    name = "missing_secret"
    summary = "Fixture: missing secret."
    secrets = ("FIXTURE_SECRET_THAT_IS_NEVER_SET",)
