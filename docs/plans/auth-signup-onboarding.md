# Auth — Sign-Up & Onboarding Buildout

**Status:** Complete — backend service + registration endpoint + hardening scaffold and the
signup/onboarding frontend are built, validated (239 backend tests, lint, build all green), and
committed. Smoke checklist verified via integration tests (CSRF, register per account type,
duplicate-email atomicity, session set, onboarding profile PATCH); seed_demo unaffected
(not refactored to use the service this sprint — left as a deliberate, low-risk follow-up).
**Scope:** Add user registration (Personal / Lab / Department), a `/signup` page, and the
onboarding intake UI on top of the existing session-auth layer (login/logout/me already built).
**Design source:** `Mycelium Auth Flow.dc.html` (login → signup → verify email → 5-step intake →
"weaving graph" loading → dashboard).
**Backend reference:** `3.Mycelium_Auth_Signup_Buildout_Plan.md`.

This plan is grounded against the current codebase (verified by exploration), not the assumptions
in the reference markdown. Differences from that markdown are called out inline.

---

## 1. Objective

A visitor can create an account and a starting workspace in one flow, then land in onboarding that
seeds their research profile. Registration is two-phase and atomic:

1. **Identity** — create `User` (+ auto `Profile` via post_save signal).
2. **Provision workspace** — Personal / Lab / Department branch, each creating a `Subscription` +
   founding `Seat` (and org rows for lab/department), via one service.

After register, the session is live and the user is routed into onboarding.

---

## 2. Grounded facts (verified against code)

- **`accounts/services.py` already exists** with `record_audit_event(...)` — use it instead of raw
  `AuditEvent.objects.create` (reference markdown predates it).
- **`billing/` has `entitlements.py`** (with `PI_CAPS`) but **no `services.py`** → create it there.
- **`Tier`** = `free` / `spore` / `lab` / `canopy`. **`Lab.slug`** is `SlugField(max_length=80, unique=True)`.
- **`Department.owner`** is `on_delete=PROTECT`. **`LabMembership`** has `role` + `is_lead`.
- **Subscription** check constraint `billing_subscription_one_scope`; **Seat** `billing_seat_one_payer`
  + unique `billing_unique_seat_member`.
- **`Profile` has no `is_verified` field** → Phase 3 adds it (migration).
- **Intake endpoints already exist & are tested**: `POST /api/auth/intake/{import,session,confirm}/`.
  `ConfirmIntakeView` validates `interests` against the contract and saves `profile.interests`.
- **Interests contract** (`accounts/interests.py`): `areas` required (`list[str]`); also `statement`,
  `methods`, `keywords`, `skills`, `funding_needs`, `eligibility`, `seeking`, `exclusions`, `sources`.
  **Unknown fields are rejected** → onboarding may only send contract fields.
- **`MyProfileView`** (`/api/auth/profile/me/`, RetrieveUpdate) edits `academic_title`, `institution`,
  `interests`, external ids on the caller's own profile.
- **Frontend** uses Tailwind + CSS variables from `web/packages/config/src/theme.css` and the **Geist**
  font (not the mockup's raw hex / Fraunces / Inter). Login lives at `web/app/src/app/login/page.tsx`
  (server page, gates via `getCurrentUser()`) + `web/app/src/components/auth/login-form.tsx` (client).
- **Top-level routing** is gated in **two** places that must stay in sync:
  `web/scripts/dev-gateway.mjs` and `web/infra/nginx/default.conf`. `/app/*` already routes to the app;
  `/signup` is new and must be added to both. Onboarding lives under `/app/onboarding` (already routed).
- **Commands:** tests `uv run --project web/backend pytest web/backend`; lint `npm run lint`
  (web eslint + backend ruff); app build/typecheck `npm --workspace @mycelium/app run build`.

---

## 3. Decisions & assumptions

| ID | Decision |
|---|---|
| D1 | Personal default tier = `FREE` (markdown D1). |
| D2 | Username explicit (login is username-based). |
| D3 | One workspace per signup. |
| D4 | `academic_title` captured in onboarding, not the signup form (`Profile` defaults to RESEARCHER). |
| D5 | Email verification **non-blocking** this sprint: user is logged in immediately; verify screen is skippable. |
| A1 | **Visual system:** mirror the existing login page's token/Tailwind/Geist conventions; take *UX* (account-type cards, conditional fields, multi-step intake, Mylo SVG, loading animation) from the mockup. Do not hardcode mockup hex or add new fonts. |
| A2 | **Onboarding persistence:** `academic_title` + `institution` via `PUT /api/auth/profile/me/`; research `interests` (areas/statement/keywords) via `POST /api/auth/intake/confirm/` (guaranteed contract validation). |
| A3 | **Goals / alert toggles / cadence** have no backend model → collected in the UI as a clearly-labelled scaffold, **not persisted** this sprint (no fake fields written). |
| A4 | **Verify email** is scaffold per markdown Phase 6: `is_verified` flag + a stub endpoint + console email backend in dev. No real token signing / templates / SMTP. |

---

## 4. Phased plan (each phase: implement → validate → commit; no push)

Commits use concise, human-authored messages with **no AI attribution / co-author trailers**
(per `docs/skills/global.md`). Changelog updated as part of the relevant phase.

### Phase 0 — Baseline
- Read the two local-validation memories. Determine the working test DB (Profile uses a pgvector
  `VectorField`).
- Run existing backend tests + app lint/build to confirm a green starting point.
- **Validate:** suite green, lint clean. (No commit — read-only.)

### Phase 1 (B1) — `provision_workspace()` service  *(keystone)*
- **New:** `web/backend/apps/billing/services.py` — `ACCOUNT_TYPES`, `ProvisionResult`,
  `provision_workspace(user, account_type, *, org_name, institution, personal_tier=Tier.FREE)`,
  `_unique_lab_slug`. `@transaction.atomic`. Personal/Lab/Department branches per the provisioning map.
- **New tests:** `web/backend/apps/billing/tests/test_services.py` — one per account type (rows, roles,
  tiers, payers), slug uniqueness on duplicate lab names, personal creates no org rows, bad type raises.
- **Validate:** `pytest .../billing/tests/test_services.py` green; `makemigrations --check` clean.
- **Commit.**

### Phase 2 (B2) — Registration serializer + endpoint
- **Edit** `accounts/serializers.py` — `RegisterSerializer` (username/email uniqueness, password match
  + `validate_password`, org_name required for lab/department).
- **Edit** `accounts/views.py` — `register_view` (AllowAny): create user → `provision_workspace` →
  `record_audit_event` → `login(request, user)` → 201 `user_to_dict`. Wrap in `transaction.atomic`.
- **Edit** `accounts/urls.py` — `register/` + `register` (slash/no-slash, matching convention).
- **Edit** `docs/api-contract.md` — add `POST /api/auth/register/`.
- **New tests** in `accounts/tests/test_auth.py`: personal/lab/department success, duplicate email 400,
  password mismatch 400, weak password 400, lab without org_name 400, session set (me returns user),
  atomicity (no orphan user on mid-provision failure).
- **Validate:** auth + billing tests green; `makemigrations --check` clean.
- **Commit.**

### Phase 3 (B3) — Hardening scaffold
- `Profile.is_verified = BooleanField(default=False)` + migration (depends correctly on prior accounts
  migration; pgvector ordering rule noted in memory).
- `verify_email_view` stub at `/api/auth/verify-email/` (+ no-slash): flips flag for the logged-in user
  (token signing deferred); document as scaffold.
- Registration throttle: `ScopedRateThrottle`/`AnonRateThrottle` subclass on `register_view`;
  configure `DEFAULT_THROTTLE_RATES` in settings.
- Reserved-name guard in `validate_username` (`login`, `signup`, `app`, `api`, `admin`, …).
- `EMAIL_BACKEND = console` for dev.
- **Tests:** reserved-name 400; verify-email flips flag; (throttle test if cheap).
- **Validate:** suite green; `makemigrations --check` clean; migrate runs.
- **Commit.**

### Phase 4 (F1) — `register()` client
- **Edit** `web/app/src/lib/auth-client.ts` — `register(input)` mirroring `login()`; add
  `AccountType` + `RegisterInput` types (in `auth-types.ts`). Surface first DRF field error.
- **Validate:** app lint + typecheck. (Commit with Phase 5.)

### Phase 5 (F2) — `/signup` page + routing
- **New:** `web/app/src/app/signup/page.tsx` (server page; gate via `getCurrentUser()` → `/app`) +
  `web/app/src/components/auth/signup-form.tsx` (client): account-type cards (Personal/Lab/Department),
  conditional org-name + institution fields, shared identity fields, client validation mirroring the
  serializer, error handling, `register()` → redirect `/app/onboarding`.
- Cross-links: "Create an account" on login, "Sign in" on signup.
- A small shared Mylo mark + brand panel as a presentational component, token-based.
- **Routing:** add `/signup` to `web/scripts/dev-gateway.mjs` and `web/infra/nginx/default.conf`;
  update the single-origin table in `docs/architecture.md`.
- **Validate:** app lint + build (typecheck); manual route check if a dev server is available.
- **Commit.**

### Phase 6 (F3) — Onboarding intake UI
- **New:** `web/app/src/app/app/onboarding/page.tsx` (server gate → `/login` if anon) +
  `web/app/src/components/onboarding/onboarding-flow.tsx` (client state machine):
  verify-email (skippable scaffold) → 5 steps (role+institution, areas, goals[scaffold], focus+keywords,
  alerts+cadence[scaffold]) → "weaving" loading → `/app`.
- Submit: profile PUT (title/institution) + intake confirm (interests). Block "continue" until areas
  chosen (areas required by contract).
- Ensure register redirect target is `/app/onboarding`.
- **Validate:** app lint + build; manual walkthrough if dev server available.
- **Commit.**

### Phase 7 — Docs, goals, changelog, smoke
- Update `docs/goals.md` (Week 6 minimal Next.js input surface), `docs/changelog.md` (entries per
  schema, one per change set), api-contract finalization.
- Run **full** backend suite + app lint + build. Walk the smoke checklist.
- **Commit** any remaining doc/changelog updates.

### Phase 8 — Merge to main
- Merge `claude/distracted-davinci-f71144` → `main`, resolve conflicts, re-run suite + lint/build.
- **No push.**

---

## 5. Acceptance criteria
- `POST /api/auth/register/` returns 201, sets session; `me` returns the new user; correct
  Subscription/Seat (+ org rows) per account type; duplicate email & mismatched/weak password & missing
  org name return 400; registration is atomic (no orphan user).
- `/signup` renders, validates, registers, and lands the user in `/app/onboarding`; `/signup` is routed
  by both gateway and nginx; cross-links work.
- Onboarding persists role/institution/interests and lands the user in `/app`.
- Full backend suite green; app lint + build clean. Branch merged to main, still green.

## 6. Exclusions
Real SMTP / token-signed email verification; password reset; OAuth; Stripe capture; team invites;
persisting goals/alert/cadence preferences (no model yet).
