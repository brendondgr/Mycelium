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
  "name": "string",
  "initials": "AB",
  "is_staff": false,
  "is_superuser": false,
  "onboarding_completed": false
}
```

`name` is the full name when set (else the username) and `initials` is its
one- or two-letter avatar form; the dashboard greets and labels the user with
these. `onboarding_completed` is false until research interests are saved.

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
importer takes ~10 most-cited and ~10 most-recent works (titles + abstracts +
declared interests) from the site and the raw résumé text, then asks the
configured language model to return all five interest fields at once
(`statement`, `areas`, `keywords`, `methods`, `skills`). When no model is
available it falls back to the structured author draft, so the endpoint always
returns a contract-valid profile.

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
`{ "topics": [...], "categories": [...], "cadence": "daily|weekly" }`.
`topics` and `categories` are deduped string lists (≤ 50 each); an unknown
cadence or a non-list value returns `400`.

## Workspace (labs, members, projects)

Endpoints that back the authenticated dashboard. All require a session. Reads are
listed first; lab creation and project creation are documented inline.

### `GET /api/auth/labs/`

The caller's lab memberships, for the workspace switcher. Success `200` — a list:

```json
[
  { "slug": "reyes-lab", "name": "Reyes Lab", "role": "owner", "is_lead": true, "department": "Biology" }
]
```

`role` is the raw membership role (`owner | admin | member | viewer`); `is_lead`
marks a PI. `department` is the lab's department name or `null`. The frontend
derives a human label (e.g. lead → "PI"). `401`/`403` when anonymous.

### `POST /api/auth/labs/`

Create a new lab after the account already exists. Body `{ "name": "Ocean Lab" }`.
The caller becomes the lab OWNER and PI lead, and a `LAB` subscription + founding
seat are provisioned (same path as a signup lab). Success `201` returns the new
membership in the `GET /api/auth/labs/` row shape. `400` if `name` is blank.

### `GET /api/auth/labs/<slug>/members/`

The roster of a lab the caller can access (any member may read). Success `200`:

```json
[
  { "username": "lena", "name": "Lena Reyes", "initials": "LR", "email": "l@uni.edu", "role": "owner", "is_lead": true }
]
```

Leads sort first. `403` for a non-member, `404` for an unknown slug.

## Lab invitations

A lab lead or owner/admin invites people; the invitee accepts, rejects, or
ignores. All require a session.

### `POST /api/auth/labs/<slug>/invitations/`

Invite by email or username: body `{ "identifier": "jsmith" | "jsmith@uni.edu",
"role": "member" }` (`role` optional, defaults to `member`). An email is matched
to an existing account when possible; an email with no account stays a **pending**
invite (`invitee` null) claimed when that person signs up. A username with no
account is a `400`. Also `400` if the target is already a member or already has a
pending invite. `403` for non-managers. Success `201` returns the invitation.

### `GET /api/auth/labs/<slug>/invitations/`

The lab's invitations (managers only). Success `200` — a list of
`{ id, lab_slug, role, status, invited_email, invited_username, invitee, inviter,
created_at, responded_at }`. `403` for non-managers.

### `GET /api/auth/invitations/`

The caller's **pending** invitations — the notifications-panel feed. Success
`200`:

```json
[
  { "id": "uuid", "lab_slug": "reyes-lab", "lab_name": "Reyes Lab", "role": "member", "inviter": "Lena Reyes", "created_at": "..." }
]
```

### `POST /api/auth/invitations/<id>/respond/`

The invitee answers: body `{ "action": "accept" | "reject" | "ignore" }`. Accept
creates the `LabMembership` (idempotent). Reject and ignore add no membership;
ignore silently dismisses it from the feed. Success `200`
`{ "id": "...", "status": "accepted" | "rejected" | "ignored" }`. `403` if the
invitation is not addressed to the caller; `409` if it was already answered.

### `GET /api/projects/?lab=<slug>`

Projects the caller may see under the lab/department visibility cascade
(`Project.objects.visible_to`). The optional `lab` query param narrows to one
lab's projects and never widens visibility. Success `200`:

```json
[
  {
    "id": "uuid", "name": "Drought study", "scope": "lab",
    "scope_name": "Reyes Lab", "goals": { "...": "..." },
    "status": "On track", "progress": 68, "member_count": 3,
    "members": [{ "username": "lena", "name": "Lena Reyes", "initials": "LR" }],
    "updated_at": "..."
  }
]
```

`scope` is `user | lab | department`. `status` and `progress` are read out of the
free-form `goals` JSON when an author set them, else `null` (the model has no such
columns). `401`/`403` when anonymous.

### `POST /api/projects/`

Create a project. Body `{ "name": "Oceanography", "lab": "reyes-lab",
"goals": { "...": "..." } }`. With `lab`, the project is scoped to that lab and
requires manage rights on it (owner/admin); without `lab`, it is a personal
project scoped to the caller. `goals` is optional. Success `201`. `400` for a
blank name; `403` when the caller cannot manage the named lab.

## Research & opportunities (personal workspace)

Base path: `/api/`. All require authentication; each returns the signed-in user's
own data only. Papers come from `GET /api/daily-report/` (the daily research
digest). Grants and conferences come from the daily 1am opportunity matching.

### `GET /api/search/`

Query-first search across the whole content corpus (papers, grants, fellowships,
conferences) — the digest retrieval pipeline run against a search box instead of
a profile. Requires authentication; reads the **global** corpus, so it is not
user-scoped. Query params:

- `q` — the search text. Blank returns an empty result (not an error).
- `type` — repeatable/comma (`paper|grant|fellowship|conference`); scopes results.
- `year` / `sponsor` / `award_class` / `country` — repeatable/comma **per-type
  facet filters**: papers by `year`, grants by `sponsor`, fellowships by
  `award_class`, conferences by `country`. Each matches its `metadata` value as
  text and so naturally scopes to its own type.
- `date_from` / `date_to` — ISO dates, filtering on ingest date.
- `sort` — `relevance` (default) | `date` (newest) | `deadline` (soonest, nulls last).
- `limit` — page size (bounded). `cursor` — opaque paging cursor from `next_cursor`.

Search **never abstains**: an in-corpus query always returns its best matches,
blending a lexical (full-text), a semantic (embedding), and a fuzzy (typo)
channel via reciprocal-rank fusion. `confidence` is `"low"` when the top semantic
match is weak — a display cue, never an empty page. Success `200`:

```json
{
  "query": "protein folding", "normalized": "protein folding",
  "sort": "relevance", "confidence": "ok",
  "count": 559, "pool_truncated": true,
  "facets": {
    "type": [{ "value": "paper", "count": 85 }, { "value": "grant", "count": 1 }],
    "year": [{ "value": "2026", "count": 80 }, { "value": "2025", "count": 5 }]
  },
  "limit": 20, "offset": 0, "next_cursor": "20",
  "results": [
    {
      "content_id": "uuid", "type": "paper",
      "title": "Generalizable Protein Folding Pathway Exploration",
      "summary": "…", "url": "https://…",
      "created_at": "2026-07-09T…", "score": 0.021,
      "matched_on": ["lexical", "semantic", "fuzzy"], "saved": false,
      "authors": ["…"], "venue": "Nature", "year": 2026,
      "sponsor": "", "amount": "", "location": "", "event_dates": "",
      "award_class": "", "deadline": ""
    }
  ]
}
```

`facets.type` is always present and its counts ignore the `type` filter (so the
UI can offer switching types). The **per-type facet** is contextual: it appears
under its own key (`year`/`sponsor`/`award_class`/`country`) **only when exactly
one `type` is selected**, is capped to its top values, and its own counts ignore
its own selection (so multi-select stays legible). `pool_truncated` is true when
more matches exist beyond the bounded relevance pool. Type-specific result fields
are populated per `type` and `""`/`[]`/`null` otherwise. `score` is the fused rank
weight (for ordering, not display).

### `GET /api/opportunities/grants/`

The user's ranked funding opportunities from the latest run, pinned-first (a
brand-new high-fit grant floats to the top for its first week). Success `200`:

```json
{
  "generated_at": "2026-07-05T01:00:00+00:00",
  "items": [
    {
      "content_id": "uuid", "title": "Amazon Agentic AI Award", "sponsor": "Amazon",
      "amount": "Upper: $70,000 USD", "matched_topics": "Agentic AI; Knowledge Graphs",
      "url": "https://...", "score": 1.19, "match_percent": 88, "rank": 1,
      "headline": "Strong Fit", "reason": "Aligns with your agentic AI work.",
      "origin": "llm", "is_new": true, "pinned": true,
      "deadline_date": "2026-11-12", "deadline_kind": "application",
      "status_summary": "Application due 2026-11-12", "saved": false
    }
  ]
}
```

`match_percent` is the model's 0–100 fit judgement (null on the fallback tail).
`is_new`/`pinned` hold while the one-week window is open. `saved` reflects whether
the user has saved the item to their deadlines. `generated_at` is `null` before
the first run.

### `GET /api/opportunities/conferences/`

Same shape for conferences (card format), with `location`, `country`,
`event_dates`, `deadlines`, and `keywords` instead of the grant fields.

### `POST /api/opportunities/save/`

Save a grant/conference to the user's deadlines. Body `{ "content_id": "uuid",
"note": "optional" }`. Snapshots the display + deadline fields so the saved
deadline survives the daily prune of expired items. Success `201` with the saved
deadline. `400` without `content_id`; `404` if it is not a grant/conference.

### `DELETE /api/opportunities/save/<content_id>/`

Remove the user's save for that item. `204` on success, `404` if not saved.

### `GET /api/deadlines/`

All the user's saved deadlines, soonest first. Success `200`:

```json
{
  "items": [
    {
      "id": "uuid", "content_id": "uuid", "area": "grant",
      "title": "Amazon Agentic AI Award", "url": "https://...", "subtitle": "Amazon",
      "deadline_date": "2026-11-12", "deadline_kind": "application", "note": "",
      "days_remaining": 5, "within_week": true
    }
  ]
}
```

`content_id` is `null` once the source item has been pruned (the snapshot
remains). `days_remaining`/`within_week` are relative to today.

### `GET /api/notifications/`

Deadline alerts for the header bell: saved items due within a week. Success `200`:

```json
{
  "count": 1,
  "items": [
    {
      "id": "uuid", "content_id": "uuid", "area": "grant", "title": "Amazon Award",
      "url": "https://...", "deadline_date": "2026-07-09", "days_remaining": 4,
      "message": "“Amazon Award” — less than a week left (4 days left)."
    }
  ]
}
```
