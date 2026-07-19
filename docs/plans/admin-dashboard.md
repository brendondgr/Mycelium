# Admin account creation & admin dashboard

Standalone admin bootstrap plus an in-app, staff/superuser-only dashboard for
managing users, their subscription tier + duration, and their watch quota.

## Objective

1. A standalone command to mint (or promote) a superuser admin, with the password
   read only from `.env` (`ADMIN_USER_PASS`), runnable outside the web process.
2. An admin dashboard under **Research → Personal Workspace → Admin**, visible only
   to platform admins, to view all users (paginated), see/assign subscriptions with
   a specific duration, and grant a per-user watch-parameter limit.

Backend and its permission gate landed and were proven **before** the UI.

## Decisions

- **Access = `is_staff` OR `is_superuser`.** `create_admin` grants both. The gate
  is `IsStaffOrSuperuser`; the frontend nav gate is only a rendering hint.
- **Subscription duration = `Subscription.expires_at`,** enforced at read-time in
  `billing/entitlements.py` (`_unexpired`): an active-but-expired plan is treated
  as absent, so a timed grant reverts to Free on its own — no cleanup job, no data
  deletion (mirrors the existing no-data-loss downgrade behaviour).
- **Watch parameter = `Profile.watch_topic_limit`** (nullable; null = tier cap),
  read through `entitlements.topic_cap` so every consumer (watch-save serializer,
  `effective_watch_topics`, cluster seeding) honours it uniformly.
- **Admin actions target a user's personal (`scope_user`) subscription.** Lab and
  department plans are out of scope for the per-user action.
- **Admin API is its own app, `apps.adminpanel`,** composing `accounts` + `billing`
  so admin logic stays out of the per-user CRUD views.

## What shipped

### Backend

- `billing/models.py`: `Subscription.expires_at` + `is_current()`; migration
  `billing/0004`.
- `billing/entitlements.py`: `_unexpired()` applied to `covering_subscriptions`,
  `_lab_subscriptions`, `users_with_feature`; `watch_topic_override` + `topic_cap`
  honouring `Profile.watch_topic_limit`.
- `accounts/models.py`: `Profile.watch_topic_limit`; migration `accounts/0018`.
- `accounts/management/commands/create_admin.py`: create/promote a staff+superuser
  from `ADMIN_USER_PASS`, seed minimal interests (skip onboarding), ensure a
  personal workspace, audit — idempotent. Root wrapper `create_admin.py` runs it in
  the backend container (real Postgres + env).
- `apps/adminpanel/`: `IsStaffOrSuperuser`, page-number pagination (25/max 100),
  serializers, `services.py` (`assign_subscription`, `set_watch_limit`, both audit),
  `views.py` (`GET /api/admin/users/` paginated + `?q=`, `GET`/`PATCH
  /api/admin/users/<id>/`). Registered in `INSTALLED_APPS` + `config/urls.py`.

### Frontend

- Route `app/(workspace)/admin/page.tsx` → `sections/admin-section.tsx`: a
  paginated, searchable user table with a per-user editor (tier, duration, status,
  watch limit) covering loading / empty / error / permission-denied / mobile states.
- `routes.ts` (`admin` section), data layer in `lib/portal/{client,hooks,mutations,
  types}.ts`, `isStaff` threaded onto `PortalUser` (`portal-context.tsx` +
  workspace `layout.tsx`), and an Admin nav entry in the sidebar + mobile nav gated
  on `!inLab && (isStaff || isSuperuser)`.

## Security

- Every admin endpoint is gated by `IsStaffOrSuperuser`; non-admins get `403`.
- All admin writes record an `accounts.AuditEvent` naming the acting admin.
- The password is read only from `ADMIN_USER_PASS`, never a CLI argument, never
  logged.
- Expiry is read-time enforced, so stale entitlements can't linger; nothing is
  deleted on expiry or downgrade.

## Validation

- Backend: full suite green (`apps.adminpanel`, `apps.billing`, `apps.accounts`
  targeted first), `makemigrations --check` clean, `ruff` clean.
- Frontend: `tsc --noEmit`, ESLint, and `next build` all clean; `/app/admin`
  registered as a dynamic route.

## Out of scope

Lab/department subscription assignment via this dashboard, Stripe/real billing,
user enable/disable & hard-delete, editing another user's watch topic *content*
(only the numeric cap), and any scheduled expiry job (handled at read-time).
