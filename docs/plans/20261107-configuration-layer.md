# Configuration layer for self-hosting

Working plan, opened 2026-11-07. Delete it once the work ships and record the
outcome in `docs/changelog.md`, `docs/architecture.md` and a new
`docs/configuration.md`.

## Objective

Someone who clones Mycelium should never hit a limit they cannot explain or
change. Every policy (what a person, lab or department may do) and every cost
control (how much model and compute the nightly run spends) is set in one
readable file, from a deployment profile that fits who the instance serves,
through a CLI or the user's own agent — not by editing Python.

## Decisions (locked 2026-11-07)

1. **Billing stays, dormant.** `billing.mode = "off"` (the default) means no
   tiers: everyone gets the configured limits, labs and departments are created
   active, and plan / seat / upgrade UI is hidden. `"subscriptions"` restores
   today's tiered behaviour for an operator who wants to sell seats.
2. **One file: `mycelium.toml`** at the repo root, commented and grouped by
   section. Precedence: built-in defaults < profile < `mycelium.toml` < env
   vars. Secrets stay in `.env`.
3. **In-app edits are per-object overrides only.** The staff admin page keeps
   (and gains) per-user / per-lab / per-department overrides on top of the file.
   No instance-wide settings editor in the UI.
4. **Default profile is `lab`** when setup runs without one.

## Audit (Phase 0)

### What actually restricts a self-hoster today

`BILLING_ENFORCE_ENTITLEMENTS` is already off, so no *feature* is withheld. The
restrictions that remain:

1. **Per-user caps follow the user's real plan, not the switch.**
   `effective_tier()` reads actual subscriptions, and the cluster, topic and
   personal-project caps key on it. The switch never touches them.
2. **The first admin is on Free.** `create_admin` calls
   `provision_workspace(user, "personal")`, whose `personal_tier` defaults to
   Free. Only sign-up applies `SIGNUP_GRANT_TIER`. So the operator who just ran
   `make setup` gets 3 clusters × 2 topics, 6 watch topics and 2 personal
   projects — the tightest box in the system.
3. **Lab membership does not lift a member's caps.** Labs and departments are
   created with an INACTIVE plan. While gating is off the *lab* has every
   feature (so lab projects work), but nobody is seated, so each member keeps
   their personal tier's caps. Activating the plan is a staff/admin step.
4. **Ambient listening is tier-gated regardless of the switch**
   (`ambient.eligibility` → `ambient_enabled(effective_tier)`, by design). A
   Free account — including the first admin — can never be listened to.
5. **Sign-up needs an access code**, with a hardcoded fallback (`251253`) in
   `settings.py` that is public in an open-source repo. `make setup` writes a
   generated one, but an instance started without setup accepts the known code.
   Three misses = a one-hour shadow ban, failing closed if Redis is down.
6. **Creating a lab or department, or inviting, needs a verified email** (staff
   exempt). `EMAIL_ENABLED` is off by default, so the code only appears in the
   container logs — invisible to a non-technical operator.
7. **~250 env vars in one 1,400-line `settings.py`**, a 549-line
   `.env.example`, no grouping, no validation, no way to see what is in effect.
   `make setup` asks only for the model endpoint.

### Policy limits (who may do what)

| Limit | Where | Free | Spore | Lab | Canopy | Enforced at |
| --- | --- | --- | --- | --- | --- | --- |
| Interest clusters | `CLUSTER_CAPS` | 3 | 6 | 6 | 6 | cluster organizer, profile save, ambient deliberation, `/api/billing/me/` |
| Topics per cluster | `CLUSTER_TOPIC_CAPS` | 2 | 10 | 15 | 15 | same |
| Watch topics (flat) | `TOPIC_CAPS` (+ per-user admin override) | 6 | 20 | 15 | 15 | profile save, both daily pipelines (`effective_watch_topics` truncates) |
| Personal projects | `PERSONAL_PROJECT_CAPS` | 2 | 5 | 5 | 5 | project create/unarchive, nightly fan-out (`in_cap_ids`) |
| Lab projects | `LAB_PROJECT_CAP` | 10 if lab has `TEAM_WORKSPACE`, else 0 | | | | same |
| Department projects | `DEPARTMENT_PROJECT_CAP` | 30 if dept has `DEPARTMENT_ROUTING`, else 0 | | | | same |
| Seats per plan | `TIER_MEMBER_CAPS` | 1 | 1 | 15 | ∞ | seat creation — only once a plan is ACTIVE; refuses invite-accept / member-add |
| PIs per lab | `PI_CAPS` | 1 | 1 | 5 | ∞ | **nowhere** — published by `/api/billing/me/` only |
| Ambient eligibility | `ambient_enabled(tier)` | no | yes | yes | yes | message intake (ignores the switch) |
| Collaborator search on Free | `collab.matcher` | blocked only when enforcing | | | | |

All of these live as Python dicts in `web/backend/apps/billing/entitlements.py`.

### Feature gates (tier → capability)

`TIER_FEATURES` in `entitlements.py`, read by about 40 call sites through
`has_feature` / `lab_has_feature` / `department_has_feature` /
`users_with_feature`: the nightly pipelines (`content/tasks.py`, `pipeline.py`,
`opportunities.py`, `theme_run.py`), reminders, report resend, Discord / Slack
delivery (`BOT_SERVER`), the integration gate, and onboarding's LLM match. All
resolve to "granted" while the switch is off, so they need no change when
billing is off — they only need to keep working when it is on.

### Access and lifecycle

| Gate | Setting / code | Default |
| --- | --- | --- |
| Sign-up code | `SIGNUP_ACCESS_CODE`, `signup_gate.py` | hardcoded `251253` fallback |
| Brute-force ban | `SIGNUP_CODE_MAX_FAILURES` / `_WINDOW_` / `_LOCKOUT_SECONDS` | 3 / 1 h / 1 h |
| Institution email required | `SIGNUP_REQUIRE_INSTITUTION_EMAIL` | off |
| Tier granted at sign-up | `SIGNUP_GRANT_TIER` | spore (admin path ignores it) |
| Verified email to create orgs / invite | `require_verified_email` | on, staff exempt |
| Email delivery | `EMAIL_ENABLED` (Resend) | off → console |
| Org plan state at creation | `create_lab_workspace` / `create_department_workspace` | INACTIVE |
| Plan activation | `activate_*_subscription` (admin page, seed command) | manual |

### Feature switches (instance-wide, all off by default)

`AMBIENT_ENABLED`, `AMBIENT_DELIBERATE_ENABLED`, `AMBIENT_DRIFT_ENABLED`,
`AMBIENT_TRANSCRIPTS_ENABLED`, `COLLAB_SEARCH_ENABLED`,
`PROJECT_ALERTS_ENABLED`, `OPPORTUNITY_ANNOUNCEMENTS_ENABLED`,
`HIGH_SIGNAL_DELIVERY_ENABLED`, `RERANK_ENABLED`, `SLACK_ENABLED`,
`TEAMS_ENABLED`, `EMAIL_ENABLED`.

### Cost controls (how much the nightly run spends)

These bound compute and model calls, not what a person may do, and should stay
bounded even when policy limits are `unlimited`:
`OPPORTUNITY_LLM_CONCURRENCY` (12), `WRITEUP_LLM_CONCURRENCY` (12),
`TYPESAFE_RERANK_CONCURRENCY` (12), `AMBIENT_EXTRACT_CONCURRENCY` (8),
`CLUSTER_WRITEUP_BUDGET` (40), `MEMBER_FIT_LLM_LIMIT` (10),
`KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP`, `KNOWLEDGE_FIELD_LOOKUPS_NIGHTLY_CAP`,
`COLLAB_SLOTS_NIGHTLY_CAP` (200), `AMBIENT_EXPLAIN_NIGHTLY_CAP` (200),
`AMBIENT_EXTRACT_DAILY_CAP_PER_LAB`, `LLM_MAX_TOKENS` (1024),
`LLM_THINKING_BUDGET` (512), the `*_MAX_SURFACE` / `*_FEED_MAX` / `REPORT_TOP_N`
sizes, and the per-day delivery caps (`HIGH_SIGNAL_WEEKLY_CAP`,
`PROJECT_ALERT_DAILY_CAP`, `AMBIENT_QUESTIONS_PER_DAY`,
`COLLAB_SEARCHES_PER_DAY`, `COLLAB_APPEARANCE_CAP`). The policy limits above are
also cost drivers: each cluster, watch topic and active project is one more
search and scoring pass per night.

The rest of `settings.py` is tuning (thresholds, weights, half-lives, TTLs),
infrastructure (hosts, cache URLs, model endpoints) or secrets.

### Frontend

- Fallback caps hardcoded to Free (3 / 2 / 6) when entitlements have not
  loaded: `onboarding-flow.tsx`, `profile-editor-modal.tsx`.
- "Upgrade" copy: `onboarding/fields.tsx`, `cluster-organizer.tsx` (×2),
  `projects-list-section.tsx` (×2), `project-detail-section.tsx`,
  `plans-card.tsx`, `collab/team-fit-line.tsx`.
- Plan UI: `BillingSection` + `PlansCard` + `LabPlanCard` on Account,
  `DeptPlanCard` on department settings, tier pills and plan assignment in
  `admin-section.tsx`.
- Feature-driven nav (`nav.ts`, `portal-sidebar`, `workspace-sheet`,
  `scope-guard`, `reports-section`) reads `/api/billing/me/` features — fine
  while gating is off.

## Proposed shape

### `mycelium.toml` sections

```toml
[instance]
profile = "lab"            # personal | lab | department | institution

[billing]
mode = "off"               # off | subscriptions

[limits]                   # used when billing.mode = "off"; "unlimited" allowed
clusters = "unlimited"
topics_per_cluster = "unlimited"
watch_topics = "unlimited"
personal_projects = "unlimited"
lab_projects = "unlimited"
department_projects = "unlimited"
lab_members = "unlimited"

[limits.tiers.free]        # used only when billing.mode = "subscriptions"
clusters = 3               # ... today's numbers, moved out of Python

[signup]
mode = "invite"            # closed | invite | code | domain | open
allowed_domains = []
verify_email = true

[features]
ambient = false
collab_search = false
# ... one key per *_ENABLED switch

[nightly]                  # cost controls
llm_concurrency = 12
# ... one key per budget / nightly cap
```

Key names are a draft; the CLI's `explain` text and the comments in the
generated file are the documentation.

### Profiles (draft numbers — to confirm)

| | personal | lab | department | institution |
| --- | --- | --- | --- | --- |
| clusters × topics | unlimited | unlimited | 6 × 10 | 4 × 5 |
| watch topics | unlimited | unlimited | 20 | 20 |
| personal / lab / dept projects | unlimited | unlimited | 5 / 10 / 30 | 3 / 10 / 30 |
| lab members | unlimited | unlimited | unlimited | unlimited |
| sign-up | closed after admin | invite | invite or domain | domain |
| billing | off | off | off | off (may switch on) |
| nightly budgets | host-sized | generous | budgeted | budgeted |

## Phases

0. **Audit** — this document. ✅
1. **Config loader.** A typed loader (`web/backend/config/instance.py`) that
   reads defaults → profile → `mycelium.toml` → env, validates, and records the
   source of every value. `settings.py` reads it; env names keep working.
2. **Limits off the tier dicts.** One resolver answers "what is this user's /
   lab's / department's limit": billing off → `[limits]` plus admin overrides;
   billing on → `[limits.tiers.*]`. `entitlements.py`, `research/limits.py`,
   `ambient/eligibility.py` and `collab/matcher.py` call it instead of reading
   tiers. Billing off also creates orgs active and seats nobody. The first
   admin no longer lands on Free.
3. **Sign-up policy.** `[signup].mode` replaces the bare access code; drop the
   hardcoded fallback; reconcile `verify_email` with email being off.
4. **CLI.** `ops/mycelium config init|show|explain|set|validate|diff|recommend`,
   all with `--json`. `make setup` asks for (or takes) the profile.
5. **Agent skill.** `docs/skills/configure.md`: interview → `config recommend
   --json` → show the proposed file with reasons → `config set` on agreement.
6. **App follows config.** `/api/instance/` (mode + effective limits);
   frontend drops tier names and Free fallbacks, hides plan UI when billing is
   off, and cap messages name the config key instead of "upgrade". Admin page
   gains per-lab / per-department overrides.
7. **Migrate and document.** A `mycelium.toml` that reproduces the hosted
   instance exactly; `docs/configuration.md`; README, repo map, architecture,
   tests per profile.

## Open questions

1. Profile numbers for `department` and `institution` (the draft above).
2. Sign-up modes: should `open` (no code, no invite) exist? Should `domain`
   admit anyone with an allowed address without an invite?
3. Email verification when email is off: auto-verify, verify by admin
   approval, or refuse to start an invite/domain profile without email?
4. Nightly cost: expose the individual knobs only, or add one
   `nightly.model_calls_per_night` budget the run degrades to?
5. `PI_CAPS` is published but never enforced: drop it, or enforce it as
   `lab_leads`?
6. Hosted instance: keep today's behaviour (`billing.mode = "subscriptions"`,
   Spore at sign-up, current caps) or move it to a profile?
