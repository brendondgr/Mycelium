"""The files tool's declaration. Standard library and spec imports only."""

from tools._framework.spec import Beat, Mount, Setting, Tool


def _s(key, kind, default, help_, **kw):
    env = "FILES_" + key.upper()
    return Setting(key, kind, default, help_, env=env, django=env, **kw)


class FilesTool(Tool):
    name = "files"
    summary = (
        "Stores files people upload to themselves, a lab, a department or a "
        "project, in structured folders under data/files/, extracts their "
        "text, and lets Mylo read them. Uploads are not virus-scanned."
    )
    depends_on = ()
    agent = "tools.files.agent"
    settings = (
        _s("max_bytes", "int", 25 * 1024 * 1024, "Largest file accepted, in bytes."),
        _s(
            "types",
            "list",
            ["pdf", "txt", "md", "csv", "docx"],
            "Accepted types, decided by the file's bytes, not its name.",
        ),
        _s("max_total_mb", "int", 0, "Most megabytes stored per owner. 0 = no limit."),
        _s("max_pages", "int", 0, "Most PDF pages extracted. 0 = all."),
        _s(
            "purge_after_days",
            "int",
            0,
            "Days a deleted file's bytes are kept before the sweep removes them.",
        ),
        _s(
            "data_dir",
            "str",
            "",
            "Where files are stored. Empty uses data/files/ at the repository root.",
        ),
    )
    beat = (
        Beat(
            "files-purge-deleted",
            "tools.files.tasks.purge_deleted",
            kwargs={"minute": "37", "hour": "4"},
        ),
    )
    mounts = (Mount("api/tools/files/"),)
