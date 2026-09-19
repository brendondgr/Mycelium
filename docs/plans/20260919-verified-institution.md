# Plan: an institution is proved by email, and only a proved one finds people

Working document — delete once shipped (see `docs/skills/planner.md`).

## Objective

1. **A claim of institution or location must be backed by the sign-up email.**
   A person is "at" an institution only when the address they verified belongs
   to it (its domain resolves in the affiliation directory). Nobody can type an
   institution they cannot receive mail at.
2. **People suggestions need a verified account at an institution.** Only a
   person whose email has been confirmed working, *and* resolves to an
   institution, can be shown other people — and only people from that same
   institution or, at widest, the same country.

## What exists (why this is smaller than it sounds)

- `apps/collab` (plans CN-01..08) already derives a `VerifiedAffiliation`
  (domain, institution, country) from a **verified** email
  (`apps/collab/affiliation.py`), never from typed text, and the matcher refuses
  an unverified seeker (`matcher.check_seeker`). Candidates are scoped by
  `consent.mutually_visible` on verified affiliations only.
- The gaps:
  - **G1 — typed institution.** `Profile.institution` is free text written by
    `PATCH /api/auth/account/` and `PATCH /api/auth/profile/me/` (picker in
    onboarding, profile editor, account page). `Department.institution` is typed
    in `POST /api/auth/departments/`. `provision_from_author` copies an
    imported draft's institution onto an account whose email is fake.
  - **G2 — typed institution is trusted downstream.** Fellowship eligibility
    (`apps/content/fellowships.eligibility_from_profile`) takes
    `interests.eligibility.university` / `is_illinois_student` or the free text
    as a *hard* gate; ranking and report prompts read `profile.institution` as
    fact (`targets.py`, `typesafe_rerank.py`, `opportunity_llm.py`,
    `opportunities.py`).
  - **G3 — a verified personal address can search.** `place_of` returns a
    `Place(domain="")` for a verified gmail account, so `check_seeker` passes
    and the search runs, just empty. The rule says: no institution, no people.
    Likewise `allowed_audiences` offers such a person "anywhere".
  - **G4 — scope can widen past "same location".** `COLLAB_MAX_SCOPE` may be set
    to `anywhere`, and the saved-people view filters with
    `eligible_candidates(user, "anywhere")`.
  - **G5 — derivation is lazy.** `affiliation.refresh` only runs on collab
    reads; nothing re-derives at the moment an address is verified.

Surfaces that name other people but are **not** suggestions and stay as they
are: the lab's team-fit line (lab-mates, by design principle 10), lab/department
rosters, and invite-by-exact-username (no discovery happens).

## Decisions and assumptions

- **Location means country.** Mycelium has no typed location field; the only
  location is the country the verified institution sits in. Any future location
  field follows this plan's rule.
- **Institution is derived, never typed.** `Profile.institution` becomes a
  server-written mirror of `VerifiedAffiliation.institution`: set when an
  address is verified, cleared when there is none. A write of a *different*
  value is refused (400, `code: "institution_from_email"`) with the fix spelled
  out ("change your email to an address at …"); resending the current value is a
  harmless no-op so an older client does not break.
- **Unverified means no institution yet.** Before the code is entered the account
  shows what the address *would* resolve to (`institution_from_email`) but holds
  no institution. An email-invite sign-up is verified at registration (existing
  behaviour) and gets its institution then.
- **The directory is the authority.** `web/app/public/data/institutions.json`
  (~10.3k domains). An address at an institute missing from it is treated like a
  personal address; the remedy is adding the domain via
  `web/scripts/data/research-institutions.json`, not a free-text escape hatch.
- **Seekers never reach past their country.** A hard ceiling of `country` in the
  matcher, whatever `COLLAB_MAX_SCOPE` says. A candidate's audience choice
  "anywhere" remains (it only says who they *allow*); the seeker's side is what
  enforces "same location".
- **A department's institution is its creator's verified institution.** Typed
  values that differ are refused. Existing department rows are left as they are
  (their creators were already required to be verified).
- **Existing profiles are re-derived once**, in a data migration. Every changed
  value is written to the audit log (`before`/`after`) so nothing is lost
  silently. Staff and seeded accounts with non-deliverable addresses lose their
  typed institution; that is the rule working.
- **Coupling.** `accounts` must not import `collab`. Accounts sends an
  `email_verified` signal; collab's `ready()` connects `affiliation.refresh`,
  which remains the one derivation point and now also writes the mirror.
- **Entitlements.** Unchanged: search stays behind its existing paid-plan check
  in `check_seeker` (read through `billing.entitlements`).

## Phases

Each phase ends green on its validation command, then one commit (no push).

### Phase 1 — derive institution from the verified email (backend, G1 G5)

What / how:
- `apps/accounts/signals.py`: add `email_verified = Signal()`; send it at the end
  of `email_verification.verify()` (after the transaction commits, via
  `transaction.on_commit`) and in `register_view` when an email invite verifies
  the account.
- `apps/collab/affiliation.py`: `refresh(user)` also sets
  `profile.institution` to the derived name (or `""`), saving only that column.
  Add `institution_for(user)` (the verified name, no write) and keep
  `resolve_email` as the one resolver. `apps/collab/apps.py` connects the signal.
- `apps/accounts/serializers.py` / `views.py`:
  - `ProfileSerializer`: `institution` read-only.
  - `AccountView.patch`: refuse a differing `institution` with 400 and
    `code: "institution_from_email"`; accept an equal one as a no-op.
  - `_account_payload` and `user_to_dict`/profile payload: add
    `institution_verified` (bool) and `institution_from_email` (what the current
    address resolves to, even unverified; `""` for none).
  - `MyDepartmentsView.post`: department institution = creator's verified
    institution; a differing typed value is refused the same way.
- `apps/accounts/provisioning.py`: stop copying `draft.institution`.
- Intake synthesis (`SynthesizeView` path): overwrite the client draft's
  `institution` with the account's verified one before any prompt reads it.
- Data migration `accounts/0029_institution_from_email`: re-derive every
  profile through a plain function in `apps/accounts/institution.py`
  (`rederive_all()`, also used by tests), writing an audit event per changed
  profile.

Why: closes the claim path at the server — the UI change in Phase 3 is
convenience, the API refusal is the rule.

Tests (`apps/accounts/tests/test_institution_from_email.py`): verifying a
signup code sets the institution; a personal address leaves it empty; unverified
holds none; an email change re-derives on verification of the new address; an
email-invite sign-up has it at once; a differing PATCH is refused and an equal
one accepted; profile PATCH cannot write it; department create takes the
creator's; provisioning leaves it empty; `rederive_all` rewrites and audits.
Update existing tests that PATCH a typed institution
(`test_account_api.py`, `test_profile_api.py`, `test_department_create.py`,
`test_provision_from_author.py`).

Validate: `uv run --project web/backend pytest web/backend/apps/accounts web/backend/apps/collab -q`
(isolated `DATABASE_URL` database name if another session is running tests).

### Phase 2 — people suggestions need a verified institution, same location only (backend, G2 G3 G4)

What / how:
- `apps/collab/consent.py`: `allowed_audiences` returns `[]` for a place with no
  domain; `update` refuses with "use your institution's email to be found".
- `apps/collab/matcher.py`:
  - `check_seeker`: after the unverified check, refuse a place with no domain —
    `SearchRefused("use your institution's email to find people", "no_institution")`.
  - `_allowed_scope`: `SEEKER_SCOPE_CEILING = Audience.COUNTRY`; `anywhere` is
    refused regardless of `COLLAB_MAX_SCOPE`.
  - `eligible_candidates`: return `[]` for a seeker without a domain (the saved
    and introduction paths inherit it).
- `apps/collab/views.py`: saved-people view filters with the ceiling, not
  `"anywhere"`; `search_availability` reports `max_scope` clamped to the ceiling.
- `apps/collab/evaluation.py`: readiness never proposes widening past the ceiling.
- `apps/content/fellowships.py`: `eligibility_from_profile` reads only the
  verified institution; `interests.eligibility.university` and
  `is_illinois_student` are ignored (the UI never writes them; the API could).

Why: the suggestion gate already exists; these close the personal-address hole
and pin "same location" in code rather than in a setting.

Tests: extend `apps/collab/tests/test_matcher.py` (verified personal address is
refused `no_institution`; `anywhere` refused even with
`COLLAB_MAX_SCOPE="anywhere"`; saved people empty without a domain),
`test_consent.py` (personal address → no audiences; update refused),
`test_api.py` (availability code), `test_evaluation.py`, and
`apps/content/tests/test_fellowships.py` (typed `university` ignored).

Validate: `uv run --project web/backend pytest web/backend/apps/collab web/backend/apps/content/tests/test_fellowships.py web/backend/apps/content/tests/test_fellowships_api.py -q`

### Phase 3 — the app shows the institution, it does not ask for it (frontend)

What / how:
- `web/app/src/lib/auth-types.ts` (+ `auth-client.ts` payload types): the new
  `institution_verified` / `institution_from_email` fields.
- New `web/app/src/components/ui/institution-from-email.tsx`: read-only line —
  verified: "Florida State University · from your verified email"; unverified
  but resolvable: "Florida State University, once you confirm your email";
  personal address: "No institution — your email isn't at one we recognise. Use
  your institution's address to list it and to find people there."
- Replace `InstitutionPicker` in onboarding step 1, `profile-editor-modal.tsx`,
  `account-section.tsx`, and `CreateDepartmentModal`; stop sending
  `institution` in their PATCH/POST bodies. Delete `institution-picker.tsx` once
  nothing mounts it; keep `lib/institutions.ts` if the sign-up hint uses it.
- `components/auth/signup-form.tsx`: a hint under the email field (directory
  fetched lazily on blur): which institution the address resolves to, or that a
  personal address cannot list an institution or find people.
- `collaboration-settings-card.tsx` and `find-collaborators.tsx` /
  `search-panel.tsx`: copy for the new `no_institution` refusal and the empty
  audience list.
- States: loading, verified, unverified, personal address, error; mobile and
  keyboard per `docs/skills/ui-frontend.md`.

Why: a field that looks editable but is refused is worse than no field.

Validate: from the repo root, the web lint + typecheck scripts (see
`package.json`), plus the running app via the `run` skill if the stack is up.

### Phase 4 — documentation and close-out

- `docs/api-contract.md`: account/profile `institution` read-only + new fields,
  the `institution_from_email` refusal, department create, `no_institution`.
- `docs/goals.md` (Collaboration paragraph), `docs/architecture.md` (where an
  institution comes from), `docs/plans/collaboration-network/design.md` §7 (the
  country ceiling replaces "widen to anywhere"), `docs/repo-map.md` (new module,
  picker removed, new component).
- `docs/changelog.md` entry; delete this plan.

Validate: `make validate-research` (unchanged, but cheap) and link check by eye.

## Explicit exclusions

- Proving membership other than by email (ORCID affiliation, SSO/SAML).
- Re-deriving existing `Department.institution` rows.
- The Illinois substring match's own imprecision (any "Illinois" institution).
- The team-fit line, rosters and invite-by-username (not suggestions).
- Admin-edited emails (Django admin) — collab re-derives on its next read; the
  profile mirror catches up on the next verification.
