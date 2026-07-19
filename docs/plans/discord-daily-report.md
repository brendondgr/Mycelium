# Daily Discord PDF Report

**Status:** implemented (2026-07-19).

## What it is

Every linked, entitled, opted-in user is DM'd a **daily "Mylo Report" PDF** by the
Discord bot — a professional, brand-styled document with the day's written report,
the **top 25 articles**, the **combined top 25 grants / fellowships / conferences**
they watch, and a **full appendix** of everything Mylo found. The DM itself is a
short summary ("Mylo found 139 papers, 126 grants, 87 fellowships") with the PDF
attached.

This is the first *content* push over Discord: previously the bot only carried
deadline reminders and admin/observability. It is delivery-only — it re-describes
the recommendations the daily pipeline already wrote; it never re-scores or mutates
them.

## Eligibility

A recipient is the intersection of three gates that already exist:

1. **Entitled + active** — `apps.content.tasks.select_users` (holds
   `SCHEDULED_REPORTS`; Free accounts are on-demand and never pushed a scheduled run).
2. **Linked + reachable** — an ACTIVE `DiscordIdentity` with `dm_ok` not `False`.
3. **Opted in** — `DiscordIdentity.daily_report_opt_out` is `False` (default). The
   toggle lives on the profile **Discord card** ("Daily research report" switch) and
   flips via `POST /api/integrations/discord/daily-report`.

## Flow (the brief's ordering)

`send_daily_discord_reports` (management command → `daily_report_send.run_daily_report_send`)
runs **phased**, not interleaved:

1. **compile** every recipient's day (`daily_report.compile_report_for_user` — reuses
   `briefing`'s canonical readers so the PDF never drifts from the app feeds),
2. **render** every report to a PDF on disk in a throwaway temp dir
   (`daily_report_pdf.render_report_pdf` — reportlab, no system fonts/images),
3. **send** every PDF as a personal DM
   (`reminders_discord.send_personal_report` → `discord_api.create_message_with_attachment`),
4. **delete** the temp dir — the PDFs never linger.

A per-user failure is caught and counted; it never sinks the batch. Discord being
unreachable is a soft outcome (counted, not fatal), so it is safely the **last stage
of `manual_all.py`** (the daily `mylo-daily.timer` run), right after the briefing is
written so the PDF embeds the freshest report.

## PDF structure

Cover (recipient, date, summary table) → **table of contents** (real page numbers,
first entry = the written report) → **Your Mylo Report** (the briefing markdown) →
**Top 25 Articles** → **Top 25 Grants, Fellowships & Conferences** → **Everything
Mylo Found** (full per-category appendix). Palette is the light theme from
`docs/styles.md` (cream page, forest headings, restrained gold for deadlines).

## Key files

| Concern | File |
|---|---|
| Opt-out flag | `apps/integrations/models.py` (`DiscordIdentity.daily_report_opt_out`), migration `0004` |
| Toggle endpoint | `apps/integrations/views.py` `DiscordDailyReportView` (`/api/integrations/discord/daily-report`), resolve `set_daily_report_opt_out` / `report_recipient_user_ids` |
| Discord file upload | `apps/integrations/services/discord_api.py` `create_message_with_attachment` (multipart, `parse:[]` preserved) |
| DM send path | `apps/content/reminders_discord.py` `send_personal_report` |
| Compile | `apps/content/daily_report.py` |
| PDF render | `apps/content/daily_report_pdf.py` (reportlab) |
| Orchestration | `apps/content/daily_report_send.py` + command `send_daily_discord_reports` |
| Daily wiring | `manual_all.py` (final `CONTAINER_STAGES` entry) |
| Frontend toggle | `web/app/src/components/portal/sections/profile-section.tsx` (`DiscordCard`) + `lib/portal` hook/mutation/type |

## Verifying by hand

```
# Inspect a PDF without sending (kept in --save-dir):
python web/backend/manage.py send_daily_discord_reports --user <name> --dry-run --save-dir /tmp/mylo-reports
# Send a real DM to one linked user:
python web/backend/manage.py send_daily_discord_reports --user <name>
```
