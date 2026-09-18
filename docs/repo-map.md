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
| A marketing page | `web/landing/src/pages/*.astro` — five pages: `index`, `product`, `pricing`, `about`, `contact` |
| Landing copy & capability claims | `web/landing/src/data/{landing,product,pricing,pricingComparison,site}.ts` |
| Landing components | `web/landing/src/components/{landing,site,pricing}/` |
| Landing feed preview — the four cards, mirroring the app's feeds | `web/landing/src/components/landing/feed/{Paper,Grant,Fellowship,Conference}Card.astro` + shared `ClusterRow`, `ActionBar`, `Reason`, `SourceRow`, `Glyph`; `FeedCard.astro` picks by kind, `LiveFeed.astro` supplies the section header, search bar and filter rail |
| Landing feed preview content & shapes | `web/landing/src/data/feed-preview.ts` — fictional content, real field set; carries **no** verdict or position, because the app's cards draw none |
| Landing feed preview styles (plain-CSS port of the app's card classes) | `web/landing/src/styles/feed-card.css` — global, imported once by `LiveFeed.astro` |
| Section backgrounds (tinted ground + botanical motif) | `web/landing/src/components/site/SectionGround.astro` — pick a different motif per section; leave plain sections between |
| The motif artwork (roots, moss overhang, leaf vine, canopy, spores, filaments) | `web/landing/src/components/site/motifs/` |
| Landing styles, scroll reveals | `web/landing/src/styles/global.css` (rules) + the two inline scripts in `web/landing/src/layouts/PublicLayout.astro` (arming flag + IntersectionObserver); no framework JS |
| Artwork masters & sync | `web/art/`, `web/scripts/sync-art-assets.mjs` (derivatives are git-ignored) |
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
| Which sections a scope offers (and the redirect when it doesn't) | `web/app/src/lib/portal/nav.ts` + `web/app/src/components/portal/scope-guard.tsx`; icons resolved in `portal/nav-icon.tsx`. A department scope has **no research feeds** — there is no department `MatchTarget` |
| The active workspace in the URL | `SCOPE_PARAM` / `routeWithScope` in `web/app/src/lib/portal/routes.ts` — `?ws=<lab-slug\|dept-id>`; the URL wins, `localStorage` is only the default for a bare entry |
| Shared card primitives | `web/app/src/components/portal/primitives/` — `card`, `match-card`, `cluster-badge`, `hidden-by-filters`, `pill`, `section-header`, `feed-search-bar`, `feed-sentinel`, `markdown-prose`, `modal`, `editor-modal`, `recommended-for`, `info-popover`, `deadline-list`, `source-footer` |
| A card's judgement | **The app shows none.** There is no percent match, no per-theme position, and no verdict chip anywhere in the app UI. The backend still computes and stores a verdict and a slate position, and the API still serves both (`verdict`, `position`, `position_of`), so restoring a display is a frontend-only change; the printed report (`daily_report_pdf.py`), the Discord digest and the briefing still read them |
| The rows a feed's filter rail took out | `web/app/src/components/portal/primitives/hidden-by-filters.tsx`; mounted after the card list on the grants, conferences and fellowships feeds |
| A feed card's theme badges (attributed cluster + "Also…") | `ClusterRow` in `web/app/src/components/portal/primitives/cluster-badge.tsx`; rendered under the title by every feed card, not on the rail |
| A feed card's Deadlines button + dropdown (alerts per round) | `web/app/src/components/portal/primitives/deadline-list.tsx` (`DeadlineMenu`) |
| A feed card's source row + "View …" button | `web/app/src/components/portal/primitives/source-footer.tsx` (`SourceRow`, `ViewLink`) |
| The report's ranked entry (title, insight, note, match rail, deadline strip) | `web/app/src/components/portal/primitives/report-entry.tsx`; its print half is `_entry_row` in `web/backend/apps/content/daily_report_pdf.py` |
| Decorative motion (vines, threads, seedlings, ring sweep) | `web/app/src/components/portal/motion/` (reduced-motion + in-view-once hooks), `portal/leaf-vine.tsx`, keyframes in `web/app/src/app/globals.css` |
| Feed card scroll entrance (predictive, fires ahead of the reader) | `web/app/src/components/portal/motion/reveal-on-scroll.tsx` |
| Workspace background growth, per section | `web/app/src/components/portal/motion/section-ground.tsx`, mounted in `portal/workspace-shell.tsx` |
| Affiliation picker (the combobox behind every "Institution" / "Affiliation" field) | `web/app/src/components/ui/institution-picker.tsx`; search + address matching in `web/app/src/lib/institutions.ts`; mounted by onboarding step 1, `profile-editor-modal.tsx`, `account-section.tsx`, and `CreateDepartmentModal` in `labs-section.tsx`. Typed text is always the value — there is no "Custom" mode to enter |
| The affiliation directory itself (~10.3k universities, national labs, institutes) | `web/app/public/data/institutions.json`, built by `web/scripts/build-institutions.mjs` (`npm run institutions`) from Hipolabs' list plus `web/scripts/data/research-institutions.json` (curated institutes + typed aliases). Served at `/data/`, which needs its own nginx block |
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
| Invite-only sign-up gate | `web/backend/apps/accounts/signup_gate.py` |
| Join invitations (emailed to one address, or a share link with a use budget + expiry) | `web/backend/apps/accounts/invites.py`, models `OrgInvite` / `OrgInviteRedemption`; `create_invites` + `screen_address` are the batch path (≤15 addresses, per-address refusals) |
| Invite → sign-up, end to end, both org kinds | `web/backend/apps/accounts/tests/test_invite_signup_flow.py` |
| Email verification (the six-digit code that activates an account) | `web/backend/apps/accounts/email_verification.py`, model `EmailVerification` |
| Password reset by emailed link | `web/backend/apps/accounts/password_reset.py` |
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
| The report body's markdown grammar, stated once for both renderers | `report_grammar.py` — `[P#]` citations, `[S:path]` state markers, labelled beats, the code-rendered references block |
| Deterministic project matchers (no model writes a number) | `matchers/` — `timeline.py` (can this project make that deadline), `overlap.py` (does this threaten the claim), `blockers.py` (does this unblock), `known_literature.py` (does the reader already have it, or write it), `team_gap.py` (does the call need somebody the team lacks), `similarity.py` (raw cosine, never RRF) |
| Which findings become alerts, and how few | `alerts.py` (five triggers, daily cap, once-ever constraint, the `PROJECT_ALERTS_ENABLED` gate), model `ProjectAlert`; command `evaluate_project_alerts` |
| The one DM a weekly-cadence reader gets between Mondays | `urgent_alerts.py` — opt-in, weekdays only, a moved deadline on a saved item inside their buffer, keyed on the alert so it is sent once ever |
| How an alert is said on each surface | `alert_report.py` — the "Needs your attention" section, the Discord lines, the bell notification |
| One run's numbers (volume, matched, entered, by category/project/theme, deadline horizon) | `report_stats.py` — derived from the finished `ReportData`, stored on `DailyBriefing.stats`, read back by every surface |
| The Discord post's shape (overview, statistics, Discord's size limits) | `discord_embeds.py` — `personal_report_embed`, `lab_post_embed`, `fit_embed` |
| Who gets a Discord push today, and at what local hour | `delivery.py` — `push_kinds` (the cadence matrix), `send_time`/`local_today`, and every dedupe key. Cadence governs push only; the nightly run and the web app are unchanged by it |
| Nightly run analytics | `run_analytics.py`, `analytics_report_pdf.py`, `management/commands/run_analytics_report.py` |
| Reminders | `reminders.py`, `reminders_tick.py`, `reminders_views.py`, `reminders_discord.py`, `reminders_announce.py`, `reminder_access.py` |
| Deadline projection | `deadlines_projection.py` |
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
| Where a person's actual words live (and for how long) | `web/backend/apps/ambient/buffer.py` — Redis only, per-message TTL, dropped explicitly once a window is read; a source can shorten the window but never lengthen it |
| The id-only pointer beside it (no body, ever) | `web/backend/apps/ambient/models.py` (`RawMessageRef`) — the window index and the handle an edit or deletion is reconciled through |
| Recording one message: eligibility, hash, buffer, reference, repeat collapse | `web/backend/apps/ambient/ingest.py` (`record`, `IncomingMessage`); normalisation for the repeat hash in `text.py` |
| The durable record — what Mylo understood, in Mylo's own words | `web/backend/apps/ambient/models.py` (`Observation`); six understanding kinds, six forces, subject, visibility, supersession. **No quote column** |
| A person's own verdict on an observation (the labels the feature is judged by) | `web/backend/apps/ambient/models.py` (`ObservationFeedback`) — append-only; a correction is a new row |
| Something was removed, so these things must be recomputed | `web/backend/apps/ambient/models.py` (`Retraction`) |

## Backend — billing, admin, integrations, ingestion

| Task | Path |
|---|---|
| Entitlements (the single read path) | `web/backend/apps/billing/entitlements.py` |
| Tiers, pricing, add-ons, seats, periods | `web/backend/apps/billing/{tiers,pricing,addons,seats,seat_sync,period,services}.py` |
| Standing up an org's rows (lab or department, plan inactive) | `create_lab_workspace` / `create_department_workspace` in `web/backend/apps/billing/services.py`; sign-up only ever calls `provision_workspace(user, "personal")` |
| Platform-admin API | `web/backend/apps/adminpanel/` |
| Discord identity & lab linking | `web/backend/apps/integrations/models.py`, `services/resolve.py` (the single ORM boundary) |
| Discord OAuth, API calls, outbox | `web/backend/apps/integrations/services/` |
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
| Full-stack start/stop | `scripts/mycelium` (start/stop/restart/status/migrate — wipes frontend caches, waits for the API, applies migrations, restarts Mylo), `run.py`, `compose.yaml`, `compose.gpu.yaml` |
| Nightly research run | `manual_all.py` (fired by `mylo-daily.timer`) |
| On-demand re-score everyone | `manual_mylo.py` |
| Illinois fellowship scrape → import (host, Playwright) | `scrape_fellowships.py` |
| Per-stage manual runners | `utils/manual/` |
| Mylo Discord bot & run observability | `mylo/` — `bot/`, `config.py`, `reporting.py`, `analytics.py`, `runstate.py`, `linking.py` |
| systemd units | `mycelium.service`, `mycelium-update.service`, `mylo-daily.{service,timer}`, `mylo-bot.service` |
| Gateway routing | `web/infra/nginx/default.conf` |
| Env contract | `.env.example`, `.env-mylo.example` |
| Onboarding load test | `loadtest.py`, `loadtest_interests.py`; guide in [`loadtest.md`](loadtest.md) |
| Retrieval evaluation | `eval/` — `run.py`, `report.py`, `collections.toml`, `configs/`, `harness/`; results in `eval/results/`, guide in [`evaluation.md`](evaluation.md) |
| Frozen eval subset + embedding-matrix slicing | `eval/freeze_subset.py`, `eval/harness/subset.py`; the id list is `eval/subsets/*.txt` (committed) |
| Candidate ladder stages (SPLADE, ColBERT, cross-encoder, LLM rerank) — **not production** | `eval/harness/{ladder,neural,llm_rerank}.py`, encoded by `eval/encode_ladder.py`; measured in `EXP-2026-08-008` |
| TypeSafe pointwise rerank arms (`typesafe_noul`, `typesafe_score`) — **not production** | `eval/harness/typesafe_rerank.py`, configs `eval/configs/typesafe_*.toml`; measured in `EXP-2026-09-004` |
| Paired significance testing (bootstrap intervals, sign test, query-length strata) | `eval/harness/stats.py` — shared by `EXP-2026-08-009` and `EXP-2026-08-010`; never re-implement it per experiment |
| LLM query expansion for the reranker (candidate, refuted) | `eval/expand_queries.py`; cached at `data/eval-cache/expansions/`, measured in `EXP-2026-08-010` |
| Pool contrast against the **production** store (not LongEval) | `docs/research/experiments/EXP-2026-08-013-production-pool-contrast/code/` — `production_pool.py` builds the union-pool variants on top of the deployed `_build_pool`/`fuse_interest`; `run.py` scores them against the real `ContentItem` rows over a compose `postgres`. Nothing under `apps/content` is modified |
| Research record (experiments, claims, figures) | `docs/research/` — start at [`research/README.md`](research/README.md) |
| Research-record tooling | `scripts/research/` — `new_experiment.py`, `validate_research.py`, `generate_index.py`, `build_figures.py`, `manifest.schema.json`; driven by the root `Makefile` |
| Admin bootstrap | `create_admin.py` |

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
| `repost_lab_report` | Re-render one lab's report and re-post it (`--lab`) |
| `render_sample_report` | Render a sample report PDF from synthetic data, for reviewing its formatting (`--kind personal\|lab`) |
| `run_reminder_tick` | Fire due reminders |
| `prune_opportunities` | Delete expired listings; `--stale-only` also removes dateless conferences the collector has stopped listing, `--dry-run` reports without deleting |
| `prune_briefings` | Delete briefings past `BRIEFING_RETENTION_DAYS` |
| `run_analytics_report` | Measure the run: metrics JSON + analytics PDF for the Discord summary |
| `drain_discord_outbox`, `reconcile_discord` | Deliver queued Discord messages / reconcile guild state |
| `discord_check` | Print the OAuth redirect URIs to register in the Developer Portal, and how that origin resolved |
| `scan_literature` | Paper ingestion only |
| `collect_opportunities` | Open collector end to end (collect → map → ingest → extract → embed) for grants/conferences, in-container; nightly invocation is `--new-only --no-prune` |
| `refresh_dblp_registry` | Refresh the dblp venue registry cache the conference resolve stage joins against (weekly cadence, self-throttled from `manual_all.py`; must run before collection) |
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
| `docs/api-contract.md` | HTTP surface |
| `docs/repo-map.md` | This file |
| `docs/discord-integration.md` | Discord identity & lab linking reference |
| `docs/loadtest.md` | Onboarding load-test guide |
| `docs/research-audit.md` | Independent audit of the ranking and agentic layers; its C-claims and W-workstreams are tracked live in `docs/research/` |
| `docs/evaluation.md` | How to run the retrieval harness, the leaderboard, qrels provenance, and the claims boundary |
| `docs/research/` | The research record — experiments, claims ledger, decisions, open questions, figures, paper plan |
| `docs/skills/` | Canonical agent guidance — start at `skills/index.md` |
| `docs/changelog.md` | Append-only project history |
| `docs/plans/` | Implementation plans (working documents, deleted when shipped); `plans/ambient-profile/` is the sequenced series for the self-maintaining profile, start at its `README.md` |
| `docs/chats/`, `docs/Resources/` | Source conversations and the project brief |
