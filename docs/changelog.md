# Mycelium Change Log

Log format version: `1.0`

This log records broad project changes so humans and agents can recover context across sessions. Entries are append-only. Keep summaries brief, non-technical, and focused on the outcome or motivation of the work.

## Schema

| Field | Rule |
| --- | --- |
| Timestamp | UTC ISO 8601 timestamp, such as `2026-06-01T15:58:33Z`. |
| Action | One of `CREATED`, `MODIFIED`, `DELETED`, `REVIEWED`, `EXECUTED`, `RENAMED`, `MOVED`, `CORRECTED`, or `SUMMARIZED`. |
| Correlation ID | `YYYYMMDD-topic-slug`, using the local session date and a short task slug. |
| Summary | Brief plain-language outcome or motivation. Do not include line-level implementation detail. |

## Entries

| Timestamp | Action | Correlation ID | Summary |
| --- | --- | --- | --- |
| 2026-06-01T15:58:33Z | CREATED | 20260601-global-changelog-schema | Added a structured changelog format so future project updates stay consistent and auditable. |
| 2026-06-01T15:59:27Z | MODIFIED | 20260601-git-commit-rules | Clarified that every completed project change should be committed, including small documentation and rule updates. |
| 2026-06-01T16:05:48Z | CREATED | 20260601-landing-pages-plan | Added a frontend shell plan for the public landing pages and hero direction. |
| 2026-06-01T17:11:30Z | MODIFIED | 20260601-landing-frontend-shell | Implemented the public landing shell with hero, sections, navigation, route pages, and shared layout. |
| 2026-06-01T17:25:00Z | MODIFIED | 20260601-landing-hero-layout | Made the front-page hero image full-bleed edge to edge and removed rounded corners and scroll hint. |
| 2026-06-01T22:41:29Z | MODIFIED | 20260601-landing-hero-image | Restored the real hero artwork in the landing public assets and removed the front-page tint overlay so Mylo displays more clearly. |
| 2026-06-01T23:19:45Z | CREATED | 20260601-login-system-plan | Added a plan for Django-backed login, a proper Next.js login portal, and authenticated workspace gating. |
| 2026-06-01T23:45:00Z | MODIFIED | 20260601-login-routing | Routed public login handoff to the app portal and reserved lab dashboard URL shape in nginx and Next.js. |
| 2026-06-01T23:52:00Z | CREATED | 20260601-django-session-auth | Added Django session auth endpoints with CSRF, CORS credentials, and tests for login, me, and logout. |
| 2026-06-02T00:02:00Z | CREATED | 20260601-login-portal | Built the Next.js sign-in portal with CSRF-aware session login and a documented auth API contract. |
| 2026-06-02T00:06:00Z | MODIFIED | 20260601-workspace-gating | Gated the authenticated workspace behind session checks with a placeholder shell and sign-out. |
| 2026-06-02T00:12:00Z | CREATED | 20260601-lab-permissions-foundation | Added lab, membership, audit, and permission helpers with admin registration and access tests. |
| 2026-06-02T00:20:00Z | CORRECTED | 20260601-login-hydration | Suppressed root layout hydration warnings when browser extensions alter the document body before React loads. |
| 2026-06-02T00:30:00Z | CORRECTED | 20260601-login-hydration | Moved layout classes off the document body and strip extension-injected classes before hydration to stop login page mismatches. |
| 2026-06-02T01:10:00Z | CORRECTED | 20260601-login-fetch-and-form | Fixed login API routing through the Next proxy, blocked GET credential leakage, and sanitized accidental query-string passwords. |
| 2026-06-02T19:19:05Z | MODIFIED | 20260602-connected-workspace-section | Updated the front-page workspace section with connected workspace artwork, scaled feature cards, and responsive landing content. |
| 2026-06-10T17:22:20Z | CREATED | 20260610-project-brief-markdown | Added a Markdown version of the Mycelium project brief alongside the source PDF. |
| 2026-06-10T19:22:37Z | CREATED | 20260610-grants-prototype-ingest | Added a prototype grants ingest utility for sampling public funding sources into normalized CSV files. |
| 2026-06-12T18:00:00Z | MODIFIED | 20260612-pricing-page-tiers | Replaced the pilot pricing placeholder with Spore, Mycelium Lab, and Canopy tiers plus Mylo Bot add-ons on a light-themed layout.
| 2026-06-12T22:50:00Z | MODIFIED | 20260612-pricing-comparison-table | Added a full plan comparison table below the pricing trial footer on the public pricing page.
| 2026-06-12T23:00:00Z | MODIFIED | 20260612-pricing-table-addons | Corrected the pricing comparison table to match the reference layout, clarified Discord and Slack add-ons, and moved the trial footer below the table.
| 2026-06-13T03:45:00Z | MODIFIED | 20260612-dev-gateway-routing | Routed local dev and Docker through port 9911 with a dev gateway, fixed Compose workspace linking, and aligned CORS origins for single-origin browsing. |
| 2026-06-14T04:17:40Z | MODIFIED | 20260614-goals-roadmap-alignment | Aligned the goals checklist with the five-month first-draft roadmap, including phased milestones, build sequence rules, and deferred later-phase features. |
| 2026-06-14T04:25:00Z | MODIFIED | 20260614-goals-weekly-breakdown | Restructured the goals document as a 20-week checklist with per-week milestones aligned to the development roadmap. |
| 2026-06-20T20:33:07Z | REVIEWED | 20260620-p0-scaffold-verify | Verified the baseline scaffold end to end: the Nginx gateway serves landing, app, and backend on port 9911, the health and login/logout/me endpoints pass against the live backend, and tests and lint are green. |
| 2026-06-20T20:33:07Z | MODIFIED | 20260620-p0-pgvector | Enabled the pgvector extension through a backend dependency and database migration so embedding columns can be added later for relevance scoring without a disruptive mid-sprint migration. |
| 2026-06-20T20:33:07Z | MODIFIED | 20260620-p0-compose-stability | Hardened the Docker Compose dev stack so frontend and backend dependency installs no longer race on shared mounts and the Celery worker starts cleanly. |
| 2026-06-20T20:56:24Z | CREATED | 20260620-planner-source-cards | Added the planning-agent briefing to docs and the first planner building block: source cards that hold each lab graph's introspected routing truth, declared join keys, safety limits, and content-probe expectations, with a card-consistency validator. |
| 2026-06-20T20:59:21Z | CREATED | 20260620-planner-discovery | Added planner discovery and liveness: a content probe that confirms each graph holds expected labels and enough nodes, a per-probe timeout guard so a hung backend cannot stall planning, and a per-request live-source view cached briefly. |
| 2026-06-20T21:01:12Z | CREATED | 20260620-planner-plan-schema | Added the machine-readable plan schema the planner emits: target sources, sub-questions with required traversal limits and routing rationale, join keys, unsupported parts, assumptions, a partial flag, and the reasoning trace, plus intrinsic structural validation. |
| 2026-06-20T21:03:55Z | CREATED | 20260620-planner-self-eval-gate | Added the planner's deterministic self-evaluation gate that grades a drafted plan against the live-source view and source cards, rejecting dead targets, nonexistent entities, undeclared join keys, out-of-bounds limits, unnecessary source calls, and degenerate plans. |
| 2026-06-20T21:10:00Z | CREATED | 20260620-planner-react-loop | Added the planner's drafting seam and self-evaluating ReAct loop: a card-grounded heuristic drafter that routes only to live sources and marks gaps unsupported, plus a bounded draft-grade-revise loop that feeds gate feedback forward and degrades to an honest partial plan instead of looping forever. |
| 2026-06-20T21:12:02Z | CREATED | 20260620-planner-agent-wiring | Wired the top-level planning agent that re-probes liveness per request and drives the ReAct loop end to end, with an offline factory for tests and a lazy Neo4j inspector seam for production. |
| 2026-06-20T21:16:57Z | CREATED | 20260620-planner-evaluation | Added the planner evaluation harness that scores plans directly against a fixed, manually reviewed set of expected plans, including out-of-scope and down-source cases, with a held-out regression split. |
| 2026-06-20T21:18:32Z | MODIFIED | 20260620-planner-traceability | Closed a gate test gap for the card-consistency re-check and added an implementation-traceability appendix mapping every planning-agent failure mode to its module and test. |
