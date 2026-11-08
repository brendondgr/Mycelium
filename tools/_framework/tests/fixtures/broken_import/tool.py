from tools._framework.spec import Mount, Setting, Stage, Tool  # noqa: F401


class BrokenImportTool(Tool):
    name = "broken_import"
    summary = "Fixture: broken import."
    stages = (Stage("fixture_broken_stage", "deliver", "Never runs…"),)
