# Login System And Portal Plan

## Objective

Create the first working Mycelium login system and replace the current login
handoff with a proper authenticated portal. The initial milestone should let
the existing Django superuser sign in from the Next.js app, prove the session is
recognized, and route the user into the private workspace shell.

This plan keeps Django responsible for authentication, session validation,
permissions, admin access, and audit-relevant events. Next.js owns the login
experience and authenticated app routes. Astro remains the public site and only
links users into the app login route.

## Assumptions And Open Questions

- A Django superuser already exists and can be used for the first local sign-in
  test. This is only a smoke-test account, not the long-term product role model.
- The first implementation should use Django session authentication with CSRF
  protection because `web/backend/config/settings.py` already enables Django
  auth, sessions, and DRF session authentication.
- Local development will run the app on `localhost:3000` and Django on
  `localhost:8000`; production should route `/login`, `/app`, `/api`, and
  `/admin` through Nginx on one site origin.
- Lab membership, roles, object-level authorization, and audit logging are
  required before exposing real lab-scoped data. The first login milestone can
  show a placeholder authenticated workspace after verifying `request.user`.
- The repository currently has only `apps.core`; the implementation may add a
  dedicated Django app such as `apps.accounts` once auth endpoints outgrow the
  core app.
- Final invitation, password reset, email verification, SSO, MFA, and team
  onboarding flows are out of scope for the first milestone unless requested.

## Implementation Phases

### 1. Confirm Auth Boundary And Routing

- Keep public marketing and content routes in `web/landing`.
- Move the real login form to the Next.js authenticated app at `web/app`.
- Add or reserve these app routes:
  - `/login` for the sign-in portal.
  - `/app` for the authenticated workspace landing or redirect.
  - `/app/[labSlug]/dashboard` for the later lab-aware route shape.
- Update the Astro `/login` page in `web/landing/src/pages/login.astro` so it
  sends users to the Next.js `/login` portal instead of presenting itself as the
  login experience.
- Ensure Nginx routing later maps:
  - public pages to Astro,
  - `/login` and `/app/*` to Next.js,
  - `/api/*` and `/admin/*` to Django.

### 2. Add Django Session Auth Endpoints

Create a small, explicit API surface for the Next.js app:

- `GET /api/auth/csrf/`
  - Ensures a CSRF cookie is available before form submission.
- `POST /api/auth/login/`
  - Accepts username and password.
  - Uses Django's built-in `authenticate()` and `login()`.
  - Returns the authenticated user's basic profile and permission flags.
  - Returns structured validation errors without leaking whether a username
    exists.
- `POST /api/auth/logout/`
  - Uses Django's built-in `logout()`.
  - Requires CSRF protection.
- `GET /api/auth/me/`
  - Returns the current authenticated user when the session is valid.
  - Returns `401` for anonymous requests.

Implementation should prefer Django and DRF primitives over custom credential
handling. If these endpoints live in a new `apps.accounts` app, register that
app in `INSTALLED_APPS` and include its URLs under `/api/auth/`.

### 3. Configure Local Session And CSRF Behavior

- Allow credentialed local requests from the Next.js app:
  - keep `DJANGO_CORS_ALLOWED_ORIGINS` aligned with `http://localhost:3000`;
  - add credential support if direct browser requests to Django are used;
  - configure `CSRF_TRUSTED_ORIGINS` for local app origins.
- Keep session cookies HTTP-only.
- Use secure cookie settings in non-debug deployments.
- Avoid storing passwords, session IDs, or tokens in browser local storage.
- Keep the long-term production target as same-origin routing through Nginx to
  reduce cross-origin session complexity.

### 4. Build The Next.js Login Portal

Add the primary portal in `web/app/src/app/login/page.tsx` with a client form
component if needed.

The page should feel like a real Mycelium app entry point:

- Warm botanical app styling from `docs/styles.md`.
- Clear Mycelium brand lockup and concise sign-in copy.
- Username and password fields with labels, autocomplete attributes, visible
  focus states, and inline validation.
- Submit button with loading, disabled, success, and error states.
- Non-blocking links back to the public site and future account help.
- A restrained Mylo or research-network visual accent only if it supports the
  login task.
- Responsive layout that works cleanly on phone, tablet, and desktop.
- No private lab data or fake personalized content before authentication.

The form should:

- fetch `/api/auth/csrf/` before submitting credentials;
- post credentials to `/api/auth/login/` with `credentials: "include"`;
- handle `400`, `401`, `403`, and network errors distinctly;
- redirect authenticated users to `/app` after successful sign-in.

### 5. Protect The Workspace Shell

- Add an app-level auth utility in `web/app/src/lib/` for `getCurrentUser()`,
  login, logout, and response normalization.
- Gate `/app` and future authenticated routes by checking `/api/auth/me/`.
- Redirect anonymous users to `/login`.
- Show an authenticated placeholder workspace for the first milestone that
  confirms the signed-in user without exposing lab data.
- Add logout affordance in the workspace shell once login works.
- Plan the next milestone to introduce account, lab, membership, and role
  models before replacing placeholder workspace content with lab-scoped data.

### 6. Add Lab And Permission Foundations Before Real Data

Before any private lab objects appear in the workspace, add:

- durable account profile fields only if Django's built-in user model is not
  sufficient for display and ownership needs;
- lab model;
- membership model with role;
- object-level permission helpers;
- audit event model or service for sensitive actions;
- admin registration for accounts, labs, and memberships;
- tests proving users cannot access labs or objects they do not belong to.

This phase can follow the superuser smoke test, but it should come before
research feeds, papers, grants, fellowships, reports, or graph data become real.

## Public Interfaces And Files Expected To Change

- `web/backend/apps/accounts/` or `web/backend/apps/core/` for auth API views,
  serializers or forms, URLs, and tests.
- `web/backend/config/settings.py` for CORS, CSRF, cookie, and installed app
  settings.
- `web/backend/config/urls.py` for `/api/auth/` routing.
- `web/app/src/app/login/page.tsx` for the login portal.
- `web/app/src/app/app/page.tsx` and later nested app routes for authenticated
  workspace gating.
- `web/app/src/lib/auth.ts` or similar for frontend auth calls.
- `web/landing/src/pages/login.astro` for public-to-app handoff copy and link.
- `web/infra/nginx/default.conf` when production-like routing is wired.
- `docs/api-contract.md` if the auth payload shape becomes a committed frontend
  contract.

## Data Flow

1. Visitor opens public `/login` on Astro.
2. Astro links to the Next.js `/login` portal.
3. Next.js login page requests a CSRF cookie from Django.
4. User submits username and password.
5. Django authenticates credentials, creates the session, and returns the
   current user summary.
6. Next.js redirects to `/app`.
7. `/app` checks `/api/auth/me/`.
8. Authenticated users see the workspace shell; anonymous users return to
   `/login`.
9. Later lab routes check membership, role, object-level permission, and audit
   requirements before returning lab-scoped records.

## Validation And Acceptance Criteria

- `npm run dev` from the repository root starts landing, app, and backend
  development services.
- `uv run --project web/backend python web/backend/manage.py check` passes.
- `uv run --project web/backend pytest web/backend` passes once tests exist.
- `npm --prefix web run lint` passes.
- `npm --prefix web run build` passes.
- A local superuser can sign in through `http://localhost:3000/login`.
- Bad credentials show a clear inline error and do not create a session.
- Refreshing `/app` after login preserves the authenticated state.
- Logging out clears the session and redirects back to `/login`.
- Anonymous requests to `/api/auth/me/` return `401`.
- Anonymous users cannot access `/app`.
- The login form is usable by keyboard, has visible focus states, has labeled
  fields, avoids horizontal overflow on mobile, and meets WCAG 2.2 AA contrast
  expectations.
- No private lab data appears until lab membership and permission checks exist.

## Explicit Exclusions

- No custom password hashing or custom credential store.
- No token storage in local storage.
- No SSO, MFA, password reset, invitation, or email verification flow in the
  first milestone.
- No real lab-scoped research data in the workspace before membership,
  object-level authorization, and audit foundations exist.
- No replacement of Django admin login unless a later plan explicitly covers
  admin UX.
