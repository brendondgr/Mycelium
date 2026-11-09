# Mylo agent: stored files, conversation logs and streaming

Part of the [Mylo agent plan](README.md). Correlation ID `20261109-mylo-agent`.
This covers backend features only. No UI is built here: each feature is
complete through its API, the CLI and tests, ready for the web app to use.

## Files

### Why a tool, and why now

Owner decision D-1: people can upload files in this pass and ask Mylo about
them. Files are their own tool, `tools/files`, and not part of the agent, for
three reasons:

- other features will want them (project state extraction could read a stored
  file instead of a fresh upload);
- an operator can turn storage off without turning chat off;
- the agent stays independent of it. `tools/files` contributes its functions
  and the `file:` reference kind through `Tool.agent`, the same way `fulltext`
  does, and the agent does not list it in `depends_on`.

It is non-core, enabled by default and depends on nothing.

The existing "read and discarded" flows (résumé import, reading project state
from a document, lab profile intake) do not change. Keeping a file is always
an explicit upload to the store, never a side effect of another feature.

### Layout on disk

`data/` is already the gitignored home of runtime state (`data/fulltext/files/`,
`data/collect`). The root is anchored to the checkout, not the working
directory, as the collector's store is. Otherwise a store opened from another
directory would look empty.

```text
data/files/
└── <owner kind>/<owner id>/          user/<id> · lab/<id> · department/<id> · project/<uuid>
    └── <file uuid>/
        ├── original.<ext>             the bytes as uploaded; ext from the sniffed type, never the filename
        ├── text.md                    extracted text, as markdown
        ├── pages.json                 page → line offsets, for "#n p.14" citations
        └── meta.json                  a copy of the database row, for recovery only
```

No path component comes from anything a person typed. The database is the
source of truth. `meta.json` exists so a store can be checked against the
database (`manage.py files_check` reports orphans both ways and repairs
nothing without `--fix`).

### The model

`StoredFile`:

- **Identity and owner:** `id` (UUID); the owner, exactly one of user, lab,
  department or project (the `core.db` exactly-one-FK helper); `uploaded_by`.
- **What it is:** `filename` (cleaned, for display only), `content_type`
  (sniffed), `size`, `sha256`, `pages`, `chars`.
- **Extraction:** `status` (`stored` → `extracting` → `ready` | `no_text` |
  `failed`) and `extract_error` (a stable code and plain words).
- **Where it came from:** `origin` (`upload` | `chat`) and `thread_id` when it
  was attached in a chat.
- **Lifecycle:** `created_at`, `deleted_at`.

The same file uploaded twice to the same owner is stored once (by `sha256`).
The second upload returns the first row.

**Who can see a file:**

- the uploader, always;
- for an org- or project-owned file, everyone who can see the owner;
- for a personal file, nobody else.

There is no per-file sharing list in this pass. A person shares a file by
uploading it to the project or lab.

### Limits and safety

`[tools.files]` settings, each with an operator default:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Ships on |
| `max_bytes` | 25 MB | Per file. Also enforced by Django's upload limits on this route |
| `types` | `pdf, txt, md, csv, docx` | Accepted, decided by sniffing the bytes, not by the name |
| `max_total_mb` | `0` (no limit) | Per owner; a tier or org may set its own |
| `max_pages` | `0` (no limit) | Pages extracted per PDF |
| `purge_after_days` | `0` | Days a deleted file's bytes are kept before the sweep removes them; `0` removes them at the next sweep |

Safety rules, each with a test:

- The type is sniffed from the bytes. A file whose bytes don't match an
  accepted type is refused, whatever it is called.
- A `docx` is a zip. Its total uncompressed size and entry count are capped
  before anything is read. That guards against zip bombs.
- Files are never served inline. Downloads carry
  `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.
- Extracted text is always wrapped in `<untrusted source="#n">` when the model
  reads it. A file cannot instruct Mylo.
- Upload, download by someone other than the uploader, and delete each write
  an `AuditEvent`.
- **Not in this pass:** virus scanning. Files are only read as text by the
  backend and only downloaded deliberately by people who could already see
  them, but the README for `tools/files` must say plainly that uploads are not
  scanned.

### Extraction

A Celery task, `files.extract`, runs after the upload:

- **PDF:** text per page with `pypdf`, the same library the résumé reader
  uses, so no new dependency. Page offsets go to `pages.json`.
- **txt, md, csv:** decoded as UTF-8 with a fallback, kept as is.
- **docx:** paragraphs and tables from the document XML with the standard
  library (`zipfile`, `xml.etree`), so no new dependency.
- **A PDF with no text layer** (a scan) ends `no_text`, with the reason "this
  PDF has no text to read; OCR is not available". No OCR in this pass.

### API: `api/tools/files/`

| Route | What |
|---|---|
| `POST files/` | Upload (multipart: `file`, `owner_kind`, `owner_id`). Checks the caller can add files to that owner: themselves; a project they can edit; a lab or department where they are at least `member` |
| `GET files/?owner_kind=&owner_id=` | List what the caller can see |
| `GET files/<id>/` | One file's row and status |
| `GET files/<id>/text/?offset=&limit=` | The extracted text, line-numbered |
| `GET files/<id>/download/` | The original, as an attachment |
| `DELETE files/<id>/` | The uploader, or an owner or admin of the owning org or project. Soft delete; the sweep removes the bytes |

POST routes register both trailing-slash forms. All routes go in
`docs/api-contract.md`.

### What the agent gets

These are contributed by `tools/files/agent.py`. All are `risk=read`, and
`output` follows the owner (`person` for a personal file, `project` / `lab` /
`department` otherwise):

- `files_list(scope)`: the files the caller can see in this thread's scope;
- `files_info(ref)`: name, type, pages, status;
- `files_read(ref, page | offset, limit)`: a slice of the text, line-numbered,
  capped like every result;
- `files_search(ref, query)`: BM25 over the file's chunks, returning passages
  with page and line, so the model can cite `#n p.14` or `#n:88`.

The `file:` reference kind resolves `file:<uuid>`, checks it through the gate's
object layer, and gives it a `#n` number in the thread.

**Chat attachments.** `send(caller, text, attachments=[…])` accepts new
uploads or existing file ids:

- **Where new uploads go:** into the thread's scope owner, with
  `origin=chat`.
- **Waiting for the text:** the turn starts once extraction is done, waiting
  at most 30 s. A file still extracting is shown to the model as "being read;
  try `files_read` in a moment".
- **Short files:** under 25 % of the context window, a file goes into the
  message whole, line-numbered, inside `<untrusted>`.
- **Longer files:** they appear as a card with how to read them, as in
  GAIFA's §5.2.

## Conversation logs

The thread and its `AgentEvent` rows are the log (see
[README](README.md#state-thread-and-event-log)). This pass adds everything
needed to manage it from an API:

- **List and search** a person's threads by title, purpose and their own
  words (`AgentThreadDigest`, shared with recall).
- **Rename, archive, delete.** Deleting a thread deletes its events. Files
  attached in it stay with their owner, because a file belongs to its scope,
  not to a chat.
- **Fork** at a seq (GAIFA §2: copy events `1..seq`, dropping a trailing
  unresolved step).
- **Export** as JSON (the events) or Markdown (a readable transcript with
  citations resolved to titles). The export is checked through the gate like
  any read, so it contains only what the caller may still see.
- **Retention:** `tools.agent.retention_days` (default `0`, keep). A Beat sweep
  deletes threads untouched for longer.
- **Who can read a thread:**
  - only its owner, the person who started it;
  - a thread opened in a lab, department or project scope is still that
    person's conversation, not the org's;
  - org admins cannot read members' threads.

  Shared org threads, such as a Discord channel conversation, are a separate
  design for the Discord plan, where the audience already decides what is
  said in them.

## Streaming

### The path of an event

```text
run_turn (Celery worker)
   │  appends AgentEvent (Postgres)      ──┐
   │  publishes the event + transients   ──┼──▶ Redis channel agent:t:<thread>
   ▼                                       │        (and agent:u:<user> for a person's threads)
LLMClient.complete_stream → text/thinking deltas (transient, never stored)
                                           │
   ┌───────────────────────────────────────┘
   ▼
SSE  GET api/tools/agent/threads/<id>/stream/?after=<seq>     (web, later the app UI)
in-process  service.subscribe(caller, thread, after=seq)       (CLI now, Discord later)
```

- **Stored events** carry their `seq` as the SSE `id:`. A client that
  reconnects with `Last-Event-ID` (or `?after=`) gets every stored event after
  it, then live ones.
- **Transient events** carry no `id`: text and thinking deltas, function
  progress, the context meter, and state. A delta missed during a reconnect
  doesn't matter, because the stored `assistant` event that follows has the
  whole text.
- **No gap or duplicate on connect:** the stream subscribes to Redis first,
  then replays from Postgres, then drops any live event whose `seq` it has
  already sent.
- **Heartbeat:** a comment line every 15 s keeps proxies from closing an idle
  stream.
- **Headers:** `Cache-Control: no-cache` and `X-Accel-Buffering: no`, so the
  reverse proxy does not buffer.
- **Redis database:** the channels use a dedicated Redis database, set as
  `tools.agent.redis_db`. `fulltext` already uses db 7.

### The server

Compose runs Django with `runserver`, which is threaded WSGI. Each open stream
holds one thread, which is fine for a lab-sized instance and for tests. The
stream view is a plain generator that Django's `StreamingHttpResponse` serves
under WSGI, and the same code accepts an async iterator under ASGI. Moving to
an ASGI server (uvicorn) for many concurrent streams is a deployment choice
for the web UI plan and does not change this code.

### Cancel, queue, steer

- **Cancel:** `POST threads/<id>/cancel/` sets a Redis flag and revokes the
  Celery task. The loop checks the flag between steps, and the model stream
  checks it every chunk. Unfinished calls get `cancelled` results (GAIFA §11).
- **Queue:** a message sent during a turn is held in `AgentQueuedMessage`.
  When the turn ends, held messages become `user` events in order, answered by
  one turn.
- **Steer:** `send(…, steer=true)` writes the message at once for the running
  turn's next model call.

### The CLI

`manage.py agent chat --user <name> --scope <personal|lab:<slug>|project:<uuid>>`
opens or resumes a thread. It streams through `service.subscribe`, renders
`ask_user` as a numbered prompt, and accepts `/attach <path>`, `/cancel`,
`/fork <seq>` and `/export`. It is the developer's way to drive the whole
backend end to end before any UI exists, and the evaluation runner uses the
same service calls.

## Tests

- **Files:**
  - type sniffing, the size cap and the zip-bomb guard;
  - no path from a filename, with traversal attempts in filenames;
  - nothing served inline;
  - visibility per owner kind and role;
  - deduplication;
  - delete then sweep removes the bytes;
  - `files_check` finds orphans;
  - extraction per type, scanned PDF → `no_text`;
  - an attachment in a project thread lands under that project.
- **Logs:**
  - fork drops an unresolved trailing step;
  - the export contains nothing the caller can no longer see;
  - retention deletes old threads;
  - another person, an org admin included, cannot read a thread.
- **Streaming:**
  - reconnect with `Last-Event-ID` loses no stored event and duplicates none;
  - deltas are never stored;
  - cancel stops within one step;
  - queued messages are answered together;
  - a stream for a thread the caller cannot read is refused before anything
    is sent.

*Check:* `uv run --directory web/backend pytest -c pyproject.toml ../../tools/files ../../tools/agent -k "files or stream or log"`
(needs the Compose Postgres and Redis).
