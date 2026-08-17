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
| Landing feed preview card (mirrors the app's `MatchCard`) | `web/landing/src/components/landing/FeedCard.astro` |
| Section backgrounds (tinted ground + botanical motif) | `web/landing/src/components/site/SectionGround.astro` — pick a different motif per section; leave plain sections between |
| The motif artwork (roots, moss overhang, leaf vine, canopy, spores, filaments) | `web/landing/src/components/site/motifs/` |
| Landing styles, scroll reveals | `web/landing/src/styles/global.css` (rules) + the two inline scripts in `web/landing/src/layouts/PublicLayout.astro` (arming flag + IntersectionObserver); no framework JS |
| Artwork masters & sync | `web/art/`, `web/scripts/sync-art-assets.mjs` (derivatives are git-ignored) |

## Frontend — authenticated app

| Task | Path |
|---|---|
| An app route | `web/app/src/app/app/(workspace)/<name>/page.tsx` |
| Login / signup routes | `web/app/src/app/{login,signup}/` + `web/app/src/components/auth/` |
| Portal shell, sidebar, nav, lab switcher | `web/app/src/components/portal/{portal-sidebar,portal-mobile-nav,lab-switcher,portal-context}.tsx` |
| Shared card primitives | `web/app/src/components/portal/primitives/` — `card`, `match-ring`, `match-card`, `cluster-badge`, `pill`, `section-header`, `feed-search-bar`, `feed-sentinel`, `markdown-prose`, `modal`, `editor-modal`, `recommended-for`, `info-popover`, `deadline-rounds`, `source-footer` |
| Decorative motion (vines, threads, seedlings, ring sweep) | `web/app/src/components/portal/motion/` (reduced-motion + in-view-once hooks), `portal/leaf-vine.tsx`, keyframes in `web/app/src/app/globals.css` |
| Feed card scroll entrance (predictive, fires ahead of the reader) | `web/app/src/components/portal/motion/reveal-on-scroll.tsx` |
| Workspace background growth, per section | `web/app/src/components/portal/motion/section-ground.tsx`, mounted in `portal/workspace-shell.tsx` |
| Onboarding (first run only) | `web/app/src/components/onboarding/` + route `web/app/src/app/app/onboarding/` |
| Cluster organizer | `web/app/src/components/onboarding/cluster-organizer.tsx` |
| Profile / lab edit modals | `web/app/src/components/portal/sections/{profile-editor-modal,lab-editor-modal}.tsx` |
| Overview (personal + lab) | `web/app/src/components/portal/sections/{overview-panels,mylo-report-card,mylo-found-card,lab-overview-section,lab-onboarding}.tsx`, `portal/primitives/report-summary-table.tsx` |
| Feeds: papers / grants / fellowships / conferences | `web/app/src/components/portal/sections/{research-papers-section,opportunities-section,fellowships-section,conferences-section}.tsx` |
| Feed filter rails | `web/app/src/components/portal/sections/{grant-filters,fellowship-filters,conference-filters,saves-filters}.tsx` |
| Saves & reminders | `web/app/src/components/portal/sections/{saves-section,reminders-section}.tsx`, `portal/{reminder-composer,reminder-editor,reminder-offsets-field}.tsx` |
| Save button & scope menu | `web/app/src/components/portal/sections/opportunity-bits.tsx` |
| Search UI | `web/app/src/components/portal/global-search.tsx`, `portal/sections/{search-section,search-result-card}.tsx` |
| Projects UI | `web/app/src/components/portal/sections/{projects-list-section,project-detail-section}.tsx` |
| Project page parts (identity, four-area tabs, editor, team) | `web/app/src/components/portal/projects/{project-identity,project-tabs,project-editor-modal,project-team-card,create-project-wizard}.tsx` |
| Labs / members / lab settings | `web/app/src/components/portal/sections/{labs-section,members-section,lab-settings-section}.tsx` |
| Reports page (briefing history) | `web/app/src/components/portal/sections/reports-section.tsx` |
| Billing page | `web/app/src/components/portal/sections/billing-section.tsx` |
| Admin page | `web/app/src/components/portal/sections/admin-section.tsx` |
| Notification bell | `web/app/src/components/portal/notification-bell.tsx` |
| API client, hooks, types | `web/app/src/lib/` and `web/app/src/lib/portal/{client,hooks,mutations,types}.ts` |
| Infinite reveal | `web/app/src/lib/portal/use-infinite-reveal.ts` |
| Design tokens / theme | `web/packages/config/src/theme.css` |

## Backend — identity & organization (`apps/accounts`)

| Task | Path |
|---|---|
| Users, labs, departments, memberships, roles | `web/backend/apps/accounts/models.py` |
| Session auth, CSRF, `/me`, labs, invitations, watch | `web/backend/apps/accounts/{views,urls,serializers}.py` |
| Permission rules | `web/backend/apps/accounts/permissions.py` |
| Workspace provisioning at signup | `web/backend/apps/accounts/provisioning.py` |
| Invite-only sign-up gate | `web/backend/apps/accounts/signup_gate.py` |
| Interests contract (v2 clusters) | `web/backend/apps/accounts/interests.py` |
| Profile / lab intake & synthesis | `web/backend/apps/accounts/intake/` — `synthesize.py`, `lab.py`, `clusters.py`, `agent.py` |
| Derived membership aggregates | `web/backend/apps/accounts/aggregates.py` |

## Backend — research context (`apps/research`)

| Task | Path |
|---|---|
| Projects, membership, invitations, visibility, archiving, collaboration endpoints | `web/backend/apps/research/{models,views,serializers,urls}.py` |
| Per-scope project caps | `web/backend/apps/research/limits.py` |

## Backend — matching & delivery (`apps/content`)

Files below are inside `web/backend/apps/content/`.

| Task | File |
|---|---|
| Content items, scores, saves, reminders, notifications | `models.py` |
| Scoring target (user / lab / project) | `targets.py` |
| Paper pipeline | `pipeline.py`, `interests_query.py`, `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, `suggest.py`, `clustering.py` |
| Ranking-stack seams (ORM-free ranking, swappable vector index) | `protocols.py` (`Retrievable`, `VectorIndex`), `retrieval.py` (`PgVectorIndex`) |
| Theme spread (opt-in, all defaults off) | `fusion.py` (`SpreadPolicy`, `apply_spread`, `quota_clusters`, `cap_cluster_share`, `mmr_clusters`, `cluster_relative_pass`, `combine_clusters(merge=…)`), reached via `pipeline.fuse_clusters_pool(spread=…)`; measured in `EXP-2026-08-005` |
| Grants / conferences / fellowships matching | `opportunities.py`, `fellowships.py`, `opportunity_llm.py`, `pinning.py` |
| Fellowship eligibility gates (stage ladder, prose constraints) | `fellowships.py` (`STAGE_LADDER`, `_stage_gate`, `_constraint_gates`, `derive_stage`) |
| Fellowship eligibility extracted from prose | `web/backend/apps/scraper/eligibility/constraints.py`, `web/backend/apps/scraper/fellowships/ingest.py` (`extract_fellowship_constraints`) |
| On-demand whole-corpus refit | `refitting.py` |
| Post-onboarding live match | `onboarding_match.py`, `scan_status.py` |
| Member fit ("who is this for?") | `member_fit.py`, `fanout.py` |
| Project team signal & sharing | `team_profile.py`, `collaboration.py` |
| Daily briefing (Personal + per-project parts, over each Top-25 slate) | `briefing.py`, `briefing_sections.py` |
| Top-25 slate: membership, entrant diff, "what is new" | `top_feed.py` |
| Manual re-render + re-send of one report | `report_resend.py` |
| Briefing history & retention | `models.py` (`DailyBriefing.generated_on`), `views.py` (`BriefingHistoryView`), `management/commands/prune_briefings.py` |
| Daily PDF report | `daily_report.py`, `daily_report_pdf.py`, `daily_report_send.py` |
| Report formatting sample (no database) | `management/commands/render_sample_report.py` |
| Report cover art (derived from `web/art/`) | `report_assets/` — `mylo-headshot.png`, `mycelium-logo.png`, `README.md` |
| Lab Discord digest | `lab_digest.py` |
| Nightly run analytics | `run_analytics.py`, `analytics_report_pdf.py`, `management/commands/run_analytics_report.py` |
| Reminders | `reminders.py`, `reminders_tick.py`, `reminders_views.py`, `reminders_discord.py`, `reminders_announce.py`, `reminder_access.py` |
| Deadline projection | `deadlines_projection.py` |
| Is an opportunity still worth showing (feeds + prune share it) | `liveness.py` |
| Unified search | `search.py`, `search_service.py`, `query_embedding.py` |
| High-signal alerts | `high_signal.py` |
| Read surfaces (feeds, saves, notifications) | `views.py`, `serializers.py`, `urls.py` |
| Display-time formatting shared by serializers (amounts) | `formatting.py` |
| Celery tasks & target selection | `tasks.py` |

## Backend — billing, admin, integrations, ingestion

| Task | Path |
|---|---|
| Entitlements (the single read path) | `web/backend/apps/billing/entitlements.py` |
| Tiers, pricing, add-ons, seats, periods | `web/backend/apps/billing/{tiers,pricing,addons,seats,seat_sync,period,services}.py` |
| Platform-admin API | `web/backend/apps/adminpanel/` |
| Discord identity & lab linking | `web/backend/apps/integrations/models.py`, `services/resolve.py` (the single ORM boundary) |
| Discord OAuth, API calls, outbox | `web/backend/apps/integrations/services/` |
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
| LLM call / token ledger | `web/backend/apps/core/{models,llm_usage}.py` |
| Health endpoint, exactly-one-FK helper | `web/backend/apps/core/{views,db}.py` |
| Django settings / URLs / Celery | `web/backend/config/` |

## Host runners & operations

| Task | Path |
|---|---|
| Full-stack start/stop | `run.py`, `compose.yaml`, `compose.gpu.yaml` |
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
| `scan_literature` | Paper ingestion only |
| `collect_opportunities` | Open collector end to end (collect → map → ingest → extract → embed) for grants/conferences, in-container; nightly invocation is `--new-only --no-prune` |
| `refresh_dblp_registry` | Refresh the dblp venue registry cache the conference resolve stage joins against (weekly cadence, self-throttled from `manual_all.py`; must run before collection) |
| `reset_opportunities` | ORM-level wipe of grant / conference items before a re-populate (`--types`); leaves fellowships, papers, users, and saves alone |
| `annotate_member_fit` | Backfill the "who is this for?" layer |
| `recompute_project_profiles` | Rebuild project team vectors |
| `rebuild_content_deadlines`, `backfill_project_seen`, `dedupe_content_papers` | Backfills |
| `run_billing_tick`, `reconcile_seats` | Billing period roll / seat reconciliation |
| `embedding_device` | Report and benchmark the embedding device |
| `llm_check` | LLM reachability pre-flight |
| `high_signal_shadow` | Shadow-run the high-signal alert rule |
| `create_admin`, `seed_demo`, `loadtest_purge` | Ops utilities |

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
| `docs/chats/`, `docs/Resources/` | Source conversations and the project brief |
