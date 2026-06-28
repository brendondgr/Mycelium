# Mycelium API Contract

Committed shapes for frontend consumers. Session authentication uses Django
session cookies and CSRF tokens; do not store credentials in browser storage.

## Auth

Base path: `/api/auth/`

### `GET /api/auth/csrf/`

Ensures a `csrftoken` cookie is set. Response body:

```json
{ "detail": "ok" }
```

### `POST /api/auth/login/`

Request:

```json
{
  "username": "string",
  "password": "string"
}
```

Success `200` — authenticated user summary:

```json
{
  "id": 1,
  "username": "string",
  "email": "string",
  "is_staff": false,
  "is_superuser": false
}
```

Errors:

- `400` — `{ "non_field_errors": ["Enter both username and password."] }`
- `401` — `{ "non_field_errors": ["Invalid username or password."] }`

### `POST /api/auth/register/`

Creates the user and provisions a starting workspace in one atomic step, then
sets the session (the caller is logged in on success).

Request:

```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "password_confirm": "string",
  "first_name": "string (optional)",
  "last_name": "string (optional)",
  "account_type": "personal | lab | department",
  "org_name": "string (required for lab/department)",
  "institution": "string (optional)"
}
```

`account_type` chooses what is provisioned: `personal` creates a user-scoped
subscription (Free) and a self-paid seat; `lab` also creates a Lab with the
founder as owner + PI lead (Lab tier); `department` also creates a Department the
founder owns (Canopy tier). Every account gets one founding seat.

Success `201` — same user summary as login (id, username, email, is_staff,
is_superuser); session set.

Errors:

- `400` — field errors, e.g. `{ "email": ["An account with that email already exists."] }`,
  `{ "password_confirm": ["Passwords do not match."] }`,
  `{ "org_name": ["A lab name is required."] }`.
- `403` — CSRF missing or blocked.

### `POST /api/auth/logout/`

Success `204` with empty body. Requires CSRF header when using session auth.

### `GET /api/auth/me/`

Success `200` — same user summary as login.

`401` with empty body when anonymous.

### `POST /api/auth/verify-email/`

Marks the signed-in caller's email verified (scaffold). Verification is
non-blocking at signup; this only flips `Profile.is_verified`. Real token
signing, email templates, and SMTP delivery are deferred.

Success `200` — `{ "is_verified": true }`.

`401` / `403` when anonymous.

## Profile & onboarding intake

All endpoints below require an authenticated session.

### `POST /api/auth/intake/synthesize/`

Builds an editable research-interest draft from **at most one** publication
source plus an **optional** résumé/CV upload. `multipart/form-data` fields:

| Field | Required | Notes |
| --- | --- | --- |
| `source` | with `identifier` | One of `openalex`, `semantic`, `scholar`, `orcid`. |
| `identifier` | with `source` | The author id for that source. |
| `resume` | optional | A PDF or text file (≤ 5 MB). Parsed and discarded — never stored. |

At least one of (`source` + `identifier`) or `resume` must be present. The
importer takes ~10 most-cited and ~10 most-recent works from the site, merges
them with the résumé, and drafts a natural-language statement (language model
when configured, deterministic template otherwise).

Success `200` — `{ "draft": { … }, "interests": { "version": 1, "areas": [...],
"keywords": [...], "methods": [...], "skills": [...], "statement": "…",
"sources": { … } } }`. The `interests` object is contract-valid and ready to
post to `confirm`.

`400` for a missing/partial/unknown source or an unreadable/oversize/unsupported
file (`{ "resume": ["…"] }`). `502` when an upstream source fails.

### `POST /api/auth/intake/import/`

JSON `{ "identifier", "source" }` → `{ "draft", "interests" }` from a single
source (no résumé, no statement). The lighter sibling of `synthesize`.

### `POST /api/auth/intake/session/`

Drives one stateless step of the bounded Mylo intake loop. Body
`{ "interests", "free_text"?, "answer"? }` → `{ "interests", "question",
"summary", "done" }`.

### `POST /api/auth/intake/confirm/`

Validates `{ "interests" }` against the contract and saves it onto the caller's
own profile. Success `200` returns the profile; `400` on contract violation.

### `GET` / `PATCH` `/api/auth/profile/me/`

Reads or updates the caller's own profile (`academic_title`, `institution`,
`interests`, external ids). `interests` is validated against the contract.

### `GET` / `PATCH` `/api/auth/watch/me/`

Reads or updates what Milo keeps an eye on for the caller (own only). The row is
created on first access with defaults. Body / response:
`{ "topics": [...], "categories": [...], "cadence": "daily|weekly|realtime" }`.
`topics` and `categories` are deduped string lists (≤ 50 each); an unknown
cadence or a non-list value returns `400`.
