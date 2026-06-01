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

### `POST /api/auth/logout/`

Success `204` with empty body. Requires CSRF header when using session auth.

### `GET /api/auth/me/`

Success `200` — same user summary as login.

`401` with empty body when anonymous.
