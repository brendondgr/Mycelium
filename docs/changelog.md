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
