# Files

Stores files people upload to themselves, a lab, a department or a project,
reads their text, and gives Mylo four functions to read and search them.
Keeping a file is always an explicit upload (or an attachment to a chat
message the person sends); the résumé, project-state and lab-profile readers
still read and discard.

**Uploads are not virus-scanned.** The backend only reads them as text, and
they are only downloaded, as attachments, by people who could already see them.

| | |
|---|---|
| Depends on | — |
| Exports | `read`, `service`, `events` |
| Config | `[tools.files]` in `mycelium.toml` (on by default) |
| Nightly stages | — (Beat: purge of deleted files' bytes) |
| API | `api/tools/files/` (see `docs/api-contract.md`) |

## On disk

`data/files/<owner kind>/<owner id>/<file id>/` holds `original.<ext>`,
`text.md`, `pages.json` and `meta.json`. No path part comes from anything a
person typed; the extension comes from the sniffed type. The database row
(`StoredFile`) is the source of truth; `manage.py files_check [--fix]`
compares the two.

## Rules

- The type is decided by the bytes (`pdf`, `txt`, `md`, `csv`, `docx`), never
  the name. A docx's entry count and unpacked size are checked before reading.
- Who sees a file: the uploader; for an org or project file everyone who can
  see the owner; a personal file nobody else. Who adds: yourself, a project you
  can edit, a lab or department where you are at least a member. Who deletes:
  the uploader, or an owner or admin of the owning org, or an editor of the
  owning project. Upload, a download by someone else, and delete are audited.
- Small files (≤ 2 MB) are read during the upload; larger ones by the
  `tools.files.tasks.extract` task. A PDF with no text layer ends `no_text`.
- Deleting is soft; the bytes go at the next purge (`purge_after_days`).

## Doors

- `service.py` — `store_upload`, `run_extract`, `wait_for_text`, `text_of`,
  `pages_of`, `delete`, `purge_deleted`.
- `read.py` — `visible_files`, `can_see`.
- `agent.py` — Mylo's `files_list`, `files_info`, `files_read`, `files_search`
  and the `file:` reference kind (contributed through `Tool.agent`; this tool
  never imports the agent).

## Tests

`uv run --directory web/backend pytest -c pyproject.toml ../../tools/files`
