# Delivery

Puts what was ranked in front of people, and keeps track of what they do with
it. It covers:

- the API the web app reads: the feeds, saves and ignores, search, the
  briefings, reminders, notifications and announcements;
- the daily briefing and its PDF report, and the Monday weekly;
- lab digests and Discord and Slack delivery;
- deadline reminders;
- project alerts and reflection proposals;
- opportunity announcements;
- project shares, the share fan-out, and collections.

| | |
|---|---|
| Depends on | `retrieval`, `recommendation` |
| Core | yes. The platform still calls into it: Mylo's Discord commands, project pages and the ambient ledger (see `tools/_framework/platform_imports.txt`) |
| Django app label | `delivery`; its tables keep their `content_*` names (two many-to-many tables included) |
| Exports | `read`, `service`, `events`, plus the modules the platform still imports directly (listed in `tool.py`) |
| Config | `[tools.delivery]` in `mycelium.toml`; `make config ARGS="explain tools.delivery"`. Feature switches (`features.announcements`, `features.project_alerts`, `features.high_signal`, `features.slack`) stay universal |
| Nightly stages | `run_reminder_tick` (remind), `prune_briefings` (prune), `evaluate_project_alerts` (alert), `announce_opportunities`, `announce_opportunity_updates` (announce), `generate_daily_briefing` (brief), `send_daily_discord_reports`, `send_lab_digests` (deliver), `generate_weekly_briefing`, `send_weekly_reports` (weekly) |
| API | `urls.py`, mounted at `api/` directly after `apps.research.urls`, where the include always was. Every route kept its path |

## What it wires up when loaded (`apps.py`)

- **Merge handlers.** It repoints saves, shares, seen marks, collections and
  suggestions when retrieval merges two duplicate items
  (`retrieval.items_merging`, `merge_handlers.py`).
- **Stale reminders.** It marks reminders stale when a `ContentItem` is deleted
  (Django's `pre_delete`, `signals.py`).
- **Announcement departments.** It registers the departments with
  announcements on, so recommendation scores them
  (`register_department_source`).

## What is in here

| Area | Path |
|---|---|
| Read surfaces: feeds, saves, ignores, notifications, search API | `views.py`, `serializers.py`, `urls.py`, `search_service.py` |
| Daily briefing, PDF report, Discord report, lab digest | `briefing.py`, `briefing_sections.py`, `daily_report*.py`, `lab_digest.py`, `discord_embeds.py`, `report_*.py`, `report_assets/` |
| The Monday weekly | `weekly*.py` |
| Reminders | `reminders*.py`, `reminder_access.py` |
| Project alerts, matchers, reflection | `alerts.py`, `alert_report.py`, `urgent_alerts.py`, `matchers/`, `reflection.py` |
| Opportunity announcements | `announce*.py`, `announcement_*.py`, `discord_announcements.py` |
| Shares, the share fan-out, collections | `collaboration.py`, `fanout.py` |
| Delivery cadence and failures, Slack, high-signal | `delivery.py`, `delivery_failures.py`, `slack_reports.py`, `high_signal.py` |
| Nightly analytics | `run_analytics.py`, `analytics_report_pdf.py` |

## Doors

- `read.py`: the delivery models.
- `service.py`: the share fan-out, creating and updating reminders, and
  activating a target's announcements.

```bash
uv run --directory web/backend pytest -c pyproject.toml ../../tools/delivery
```
