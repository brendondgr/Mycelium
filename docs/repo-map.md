# Mycelium Repository Map

**Purpose:** find code without searching. Look up the task, open the path. This
replaces blind `find` / `grep` / `ls` sweeps.

**Keep it accurate:** when you add, move, or rename a top-level area (a Django
app, an app route group, a `lib/` module, an infra file), update the matching row
in the same change. A map is only useful while it is trusted. Keep rows to a
locator — one line, no design rationale. Rationale belongs in
[`architecture.md`](architecture.md); HTTP shapes belong in
[`api-contract.md`](api-contract.md).

Paths are relative to the repository root.

---

## Frontend — public site

| Task | Path |
|---|---|
| A marketing page | `web/landing/src/pages/*.astro` — four pages: `index`, `product`, `about`, `contact`. There is no pricing page (removed for the open-source release); `/pricing` redirects to `/` in `astro.config.mjs` |
| Landing copy & capability claims | `web/landing/src/data/{landing,product,site}.ts`; `site.ts` holds the nav, the sign-up CTA ("free with a sign-up code") and `sourceRepoUrl` |
| Landing components | `web/landing/src/components/{landing,site}/` |
| Front page sections (Night Forest) | `web/landing/src/components/landing/` — `HomeHero` (wordmark and build-time threads; no Mylo figure, by decision), `MorningReport`, `FeedTabs`, `ShowsItsWork` (spotlight that tours the card's parts; hover a note to move it), `WhatItCovers`, `OneNight`, `TwoWays` (`#self-host`), `FinalCta` |
| Mycelium threads & spores (seeded, grown at build time) | `web/landing/src/lib/mycelium.ts`; `components/site/Spores.astro` |
| Shared Night Forest classes (`nf-*`), dark theme switch | `web/landing/src/styles/global.css`; `data-theme="dark"` on `<html>` in `PublicLayout.astro` |
| Landing feed preview — the four cards, mirroring the app's feeds | `web/landing/src/components/landing/feed/{Paper,Grant,Fellowship,Conference}Card.astro` + shared `ClusterRow`, `ActionBar`, `Reason`, `SourceRow`, `Glyph`; `FeedCard.astro` picks by kind; `FeedTabs.astro` (front page) shows two per feed behind CSS-only tabs |
| Landing feed preview content & shapes | `web/landing/src/data/feed-preview.ts` — fictional content, real field set; carries **no** verdict or position, because the app's cards draw none |
| Landing feed preview styles (plain-CSS port of the app's card classes) | `web/landing/src/styles/feed-card.css` — global, imported by `FeedTabs.astro` and `ShowsItsWork.astro` |
| Section backgrounds (tinted ground + botanical motif) | `web/landing/src/components/site/SectionGround.astro` — pick a different motif per section; leave plain sections between |
| The motif artwork (roots, moss overhang, leaf vine, canopy, spores, filaments) | `web/landing/src/components/site/motifs/` |
| Landing styles, scroll reveals | `web/landing/src/styles/global.css` (rules) + the two inline scripts in `web/landing/src/layouts/PublicLayout.astro` (arming flag + IntersectionObserver); no framework JS |
| Artwork masters & sync | `web/art/` (incl. the Mylo character sheet `Mylo/myloCharacterCard.png` and `logo/Logos.png`), `web/scripts/sync-art-assets.mjs` (derivatives are git-ignored). Mylo on the public site is painted only — `MyloHeadshot-e1.png` (transparent head, the report avatar); `MyloScout.png` (full body, cut from the character sheet) is kept as a master but not synced or shown; the vector rig in `web/art/Mylo/svg/` is not to be used |
| Mylo animation rig (vector) | `web/art/Mylo/svg/` — `mylo.svg`: ~70 hand-authored shapes placed by measuring the character sheet, plus the animation CSS, in one file; states are attributes on the root element (`data-anim`, `data-prop`, `data-facing`). `trace/draw.py` + `trace/rig.css` regenerate it (`trace/run.sh`); `rig-demo.html` exercises it; see the folder README |

## Frontend — authenticated app

| Task | Path |
|---|---|
| An app route | `web/app/src/app/app/(workspace)/<name>/page.tsx` |
| Login / signup routes | `web/app/src/app/{login,signup}/` + `web/app/src/components/auth/` |
| Join invitation landing (signed-out) | `web/app/src/app/join/[token]/` + `web/app/src/components/auth/join-invitation.tsx`; needs its own nginx `location` block like the reset routes |
| Password reset (signed-out) | `web/app/src/app/{forgot-password,reset-password}/` + `web/app/src/components/auth/{forgot-password-form,reset-password-form}.tsx`; both need an nginx `location` block (`web/infra/nginx/default.conf`) or the emailed link 404s |
| Portal shell, sidebar, scope state | `web/app/src/components/portal/{workspace-shell,portal-sidebar,portal-context}.tsx`; scope types in `web/app/src/lib/portal/workspace.ts` |
| Switching workspace (personal / lab / department) | `web/app/src/components/portal/{workspace-rail,workspace-sheet,workspace-palette,workspace-caption,workspace-mark}.tsx` — rail on desktop (`lg`+), one sheet on mobile, ⌘K palette everywhere. There is no `lab-switcher` and no `portal-mobile-nav`; mobile has no second nav row |
| Which sections a scope offers (and the redirect when it doesn't) | `web/app/src/lib/portal/nav.ts` + `web/app/src/components/portal/scope-guard.tsx`; icons resolved in `portal/nav-icon.tsx`. A department scope has **no research feeds**; its one feed-like page is *Opportunities* (department-level calls only) |
| The active workspace in the URL | `SCOPE_PARAM` / `routeWithScope` in `web/app/src/lib/portal/routes.ts` — `?ws=<lab-slug\|dept-id>`; the URL wins, `localStorage` is only the default for a bare entry |
| Shared card primitives | `web/app/src/components/portal/primitives/` — `card`, `match-card`, `cluster-badge`, `hidden-by-filters`, `pill`, `section-header`, `feed-search-bar`, `feed-sentinel`, `markdown-prose`, `modal`, `editor-modal`, `recommended-for`, `info-popover`, `deadline-list`, `source-footer` |
| A card's judgement | **The app shows none.** There is no percent match, no per-theme position, and no verdict chip anywhere in the app UI. The backend still computes and stores a verdict and a slate position, and the API still serves both (`verdict`, `position`, `position_of`), so restoring a display is a frontend-only change; the printed report (`daily_report_pdf.py`), the Discord digest and the briefing still read them |
| The rows a feed's filter rail took out | `web/app/src/components/portal/primitives/hidden-by-filters.tsx`; mounted after the card list on the grants, conferences and fellowships feeds |
| Links into Discord on the web (Discord logo + `#channel`, new tab, a menu when bound in several servers) | `web/app/src/components/portal/primitives/discord-link.tsx` (`DiscordLink`, `DiscordMark`; `MarkdownProse` uses it for report links) |
| A feed card's "Can we use this?" strip (checks, who should look, where it was announced) and a lab feed's "Mylo held back" tail | `web/app/src/components/portal/primitives/usability-strip.tsx`, `held-back.tsx`; mounted by the grants, conferences and fellowships cards |
| Lab overview "Announced" panel (+ the full list with what Mylo held back) and "Closing soon · 14 days"; lab settings → Announcements card (settings, who applies, one block per server) | `web/app/src/components/portal/sections/announced-panel.tsx`, `announcements-card.tsx`; data from `GET /api/announcements/` via `useAnnouncements` |
| Department **Opportunities** page (department-level items only: reason tags with the quoted sentence, labs that could lead, checks, its thread); department settings → Announcements card | `web/app/src/components/portal/sections/dept-opportunities-section.tsx` at `/app/department-opportunities` (`deptOpportunities` in `lib/portal/routes.ts` and `nav.ts`), data from `GET /api/announcements/department-opportunities/` via `useDeptOpportunities`; the card is mounted in `department-section.tsx` |
| A feed card's theme badges (attributed cluster + "Also…") | `ClusterRow` in `web/app/src/components/portal/primitives/cluster-badge.tsx`; rendered under the title by every feed card, not on the rail |
| A feed card's Deadlines button + dropdown (alerts per round) | `web/app/src/components/portal/primitives/deadline-list.tsx` (`DeadlineMenu`) |
| A feed card's source row + "View …" button | `web/app/src/components/portal/primitives/source-footer.tsx` (`SourceRow`, `ViewLink`) |
| The report's ranked entry (title, insight, note, match rail, deadline strip) | `web/app/src/components/portal/primitives/report-entry.tsx`; its print half is `_entry_row` in `web/backend/apps/content/daily_report_pdf.py` |
| Decorative motion (vines, threads, seedlings, ring sweep) | `web/app/src/components/portal/motion/` (reduced-motion + in-view-once hooks), `portal/leaf-vine.tsx`, keyframes in `web/app/src/app/globals.css` |
| Feed card scroll entrance (predictive, fires ahead of the reader) | `web/app/src/components/portal/motion/reveal-on-scroll.tsx` |
| Workspace background growth, per section | `web/app/src/components/portal/motion/section-ground.tsx`, mounted in `portal/workspace-shell.tsx` |
| The institution line (read-only: an institution comes from the verified email, never typed) | `web/app/src/components/ui/institution-from-email.tsx`; mounted by onboarding step 1, `profile-editor-modal.tsx`, `account-section.tsx`, and `CreateDepartmentModal` in `labs-section.tsx`. The sign-up form's "you'll be listed at …" hint resolves the address with `web/app/src/lib/institutions.ts` |
| The affiliation directory itself (~10.3k universities, national labs, institutes) | `web/app/public/data/institutions.json`, built by `web/scripts/build-institutions.mjs` (`npm run institutions`) from Hipolabs' list plus `web/scripts/data/research-institutions.json` (curated institutes + typed aliases). Served at `/data/`, which needs its own nginx block, and read from disk by the backend (`COLLAB_INSTITUTIONS_PATH`) to derive institutions — a domain missing from it places nobody, so adding it here is how an institute becomes provable |
| Workspace design playground (`/labs`: a fictional-data mock of the workspace restyled after the Night Forest front page, a right-hand panel of layout options + notes, "Copy for Claude" export) | route `web/app/src/app/labs/` (`page.tsx`, `labs.css`); `web/app/src/components/labs/` — `schema.ts` declares every option and builds the export, `preview/` holds the mock chrome, pages and fixtures. Dev-only unless `MYCELIUM_LABS=1`; its nginx block is `location = /labs` |
| Onboarding (first run only) | `web/app/src/components/onboarding/` + route `web/app/src/app/app/onboarding/` |
| Cluster organizer | `web/app/src/components/onboarding/cluster-organizer.tsx` |
| Profile / lab edit modals | `web/app/src/components/portal/sections/{profile-editor-modal,lab-editor-modal}.tsx` |
| Inviting people into a lab or department | `web/app/src/components/portal/sections/org-invite-card.tsx` — `OrgInvitePanel` is the control, `OrgInviteCard` is it in a card. Three tabs: email (chip field, ≤ `ORG_INVITE_BATCH_MAX`), share link, and `Already on Mycelium` (lab only, the legacy `LabInvitation` path) |
| Where that panel is mounted | `members-section.tsx` (dialog behind "Invite member"), `lab-settings-section.tsx` (left rail), `labs-section.tsx` (lab detail), `department-section.tsx` (department settings) |
| Creating a lab or a department from inside the app | `LabsSection` in `web/app/src/components/portal/sections/labs-section.tsx` (`CreateLabModal`, `CreateDepartmentModal`); both gated on `user.isVerified` |
| Overview (personal + lab) | `web/app/src/components/portal/sections/{overview-panels,mylo-report-card,mylo-found-card,lab-overview-section,lab-onboarding}.tsx`, `portal/primitives/report-summary-table.tsx` |
| Feeds: papers / grants / fellowships / conferences | `web/app/src/components/portal/sections/{research-papers-section,opportunities-section,fellowships-section,conferences-section}.tsx` |
| Feed filter rails | `web/app/src/components/portal/sections/{grant-filters,fellowship-filters,conference-filters,saves-filters}.tsx` |
| Saves & reminders | `web/app/src/components/portal/sections/{saves-section,reminders-section}.tsx`, `portal/{reminder-composer,reminder-editor,reminder-offsets-field,mention-picker}.tsx` |
| A feed card's tool block (ignore, reminder, bookmark + Deadlines) | `web/app/src/components/portal/sections/opportunity-bits.tsx` (`CardActionBar`) |
| Save button & scope menu | `web/app/src/components/portal/sections/opportunity-bits.tsx` |
| Undo popup shared by every card tool | `web/app/src/components/portal/sections/opportunity-bits.tsx` (`useCardUndo`, `UndoPopup`) |
| Manual ignore control + undo strip | `web/app/src/components/portal/sections/opportunity-bits.tsx` (`IgnoreButton`, `IgnoredStrip`); mounted by each feed card's `ignorable` prop |
| Ignored review view (a tab on Saves) | `web/app/src/components/portal/sections/saves-section.tsx` (`IgnoredBody`, `IgnoredRow`) |
| Search UI | `web/app/src/components/portal/global-search.tsx`, `portal/sections/{search-section,search-result-card}.tsx` |
| Projects UI | `web/app/src/components/portal/sections/{projects-list-section,project-detail-section}.tsx` |
| Project page parts (identity, four-area tabs, editor, team) | `web/app/src/components/portal/projects/{project-identity,project-tabs,project-editor-modal,project-team-card,create-project-wizard}.tsx` |
| What Mylo filed under a project from lab conversation (editors only): channel hints and "this was a different project" | `web/app/src/components/portal/projects/project-conversation-card.tsx`, mounted on the project page's Settings tab; a project's aliases are edited in `project-editor-modal.tsx` (Details) |
| Labs / members / lab settings | `web/app/src/components/portal/sections/{labs-section,members-section,lab-settings-section}.tsx` |
| Reports page (briefing history) | `web/app/src/components/portal/sections/reports-section.tsx` |
| Account page (identity, email, password + subscription) | `web/app/src/components/portal/sections/account-section.tsx`; route `/app/account` |
| Subscription management (the Account page's money half) | `web/app/src/components/portal/sections/billing-section.tsx`; `/app/billing` redirects to `/app/account` |
| Admin page | `web/app/src/components/portal/sections/admin-section.tsx` |
| Notification bell | `web/app/src/components/portal/notification-bell.tsx` |
| API client, hooks, types | `web/app/src/lib/` and `web/app/src/lib/portal/{client,hooks,mutations,types}.ts` |
| Infinite reveal (sentinel observer + scroll backstop, 1400px lead) | `web/app/src/lib/portal/use-infinite-reveal.ts` |
| Which ancestor actually scrolls a feed (every feed observer roots on it) | `web/app/src/lib/portal/scroll-parent.ts` |
| Calendar-date formatting for cards | `web/app/src/lib/portal/dates.ts` (`formatIsoDate`) |
| Design tokens / theme | `web/packages/config/src/theme.css` |

## Backend — identity & organization (`apps/accounts`)

| Task | Path |
|---|---|
| Users, labs, departments, memberships, roles | `web/backend/apps/accounts/models.py` |
| Session auth, CSRF, `/me`, labs, invitations, watch | `web/backend/apps/accounts/{views,urls,serializers}.py` |
| Permission rules | `web/backend/apps/accounts/permissions.py` |
| Workspace provisioning at signup | `web/backend/apps/accounts/provisioning.py` |
| Who may sign up (`signup.mode`: closed / invite / code / domain / open) and whether email must be verified; `GET /api/auth/signup-policy/` | `web/backend/apps/accounts/signup_policy.py`; tests `apps/accounts/tests/test_signup_modes.py`; the form reads it in `web/app/src/components/auth/signup-form.tsx` |
| The code mode's brute-force gate (shared code, shadow ban) | `web/backend/apps/accounts/signup_gate.py` |
| Join invitations (emailed to one address, or a share link with a use budget + expiry) | `web/backend/apps/accounts/invites.py`, models `OrgInvite` / `OrgInviteRedemption`; `create_invites` + `screen_address` are the batch path (≤15 addresses, per-address refusals) |
| Invite → sign-up, end to end, both org kinds | `web/backend/apps/accounts/tests/test_invite_signup_flow.py` |
| Email verification (the six-digit code that activates an account) | `web/backend/apps/accounts/email_verification.py`, model `EmailVerification` |
| A person's institution, derived from the verified email (the resolver, the one writer of `Profile.institution`, the refusal of a typed one) | `web/backend/apps/accounts/institution.py`; the `email_verified` signal in `signals.py` re-derives the collaboration affiliation |
| Password reset by emailed link | `web/backend/apps/accounts/password_reset.py` |
| Who may grant which lab role, and act on whom | `LAB_ROLE_RANK` / `lab_role_rank` / `user_can_grant_lab_role` / `user_outranks_lab_member` in `web/backend/apps/accounts/permissions.py` — authority runs strictly downward, so only the PI creates admins and ownership never moves by a role edit |
| Handing a lab to its real PI | `transfer_lab_ownership` in `web/backend/apps/accounts/services.py`, `LabTransferOwnershipView`, route `POST /api/auth/labs/<slug>/transfer-ownership/`; irreversible because the outgoing owner becomes an admin and an admin cannot grant ownership |
| Removing a member / changing a role, from the app | `MemberRow` in `web/app/src/components/portal/sections/member-row.tsx` (role select, Remove, Make PI, both confirms); `useLabMemberMutations` in `web/app/src/lib/portal/hooks.ts`; the client-side mirror of the rank rule is `LAB_ROLE_RANK`/`grantableLabRoles`/`outranksLabMember` in `lib/portal/nav.ts` |
| An invitation claimed by address rather than by link | `invites.pending_for_email` / `invites.claim_for_verified_email`; sign-up reports `pending_invite` without naming the org, and the claim lands on email verification (`email_verification.verify`) |
| Placing an account the affiliation directory cannot | `institution.grant` / `revoke_grant`, `Profile.institution_granted{,_by,_at}`, command `grant_institution --user <name> --institution <name> [--revoke]`; a grant wins over the derived value and is audited |
| What an unverified account may not do | `require_verified_email` in `web/backend/apps/accounts/permissions.py` — guards lab/department creation, both profiles, and issuing invitations. Redeeming one is *not* gated: it guards standing an org up, not being brought into one |
| Interests contract (v2 clusters) | `web/backend/apps/accounts/interests.py` |
| Profile / lab intake & synthesis | `web/backend/apps/accounts/intake/` — `synthesize.py`, `lab.py`, `clusters.py`, `agent.py` |
| Derived membership aggregates | `web/backend/apps/accounts/aggregates.py` |
| The reader's own published works, kept from the author import | `web/backend/apps/accounts/author_works.py`, model `AuthorWork` — so a report can tell a discovery from a paper the reader wrote |

## Backend — research context (`apps/research`)

| Task | Path |
|---|---|
| Projects, membership, invitations, visibility, archiving, collaboration endpoints | `web/backend/apps/research/{models,views,serializers,urls}.py` |
| Project state (what it claims, blocks on, aims at) | `web/backend/apps/research/state.py` (shape, normalising, the slow fingerprint), model `ProjectState`, endpoints `/api/projects/<id>/state/` and `.../state/confirm/` |
| Reading a project's state out of a document | `web/backend/apps/research/state_extract.py` — schema, deterministic grounding checks, one bounded repair; proposes only, never saves |
| Which buffer and window a project is judged against | `web/backend/apps/content/timeline_settings.py` (`effective_timeline`): project override → the reader's own → the lab's → 14/60 |
| Per-scope project caps | `web/backend/apps/research/limits.py` |

## Backend — matching & delivery (`apps/content`)

Files below are inside `web/backend/apps/content/`.

| Task | File |
|---|---|
| Content items, scores, saves, ignores, reminders, notifications | `models.py` |
| Manual ignore (per reader): model, endpoints, feed filtering | `models.py` (`IgnoredItem`), `views.py` (`IgnoreItemView`, `IgnoredItemsView`, `_ignored_content_ids`) |
| Scoring target (user / lab / project) | `targets.py` |
| Paper pipeline | `pipeline.py`, `interests_query.py`, `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, `suggest.py`, `clustering.py` |
| What each interest actually searches for (theme-scoped context, capped) | `interests_query.py` (`search_interests`, `INTEREST_CONTEXT_TERMS`) — it appended the whole profile's keywords to every area until EXP-2026-08-020; do not reintroduce a profile-wide suffix |
| Per-theme slates (depth, entrant diff, pruning, bridges) | `slates.py` — replaces the global Top-25 for any profile with declared areas; the flat `top_rank` signals are still derived from it for existing readers |
| Per-theme admission (absolute floor OR a theme's relative floor, hard minimum) | `admission.py` (`admit`, `AdmissionStats`), entered from `pipeline.fuse_clusters_pool` |
| The four-point verdict that replaced the percent match | `verdicts.py` (`derive_verdict` for the rank band, `parse_verdict` for the model's) |
| Stage one — profile-blind précis, cached per item forever | `comprehension.py`, model `ItemComprehension` in `models.py` |
| Stage two — per-theme fit write-up (verdict, three beats, caveat, bridge) | `cluster_fit.py`; keyed on (item, cluster, target) at `signals["writeups"]` |
| Which (theme, item) pairs earn a model call — reuse, entitlement, budget | `theme_run.py` (`plan_theme_writeups` = DB, `execute_theme_plan` = pure, `collect_theme_result`) |
| Mylo's prose — the per-theme read and the lead paragraph | `narrative.py`; stored as structure on `DailyBriefing.narrative` and read back by the PDF, the app, and Discord |
| Fellowship bands (matched to a theme vs open to you) | `fellowship_bands.py` — the eligibility gate is unchanged; this only splits what survives it |
| The `RERANK_METHOD` switch — TypeSafe re-orders each theme's slate head (`typesafe`, default, paid plans) or the local stack stands (`local`); judgements stored at `signals["typesafe"][cluster_id]` and reused by fingerprint | `typesafe_rerank.py`; entered from `pipeline.py::_explain_run` (papers), `opportunities.py::_prepare_match` (grants, conferences) and `_finalize_fellowship_match` (fellowships). Evidence `EXP-2026-09-003`/`-004` |
| Cross-encoder rerank (ships OFF, `RERANK_ENABLED`) | `reranking.py` — device resolution with CUDA auto-detect and CPU fallback, the lazy model cache, `rerank` and the per-interest/RRF `rerank_order`; entered from `pipeline.py::_apply_rerank` at the tail of `fuse_interests_pool` / `fuse_clusters_pool`. Diagnostics: `manage.py rerank_device --load`. Evidence is a **preference** (`EXP-2026-08-015`…`-017`), not a measurement — see the module docstring |
| Ranking-stack seams (ORM-free ranking, swappable vector index) | `protocols.py` (`Retrievable`, `VectorIndex`), `retrieval.py` (`PgVectorIndex`) |
| Theme spread (opt-in, all defaults off) | `fusion.py` (`SpreadPolicy`, `apply_spread`, `quota_clusters`, `cap_cluster_share`, `mmr_clusters`, `cluster_relative_pass`, `combine_clusters(merge=…)`), reached via `pipeline.fuse_clusters_pool(spread=…)`; measured in `EXP-2026-08-005` |
| Grants / conferences / fellowships matching | `opportunities.py`, `fellowships.py`, `opportunity_llm.py`, `pinning.py` |
| Fellowship eligibility gates (stage ladder, prose constraints) | `fellowships.py` (`STAGE_LADDER`, `_stage_gate`, `_constraint_gates`, `derive_stage`) |
| Fellowship eligibility extracted from prose | `web/backend/apps/scraper/eligibility/constraints.py`, `web/backend/apps/scraper/fellowships/ingest.py` (`extract_fellowship_constraints`) |
| On-demand whole-corpus refit | `refitting.py` |
| Post-onboarding live match | `onboarding_match.py`, `scan_status.py` |
| Member fit ("who is this for?") | `member_fit.py`, `fanout.py` |
| Project team signal & sharing | `team_profile.py`, `collaboration.py` |
| Daily briefing (theme sections + per-project parts, over each theme's slate) | `briefing.py`, `briefing_sections.py` |
| Arranging a day by theme for the report (entrants, standing, quiet) | `theme_report.py` |
| The legacy flat slate — still the single-vector path, and the derived `top_rank` | `top_feed.py` |
| Manual re-render + re-send of one report | `report_resend.py` |
| Briefing history & retention | `models.py` (`DailyBriefing.generated_on`), `views.py` (`BriefingHistoryView`), `management/commands/prune_briefings.py` |
| Daily PDF report | `daily_report.py`, `daily_report_pdf.py`, `daily_report_send.py` |
| Report formatting sample (no database) | `management/commands/render_sample_report.py` |
| Report cover art (derived from `web/art/`) | `report_assets/` — `mylo-headshot.png`, `mycelium-logo.png`, `README.md` |
| Lab Discord digest | `lab_digest.py` |
| The §8 smoke checklist, against live data | `smoke_reports.py`; command `manage.py smoke_reports [--send]` — twelve system checks, exits non-zero on a failure so it can gate a release |
| What Mylo proposes about a project's state, from what the reader did | `reflection.py` (deterministic rules, the rendered block), model `ReflectionProposal`, endpoints `/api/reflections/`; UI `web/app/src/components/portal/projects/reflection-card.tsx` |
| The Monday weekly | `weekly.py` (synthesis + the code frame), `weekly_packet.py` (the closed packet's shape), `weekly_build.py` (building it), `weekly_verify.py` (the citation verifier), `weekly_send.py` (Discord); commands `generate_weekly_briefing`, `send_weekly_reports` |
| The report body's markdown grammar, stated once for both renderers | `report_grammar.py` — `[P#]` citations, `[O#]` "What changed" citations, `[S:path]` state markers, labelled beats, the code-rendered references block |
| Deterministic project matchers (no model writes a number) | `matchers/` — `timeline.py` (can this project make that deadline), `overlap.py` (does this threaten the claim), `blockers.py` (does this unblock), `known_literature.py` (does the reader already have it, or write it), `team_gap.py` (does the call need somebody the team lacks), `similarity.py` (raw cosine, never RRF) |
| Which findings become alerts, and how few | `alerts.py` (five triggers, daily cap, once-ever constraint, the `PROJECT_ALERTS_ENABLED` gate), model `ProjectAlert`; command `evaluate_project_alerts` |
| The one DM a weekly-cadence reader gets between Mondays | `urgent_alerts.py` — opt-in, any non-Monday, a moved deadline on a saved item inside their buffer, keyed on the alert so it is sent once ever |
| How an alert is said on each surface | `alert_report.py` — the "Needs your attention" section, the Discord lines, the bell notification |
| One run's numbers (volume, matched, entered, by category/project/theme, deadline horizon) | `report_stats.py` — derived from the finished `ReportData`, stored on `DailyBriefing.stats`, read back by every surface |
| The Discord post's shape (overview, statistics, Discord's size limits) | `discord_embeds.py` — `personal_report_embed`, `lab_post_embed`, `fit_embed` |
| Who gets a Discord push today, and at what local hour | `delivery.py` — `push_kinds` (the cadence matrix), `send_time`/`local_today`, and every dedupe key. The stored sign-up choice is the whole rule: daily means every day including weekends, weekly means Monday only. Cadence governs push only; the nightly run and the web app are unchanged by it |
| Nightly run analytics | `run_analytics.py`, `analytics_report_pdf.py`, `management/commands/run_analytics_report.py`; the Listening section reads `apps.ambient.read.listening_totals` and is omitted when nothing is listening |
| Reminders | `reminders.py`, `reminders_tick.py`, `reminders_views.py`, `reminders_discord.py`, `reminders_announce.py`, `reminder_access.py` |
| Deadline projection | `deadlines_projection.py` |
| Opportunity announcements: which slate entrants a lab or department hears about, the six-item activation seed, never-twice (`Announcement`, `AnnouncementPost`, `AnnouncementReaction`, `AnnouncementSettings` in `models.py`) | `announce.py` (select, check, align, record); nightly commands `announce_opportunities` (`--dry-run`, `--llm`, `--lab`) and `announce_opportunity_updates` in `ops/nightly/manual_all.py`, both inert while `OPPORTUNITY_ANNOUNCEMENTS_ENABLED` is off |
| The department path: is a call one only a department can take on (institutional selection, department applicant, department-scale programme, each with the sentence it matched), which of its labs could lead, and scoring a department | `apps/content/dept_level.py` (detector v2; precision in `docs/research/experiments/EXP-2026-11-001-dept-level-precision`), `lab_fit.py` (lab-profile cosine), `targets.target_for_department`; scored only while its announcements are on (`tasks.select_departments`); `discord_announcements.notify_eligible` DMs each member who may be eligible for a department fellowship |
| Measuring announcements (Interested / Remind me / Not for us rates, web link clicks by surface, route health, held-back reasons, department slate yield and lab-fit scores) | `apps/content/announce_metrics.py` + `manage.py announcement_metrics --since --until --json`; `remind` and `link_click` reactions on `AnnouncementReaction`; web clicks from `DiscordLink`'s `surface` prop via `recordDiscordLinkClick` (`POST /api/announcements/link-click/`). Baseline: `docs/research/experiments/EXP-2026-11-002-announcement-baseline` |
| Remind me without a Mycelium account (guest reminders) | `gate.authorize_guest` in `apps/integrations/services/gate.py`; `_remind_gate` / `_guest_remind` / `unremind` in `apps/content/announcement_actions.py`; delivery in `discord_announcements.send_due_nudges` / `_dm_nudge`; `recipient_discord_id` on `DiscordOutboxMessage` |
| Announcements in Discord: forum threads per binding, in-place updates, closing, the daily closing-soon list, nudges (`ClosingSoonPost`, `AnnouncementNudge`); the outbox's `forum_thread` / `thread_update` / `delete_channel` modes | `discord_announcements.py`; outbox modes in `web/backend/apps/integrations/services/outbox.py` (`_deliver_thread_mode`) with REST helpers in `services/discord_api.py` |
| What the thread buttons do (Interested, Remind me, Not for us, Stop following) and the `/setup` announcements step (create or pick forums, who can post, switch on) | `announcement_actions.py`, `announcement_setup.py`; bot side `mylo/bot/cogs/announcements.py` and the `📣` button in `mylo/bot/cogs/setup.py`, via `mylo/linking.announcement_action` / `announcement_setup` |
| Search links into announcement threads: "Already discussed here", a manager's "Announce to …", the web card's `discord` / `discord_thread_url`, threads deleted by hand | `announcement_links.py`; `discord_commands.search(…, guild_id)`; `annx:` buttons in `mylo/bot/cogs/announcements.py`; the thread-delete listener in `mylo/bot/cogs/drift.py`; nightly `discord_announcements.verify_threads` |
| The bounded editor behind each announcement: closed packet, verifier (no digits, only offered people), template fallback | `announce_editor.py` (`edit`, `verify`, `template`, `RUBRIC_VERSION`) |
| What an announcement showed and whether its call changed (facts snapshot, fingerprint, "What changed" lines); the closing-soon list | `announce_facts.py`; the nightly plan of changed / closed / closing-soon items is `announce_updates.py` |
| "Can we use this?" — open, deadline vs buffer, who may apply, country, award, eligibility counts, team coverage (record fields only; missing → `unknown`) | `usability.py` (`assess`, `Reader`, `reader_for_lab/department/user`); the serializer field is `_OpportunitySerializer.get_usability` |
| Is an opportunity still worth showing (feeds + prune share it) | `liveness.py` |
| Unified search | `search.py`, `search_service.py`, `query_embedding.py` |
| High-signal alerts | `high_signal.py` |
| Read surfaces (feeds, saves, notifications) | `views.py`, `serializers.py`, `urls.py` |
| Display-time formatting shared by serializers (amounts) | `formatting.py` |
| Celery tasks & target selection | `tasks.py` |

## Backend — the ambient evidence ledger (`apps/ambient`)

| Task | Path |
|---|---|
| Connected surfaces and the consent each one gave | `web/backend/apps/ambient/models.py` (`Source`) |
| One person's listening opt-in and the "shut off" switch, per platform | `web/backend/apps/ambient/models.py` (`ListeningConsent`) |
| Whether a message may be recorded at all (surface consent, person opt-in, paid effective tier) | `web/backend/apps/ambient/eligibility.py` — resolved on arrival, never cached at the edge |
| Where a person's actual words live (and for how long) | `web/backend/apps/ambient/buffer.py` — its own Redis (`redis-ambient` in `compose.yaml`, persistence off), per-message TTL, dropped explicitly once a window is read; a source can shorten the window but never lengthen it |
| The id-only pointer beside it (no body, ever) | `web/backend/apps/ambient/models.py` (`RawMessageRef`) — the window index and the handle an edit or deletion is reconciled through |
| Recording one message: eligibility, hash, buffer, reference, repeat collapse | `web/backend/apps/ambient/ingest.py` (`record`, `IncomingMessage`); normalisation for the repeat hash in `text.py` |
| The durable record — what Mylo understood, in Mylo's own words | `web/backend/apps/ambient/models.py` (`Observation`); six understanding kinds, six forces, subject, visibility, supersession. **No quote column** |
| A person's own verdict on an observation (the labels the feature is judged by) | `web/backend/apps/ambient/models.py` (`ObservationFeedback`) — append-only; a correction is a new row |
| Something was removed, so these things must be recomputed | `web/backend/apps/ambient/models.py` (`Retraction`) |
| How a platform gets its conversation in (translation only — no extraction, no attribution) | `web/backend/apps/ambient/adapters/base.py` (`Adapter`, `PlatformEvent`), registry in `adapters/__init__.py`, `adapters/fake.py` for tests |
| An edit, a deletion, "delete my observations", a surface withdrawing consent | `web/backend/apps/ambient/reconcile.py` — an edit marks what rested on it stale, a deletion removes the evidence, and anything that deletes leaves a `Retraction` |
| The retention sweep (references only — observations are never touched) | `web/backend/apps/ambient/retention.py`, task `apps.ambient.sweep_retention`, command `sweep_ambient_retention` |
| Reading the ledger from the rest of the backend — **one of two doors** | `web/backend/apps/ambient/read.py` (windows, evidence, retractions); the AST guard is `apps/ambient/tests/test_import_boundary.py` |
| Everything the Mylo gateway does to the ledger — **the other door** | `web/backend/apps/ambient/service.py`; the gateway runs Django in process and imports nothing else from `ambient` |
| Which Discord snowflake is which Mycelium user, for listening | `web/backend/apps/ambient/adapters/discord.py` — resolves through `integrations.services.resolve` and nothing else |
| Whether a message is worth carrying at all (bots, chatter, excluded and social channels, length) | `web/backend/apps/ambient/filters.py` |
| What one server produced on one day, in counts and never names | `web/backend/apps/ambient/models.py` (`SourceActivity`); the one-time "this server is listening" DM is `MemberNotice` |
| Which project a message is about — seven signals, a floor and a margin, and an honest "unresolved" | `web/backend/apps/ambient/attribution.py` (`score` is pure; `candidates_for`, `context_for`, `attribute_ref` are the database half) |
| Other names a project goes by in conversation | `Project.aliases` in `web/backend/apps/research/models.py` |
| A channel's optional default project, and a person's "this was a different project" | `web/backend/apps/ambient/models.py` (`ChannelHint`, `AttributionCorrection`) |
| Which project a person is actually spending their conversation on (7- and 28-day shares) | `web/backend/apps/ambient/attention.py`, model `ProjectAttention`, task `apps.ambient.recompute_attention`; read through `read.attention_for` |
| What a project editor can see and change about attribution (aliases aside) | `web/backend/apps/ambient/editing.py` (who sees what), `views.py` + `urls.py` at `/api/ambient/` |
| Which conversations are ready to be read (quiet, capped, or about to expire) | `web/backend/apps/ambient/windows.py` (`ready`, `assemble`, `mark_read`); `RawMessageRef.read_at` |
| Reading a conversation into grounded observations (schema, grounding, no quotes, one repair) | `web/backend/apps/ambient/extract.py` |
| The hourly read: attribution's second look, extraction, concept linking, deleting the text | `web/backend/apps/ambient/reading.py`, task `apps.ambient.read_conversations`, command `read_ambient`; one `ExtractionRun` per window (counts and codes, never text) |
| Deciding what observations mean — consistency, coverage, declines, budget, one outcome per topic | `web/backend/apps/ambient/deliberate.py` (pure, no model), model `Finding` |
| Mylo's explanation of a finding, written from its own notes | `web/backend/apps/ambient/explain.py` |
| The nightly deliberation step | command `deliberate_ambient`, called by `deliberate_ambient()` in `ops/nightly/manual_all.py` (non-fatal; off unless `AMBIENT_DELIBERATE_ENABLED`) |
| Findings becoming understanding: pending conversational edges, project developments, fading, retraction fan-out | `web/backend/apps/ambient/evolve.py` (run by `deliberate_ambient`) |
| Meeting transcripts: one meeting, one window (parse, who-was-who, developments only, lower weight) | `web/backend/apps/ambient/transcripts.py`, model `TranscriptMeeting`, adapter `adapters/transcript.py`, `POST /api/ambient/transcripts/`, the project page's `transcript-card.tsx` |
| The measures and harm checks (Plan 10), the labelled record as a dataset | `web/backend/apps/ambient/evaluation.py`, commands `evaluate_ambient` (content app) and `export_ambient_dataset` |
| The "Mylo & you" page — questions, what changed (with undo), faded and declined, what Mylo knows, settings | `web/app/src/components/portal/ambient/mylo-and-you-section.tsx`, route `/app/mylo-and-you` (nav: personal Workspace); settings card `ambient-settings-card.tsx` (also on Account); a project's `project-developments-card.tsx` (project General tab); a lab's `lab-changes-card.tsx` (lab overview); data in `web/app/src/lib/portal/ambient/`; backend `web/backend/apps/ambient/review.py`, model `AppliedChange` |
| Asking once and respecting the answer: tonight's questions, the choices, the words, reading a reply, shut-off, the labelled record | `web/backend/apps/ambient/dialogue.py`, models `PendingSuggestion`, `ValidationRecord`; the gateway's `service.dialogue_turn` / `answer_button`; the web at `/api/ambient/suggestions/`; delivery and the bell in `content/management/commands/deliver_ambient_questions.py` |
| A dated event in a project, as Mylo understood it (told → active with undo; seen → pending) | `web/backend/apps/ambient/models.py` (`ProjectDevelopment`, `Change`); read through `read.developments_in_effect` |
| Confirmed explorations as extra, down-weighted paper themes (behind `AMBIENT_DRIFT_ENABLED`) | `web/backend/apps/content/explorations.py`; the weight is `fusion.combine_clusters(cluster_weights=…)` |
| Confirmed preferences, direction and learning goals in the model's prompts; the report's `context_version` | `web/backend/apps/content/understanding.py` |
| A person's report projects ordered by where their conversation went | `briefing.by_attention` |
| Developments reaching the alerts (closed blockers, dropped methods) | `alerts.developments_for`, `matchers/developments.py` |
| Carrying out a yes that edits the declared profile (the only writer of `Profile.interests` in the feature), and its exact undo | `web/backend/apps/ambient/apply.py` (`apply_answers`, first in `deliberate_ambient`; `revert`); provenance in `interests.sources.ambient` |
| What changed, how and why, with undo — personal and lab | `web/backend/apps/ambient/review.py`, model `AppliedChange`; `/api/ambient/changes/`, `/api/ambient/labs/<slug>/changes/` |
| A development that makes a project's stated state out of date, proposed to its editors | `web/backend/apps/content/ambient_proposals.py` (`propose`, `withdraw_stale`); `ReflectionProposal` kinds `close_blocker`, `drop_method`; run by `deliver_ambient_questions` |
| Tonight's questions delivered (DM with buttons, bell), changes and told facts announced | `web/backend/apps/content/management/commands/deliver_ambient_questions.py` |
| The weekly's "What changed" (personal and project streams, `[O#]` citations) and the daily's "Changed today" lines | `web/backend/apps/content/weekly_changes.py`; rows read through `apps.ambient.read.changes_between`; `[O#]` in `report_grammar.py`, checked by `weekly_verify.py` |
| The profile's "heard" marks, and conversation proposals on the reflection card | `profile-section.tsx` (`FromConversation`), `projects/reflection-card.tsx` |

## Backend — the knowledge core (`apps/knowledge`)

| Task | Path |
|---|---|
| Concepts, edges, tiers, scopes, and the merge log | `web/backend/apps/knowledge/models.py` (`Concept`, `ConceptAlias`, `Edge`, `ConceptMerge`) |
| Linking a topic from conversation to a concept (born in the person's or lab's scope) | `service.link_conversation`; a concept as it stands now, following merges, is `read.live_concepts` |
| What conversation taught Mylo about a person: pending, confirmed, faded, rejected, edited | `Edge` rows with `tier=conversational` (`qualifier`, `review_on`, `edited_by_person`); written by `service.record_conversational` / `confirm` / `keep` / `reject` / `fade` / `edit_conversational` / `delete_conversational` / `drop_evidence`; confirmed explorations read by `read.confirmed_explorations` |
| Which concept a wording names (alias → embedding → mint; private words stay private) | `web/backend/apps/knowledge/linker.py` |
| Staff merges, their reversal, and promotion of a private concept to the shared vocabulary | `web/backend/apps/knowledge/merging.py`; the admin's "Merge the selected concepts" and "Reverse" actions |
| Declared profiles, labs, and projects mirrored into edges | `web/backend/apps/knowledge/projection.py`; save hooks in `signals.py`, tasks `apps.knowledge.project_subject` and `apps.knowledge.sweep` (Beat, 04:15), command `project_declared_edges` |
| What each of a person's own papers shows, facet by facet (sentences, terms, field-neutral method, per-facet vectors) | `web/backend/apps/knowledge/works.py`, model `WorkFacets` |
| A person's papers as demonstrated edges, per work and rolled up; the OpenAlex field ruler on concepts | `web/backend/apps/knowledge/demonstrated.py` |
| Reading people's papers end to end (DOI field lookups, reading, vectors, edges) | `web/backend/apps/knowledge/papers.py`; queued on import (`service.queue_work_facets`, task `apps.knowledge.facet_user_works`), nightly via `facet_author_works` in `ops/nightly/manual_all.py` |
| A work's co-authors by id and its OpenAlex field | `web/backend/apps/accounts/author_works.py` (`store_author_works`, `enrich_fields`); `AuthorWork.coauthor_ids`, `openalex_field_id` |
| Reading the graph from anywhere else — **one of two doors** | `web/backend/apps/knowledge/read.py` (`own_edges`, `ranking_edges`, `lab_declared_edges`, `discoverable_edges`, `project_edges`, `undeclared_project_concepts` — Q1, `backing` — Q2); the AST guard is `apps/knowledge/tests/test_import_boundary.py` |
| Running the knowledge and collaboration pipeline at scale on a fake world, against planted truth | `web/backend/sandbox/collab/` — `python -m sandbox.collab all` (people and papers), `calls` (planted funding calls), `consent`, `match`, `panel` and `browser-prep`, `graph`, `bench` (one check per plan); its own database `mycelium_sandbox` (and `mycelium_bench` for `bench`); results under `docs/research/experiments/` (`EXP-2026-09-005` to `-011`) |
| Writing to it — **the other door** (projection, and ambient's conversational edges) | `web/backend/apps/knowledge/service.py` |

## Backend — collaboration matching (`apps/collab`)

| Task | Path |
|---|---|
| What a funding call asks a team to bring (requirement slots: problem, method, data, partner role; required or not) | `web/backend/apps/collab/slots.py`, model `RequirementSlots`; nightly `extract_requirement_slots` in `ops/nightly/manual_all.py` before scoring |
| Which of a call's slots the reader or their lab covers (Q3: `coverage.for_call`) | `web/backend/apps/collab/coverage.py` — reads the knowledge core only through `apps.knowledge.read` |
| The team-fit line stored on each grant score (`signals["team_fit"]`) | `web/backend/apps/collab/team_fit.py`; phase 4 of `run_daily_opportunities_batch`; backfill `annotate_team_fit` |
| Whether a person can be found, by whom, until when; their verified institution and country; the weekly appearance cap | `web/backend/apps/collab/consent.py` (`update`, `mutually_visible`, `may_appear`), `affiliation.py` (the `VerifiedAffiliation` row, from `apps/accounts/institution.py`'s resolver); `SEEKER_CEILING` in `consent.py` (no search past the seeker's country), models `CollaborationSetting`, `VerifiedAffiliation`, `Appearance`; `GET/PUT /api/collab/settings/` |
| Exactly what a seeker would see about a person | `web/backend/apps/collab/preview.py`; `GET /api/collab/preview/` |
| Renewal reminders and appearance pruning | `web/backend/apps/collab/tasks.py` (Beat `collab-daily`, 04:30) |
| The Collaboration card on the Account page | `web/app/src/components/portal/collab/collaboration-settings-card.tsx`, mounted by `account-section.tsx`; hooks in `web/app/src/lib/portal/collab/hooks.ts` |
| Finding collaborators (Q4): the query from a call, a project or one's own words; the gate; the four lanes; the rerank that can drop but never add; the day's cache; appearances and the search log | `web/backend/apps/collab/matcher.py` (`search`, `eligible_candidates`, `query_for_*`), models `SearchLog`, `MatchFeedback`; `GET/POST /api/collab/search/`, `searches/<id>/feedback/`, `saved/` |
| The collaborator search panel and its entry points (a grant card's "Find collaborators", the project's Collaborators tab, the Projects header, the ⌘K palette) | `web/app/src/components/portal/collab/search-panel.tsx` (the panel; `CollaboratorSearchHost`, mounted once in `workspace-shell.tsx`, opens it on the `mycelium:collab-search` event), `find-collaborators.tsx` (the shared button and the project card); the side-panel variant of `primitives/modal.tsx` |
| Who published with whom on Mycelium; introduction paths, "outside my network", team formation | `web/backend/apps/knowledge/coauthorship.py` (model `Coauthorship`, rebuilt by the 04:15 sweep and `rebuild_coauthorship`), walks in `knowledge/read.py` (`network_of`, `coauthor_distances`, `introduction_paths`); `matcher.introduce`, `matcher.assemble_team`; `POST /api/collab/team/`, `GET /api/collab/searches/<id>/introduction/<username>/` |
| Collaboration counts, harm checks, readiness to widen the scope | `web/backend/apps/collab/evaluation.py` (run by the `collab-daily` task and `run_analytics.collect_collaboration`); `collab_evaluation` command |
| Corrections to a call's slots | `web/backend/apps/collab/views.py` (`POST /api/collab/calls/<id>/slot-feedback/`), model `SlotFeedback` |
| The Team fit line on a grant card | `web/app/src/components/portal/collab/team-fit-line.tsx`, mounted by `GrantRow` in `opportunities-section.tsx`; types and client in `web/app/src/lib/portal/collab/` |

## Backend — billing, admin, integrations, ingestion

| Task | Path |
|---|---|
| Entitlements (the single read path) | `web/backend/apps/billing/entitlements.py` |
| Tiers, pricing, add-ons, seats, periods | `web/backend/apps/billing/{tiers,pricing,addons,seats,seat_sync,period,services}.py` |
| Standing up an org's rows (lab or department, plan inactive) | `create_lab_workspace` / `create_department_workspace` in `web/backend/apps/billing/services.py`; sign-up only ever calls `provision_workspace(user, "personal")` |
| Platform-admin API | `web/backend/apps/adminpanel/` |
| Discord identity & lab linking | `web/backend/apps/integrations/models.py`, `services/resolve.py` (the single ORM boundary) |
| Discord servers, lab/department bindings, channel routes; `/activate-department` | `DiscordGuildLink` / `DiscordTargetBinding` / `DiscordChannelRoute` in `web/backend/apps/integrations/models.py`; `services/lab_activation.py` (lab and department codes); `mylo/linking.py` + `mylo/bot/cogs/{link,setup}.py`; test builders in `apps/integrations/testing.py` |
| Discord OAuth, API calls, outbox | `web/backend/apps/integrations/services/` |
| Slack (ambient Plan 11): events, buttons, install, link codes, outbox | `web/backend/apps/integrations/slack_views.py`, `services/slack_events.py`, `slack_link.py`, `slack_outbox.py`, `slack_api.py`; `services/slack_resolve.py` is Slack's single ORM boundary; the adapter is `apps/ambient/adapters/slack.py` |
| Microsoft Teams (ambient Plan 11): Bot Framework endpoint, token checks, outbox | `web/backend/apps/integrations/teams_views.py`, `services/teams_auth.py` (RS256 against Microsoft's keys), `teams_events.py`, `teams_outbox.py`, `teams_api.py`; `services/teams_resolve.py` is its ORM boundary; the adapter is `apps/ambient/adapters/teams.py` |
| Reports on Slack for Slack-only readers and labs | `web/backend/apps/content/slack_reports.py`, command `send_slack_reports` (in `ops/nightly/manual_all.py`) |
| Where the OAuth `redirect_uri` comes from (and why it must not vary) | `_redirect_uri` in `web/backend/apps/integrations/services/oauth.py`, `DISCORD_CALLBACK_ORIGIN` in `web/backend/config/settings.py`; print what to register with `manage.py discord_check` |
| The portal's "link with a code" panel (join → copy command → wait) | `ActivationCodePanel` in `web/app/src/components/portal/sections/profile-section.tsx`; the command and invite come from `DiscordActivationCodeView` |
| Paper source scrapers | `web/backend/apps/scraper/sources/`, `ingest.py`, `window.py` |
| Open-source grants/conferences collector (vendored) | `web/backend/apps/scraper/collect/` — `runner.py` stages, `grants/`, `conferences/`, `core/` |
| Collector adapters (5 live grant, 6 conference) | `web/backend/apps/scraper/collect/{grants,conferences}/adapters/` |
| dblp venue registry (venue identity, CORE ranks) | `web/backend/apps/scraper/collect/conferences/registry/` |
| Collector record → `ContentItem` mapping, deadline/expiry rules | `web/backend/apps/scraper/collect/mapping.py` |
| Collector upsert, prune, embed | `web/backend/apps/scraper/collect/ingest.py` |
| Verified LLM description extraction (schema, validators, repair loop) | `web/backend/apps/scraper/collect/extract.py` |
| Collector data root (SQLite stores, HTTP cache, raw payloads, extraction checkpoint) | `web/backend/apps/scraper/collect/paths.py` defines it; the data lives in gitignored `data/collect/` at the repo root. Anchored to the checkout, never to the CWD — the container runs at `/app` and a host shell may not |
| Fellowship eligibility rule engine (deterministic, prose → constraints) | `web/backend/apps/scraper/eligibility/` |
| Illinois Fellowship Finder scraper + ingest | `web/backend/apps/scraper/fellowships/` (`illinois.py` scrapes, `records.py`/`ingest.py` upsert) |
| Embedder (CPU / CUDA) | `web/backend/apps/scraper/embedding.py` |
| External DOI / arXiv / URL resolver | `web/backend/apps/scraper/resolver.py` |
| LLM client | `web/backend/apps/core/llm.py` |
| TypeSafe System One client (typed decisions with calibrated probabilities) | `web/backend/apps/core/systemone.py` — every call counted in the LLM ledger |
| Transactional email (send one) | `web/backend/apps/core/mail/messages.py` (`send_email`, `app_url`, the `TEMPLATES` registry) |
| Email transport & Django backend | `web/backend/apps/core/mail/{client,backend}.py` — Resend over stdlib urllib; wired as `EMAIL_BACKEND` so `django.core.mail` routes through it |
| Email templates (HTML + text pairs) | `web/backend/templates/email/` — `base.html`, `_button.html`, and one pair per entry in `TEMPLATES` |
| LLM call / token ledger | `web/backend/apps/core/{models,llm_usage}.py` |
| Health endpoint, exactly-one-FK helper | `web/backend/apps/core/{views,db}.py` |
| Django settings / URLs / Celery | `web/backend/config/` |

## Host runners & operations

| Task | Path |
|---|---|
| Full-stack start/stop | `ops/mycelium` (start/stop/restart/status/migrate — wipes frontend caches, waits for the API, applies migrations, restarts Mylo), `Makefile` (`make up`/`down`/`status`), `compose.yaml`, `ops/compose.gpu.yaml` |
| Nightly research run | `ops/nightly/manual_all.py` (fired by `mylo-daily.timer`) |
| On-demand re-score everyone | `ops/nightly/manual_mylo.py` |
| Illinois fellowship scrape → import (host, Playwright) | `ops/scrapers/scrape_fellowships.py` |
| Per-stage manual runners | `ops/nightly/` |
| Mylo Discord bot & run observability | `mylo/` — `bot/`, `config.py`, `reporting.py`, `analytics.py`, `runstate.py`, `linking.py`, `listening.py` |
| Hearing a conversation and handing it to the ledger | `mylo/bot/cogs/listen.py` (Stage A: DMs, mentions, reactions on Mylo's posts, edits, deletions, the *Tell Mylo about this* action; Stage B behind `MYLO_LISTEN_ENABLED` **and** the Message Content intent, both off) + `mylo/listening.py` |
| Turning listening on for a server, excluding channels, the pinned notice | `/setup`'s Listening section in `mylo/bot/cogs/setup.py`; one person's own opt-in is `/mylo listening` in `mylo/bot/cogs/mylo_commands.py` |
| systemd units | `ops/systemd/` — `mycelium.service`, `mycelium-update.service`, `mylo-daily.{service,timer}`, `mylo-bot.service`; installed by `ops/mycelium install-service` |
| Gateway routing | `web/infra/nginx/default.conf` |
| Env contract | `.env.example`, `.env-mylo.example` |
| Instance configuration (`mycelium.toml`: profiles, billing switch, limits, sign-up, email, features, nightly budgets) | `web/backend/config/instance.py` (keys, profiles, merge, render); template `mycelium.example.toml`; tests `web/backend/apps/core/test_instance_config.py` |
| Onboarding load test | `ops/loadtest/loadtest.py`, `ops/loadtest/loadtest_interests.py`; guide in [`loadtest.md`](loadtest.md) |
| Retrieval evaluation | `eval/` — `run.py`, `report.py`, `collections.toml`, `configs/`, `harness/`; results in `eval/results/`, guide in [`evaluation.md`](evaluation.md) |
| Frozen eval subset + embedding-matrix slicing | `eval/freeze_subset.py`, `eval/harness/subset.py`; the id list is `eval/subsets/*.txt` (committed) |
| Candidate ladder stages (SPLADE, ColBERT, cross-encoder, LLM rerank) — **not production** | `eval/harness/{ladder,neural,llm_rerank}.py`, encoded by `eval/encode_ladder.py`; measured in `EXP-2026-08-008` |
| TypeSafe pointwise rerank arms (`typesafe_noul`, `typesafe_score`) — **not production** | `eval/harness/typesafe_rerank.py`, configs `eval/configs/typesafe_*.toml`; measured in `EXP-2026-09-004` |
| Paired significance testing (bootstrap intervals, sign test, query-length strata) | `eval/harness/stats.py` — shared by `EXP-2026-08-009` and `EXP-2026-08-010`; never re-implement it per experiment |
| LLM query expansion for the reranker (candidate, refuted) | `eval/expand_queries.py`; cached at `data/eval-cache/expansions/`, measured in `EXP-2026-08-010` |
| Pool contrast against the **production** store (not LongEval) | `docs/research/experiments/EXP-2026-08-013-production-pool-contrast/code/` — `production_pool.py` builds the union-pool variants on top of the deployed `_build_pool`/`fuse_interest`; `run.py` scores them against the real `ContentItem` rows over a compose `postgres`. Nothing under `apps/content` is modified |
| Research record (experiments, claims, figures) | `docs/research/` — start at [`research/README.md`](research/README.md) |
| Research-record tooling | `ops/research/` — `new_experiment.py`, `validate_research.py`, `generate_index.py`, `build_figures.py`, `manifest.schema.json`; driven by the root `Makefile` |
| First-time setup (`make setup [PROFILE=…]`: picks a profile and writes `mycelium.toml`, writes `.env`, builds, migrates, first admin) | `ops/setup/bootstrap.py` |
| Changing the instance configuration (`ops/mycelium config` / `make config ARGS=…`: profiles, init, show, explain, get, set, unset, validate, diff, recommend; all `--json`) | `ops/setup/config_cli.py`; tests `web/backend/apps/core/test_config_cli.py` |
| Admin bootstrap (`make admin NAME=…`) | `ops/setup/create_admin.py` |
| Every root command | `Makefile` (`make help`) |
| README banner (generated, committed) | `docs/assets/header.svg`, written by `ops/readme/make_header.py` from `web/art/logo/logo-colored.svg`; re-run it when the logo or the README's first sentence changes |
| README screenshots (committed) | `docs/assets/screenshot-{hero,report,feeds}.webp`, captured from the landing dev server by `ops/readme/screenshots.py` |

## Management commands

All under `web/backend/apps/*/management/commands/`. Run with
`uv run --project web/backend python web/backend/manage.py <name>`.

| Command | Purpose |
|---|---|
| `run_daily_suggestions` | Daily paper scan + rank for users, labs, projects |
| `run_daily_opportunities` | Nightly whole-corpus rank of grants / conferences / fellowships for users, labs, projects |
| `run_refitting` | On-demand re-score that also re-sends every item to the model |
| `generate_daily_briefing` | Write each user's and lab's briefing |
| `send_daily_discord_reports` | DM the personal PDF report |
| `send_lab_digests` | Post a lab's summary + report PDF |
| `resend_user_report` | Re-render one person's report and DM it again (`--user`) |
| `grant_institution` | Place an account at an institution its email cannot prove (`--user`, `--institution`, `--actor`, `--revoke`); the name must exist in the affiliation directory |
| `repost_lab_report` | Re-render one lab's report and re-post it (`--lab`) |
| `render_sample_report` | Render a sample report PDF from synthetic data, for reviewing its formatting (`--kind personal\|lab`) |
| `run_reminder_tick` | Fire due reminders |
| `prune_opportunities` | Delete expired listings; `--stale-only` also removes dateless conferences the collector has stopped listing, `--dry-run` reports without deleting |
| `prune_briefings` | Delete briefings past `BRIEFING_RETENTION_DAYS` |
| `project_declared_edges` | Mirror declared profiles, labs, and projects into the knowledge graph and prune orphaned private concepts (no arguments: every subject, which is also the backfill); `--user`, `--lab`, or `--project` for one |
| `extract_requirement_slots` | Read what funding calls ask a team to bring (nightly within `COLLAB_SLOTS_NIGHTLY_CAP`; `--content` for one, `--limit`) |
| `annotate_team_fit` | Write the team-fit line on grants already shown to each target, without re-scoring (`--user`, `--lab`) |
| `facet_author_works` | Read people's own imported papers into facets and demonstrated edges (nightly within `KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP`; `--user` for one person now, `--limit`, `--lookups`) |
| `sweep_ambient_retention` | Delete ambient message references past their window (`--dry-run` reports without deleting); observations are never touched |
| `run_analytics_report` | Measure the run: metrics JSON + analytics PDF for the Discord summary |
| `drain_discord_outbox`, `reconcile_discord` | Deliver queued Discord messages / reconcile guild state |
| `discord_check` | Print the OAuth redirect URIs to register in the Developer Portal, and how that origin resolved |
| `scan_literature` | Paper ingestion only |
| `collect_opportunities` | Open collector end to end (collect → map → ingest → extract → embed) for grants/conferences, in-container; nightly invocation is `--new-only --no-prune` |
| `refresh_dblp_registry` | Refresh the dblp venue registry cache the conference resolve stage joins against (weekly cadence, self-throttled from `ops/nightly/manual_all.py`; must run before collection) |
| `reset_opportunities` | ORM-level wipe of grant / conference items before a re-populate (`--types`); leaves fellowships, papers, users, and saves alone |
| `annotate_member_fit` | Backfill the "who is this for?" layer |
| `recompute_project_profiles` | Rebuild project team vectors |
| `rebuild_content_deadlines`, `backfill_project_seen`, `backfill_slate_size`, `dedupe_content_papers` | Backfills |
| `run_billing_tick`, `reconcile_seats` | Billing period roll / seat reconciliation |
| `embedding_device` | Report and benchmark the embedding device |
| `llm_check` | LLM reachability pre-flight |
| `typesafe_check` | TypeSafe System One reachability check (one fixed question, never database text) |
| `send_test_email` | Send one email through the real stack to check the transport (`--to`, `--template`) |
| `high_signal_shadow` | Shadow-run the high-signal alert rule |
| `create_admin`, `seed_demo`, `loadtest_purge` | Ops utilities |
| `seed_fsu_sc` | Simulated FSU Dept. of Scientific Computing + PULSE Lab (public roster names, non-deliverable `@fsu-sc.mycelium.invalid` emails); the lab sits in the department but stays off its plan, on its own Lab plan |

## Documentation

| Path | What |
|---|---|
| `docs/purpose.md`, `docs/goals.md`, `docs/styles.md` | Canonical product direction |
| `docs/architecture.md` | Stack, boundaries, data ownership, configuration |
| `docs/configuration.md` | Operator guide to `mycelium.toml`: profiles, layers, every section, common changes |
| `docs/api-contract.md` | HTTP surface |
| `docs/repo-map.md` | This file |
| `docs/discord-integration.md` | Discord identity & lab linking reference |
| `docs/loadtest.md` | Onboarding load-test guide |
| `docs/research-audit.md` | Independent audit of the ranking and agentic layers; its C-claims and W-workstreams are tracked live in `docs/research/` |
| `docs/evaluation.md` | How to run the retrieval harness, the leaderboard, qrels provenance, and the claims boundary |
| `docs/research/` | The research record — experiments, claims ledger, decisions, open questions, figures, paper plan |
| `docs/skills/` | Canonical agent guidance — start at `skills/index.md` |
| `docs/changelog.md` | Append-only project history |
| `docs/plans/` | Implementation plans (working documents, deleted when shipped); `plans/ambient-profile/` is the sequenced series for the self-maintaining profile and `plans/collaboration-network/` the one for collaborator matching; both build on the shared knowledge core (`apps/knowledge`, shipped as plans CN-01 and CN-02; `apps/collab` since CN-03). Start at each `README.md` |
