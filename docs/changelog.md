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
