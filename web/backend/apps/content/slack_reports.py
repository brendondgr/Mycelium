"""Reports on Slack and Teams (ambient Plan 11, step 5 and rule 15).

The reports are written once, by the same pipeline. This module only sends
them to where a reader or a lab lives:

- **a person** linked on Slack and not on Discord gets their daily or weekly
  as a Slack DM, on the same cadence, at the same local hour. A person linked
  on both keeps Discord, the surface they linked first.
- **a lab** gets its daily and weekly posts in its Slack updates channel when
  the lab has no Discord updates channel, or when its workspace is marked
  primary for reports (``SlackWorkspace.reports_primary``). In that case the
  Discord senders skip the lab (:func:`slack_is_primary`).

The post is the same overview the Discord embed carries, as Block Kit, plus a
link to the full report on the web. Slack gets no PDF attachment: a file
upload needs a scope this app does not ask for.

Teams follows the same rules: a person linked on Teams only gets their report
in their chat with Mylo, and a lab gets its posts in the team's updates
channel when it has no Discord channel or marks the team primary. On Teams
the post is the overview as text, with the same link.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from django.conf import settings

from apps.content import delivery

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return bool(getattr(settings, "SLACK_ENABLED", False))


def _mrkdwn(text: str) -> str:
    """Discord markdown to Slack mrkdwn: bold, and links."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", text or "")
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)


def embed_to_blocks(embed: dict, *, link: str = "") -> list[dict]:
    """A report embed as Block Kit. Pure; tested on its own."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": str(embed.get("title", ""))[:150]},
        }
    ]
    if embed.get("description"):
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _mrkdwn(embed["description"])[:2900],
                },
            }
        )
    for field in embed.get("fields") or []:
        text = f"*{_mrkdwn(field.get('name', ''))}*\n{_mrkdwn(field.get('value', ''))}"
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}
        )
    if link:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Read the full report"},
                        "url": link,
                        "action_id": "open_report",
                    }
                ],
            }
        )
    return blocks[:50]


def _report_link() -> str:
    base = str(getattr(settings, "DISCORD_APP_BASE_URL", "") or "").rstrip("/")
    return f"{base}/app/reports"


def slack_only(user) -> bool:
    from apps.integrations.services import resolve, slack_resolve

    return (
        slack_resolve.identity_for(user) is not None
        and resolve.active_identity_for_user(user) is None
    )


def lab_workspace(lab):
    from apps.integrations.services import slack_resolve

    return slack_resolve.workspace_for_lab(lab, with_channel=True)


def slack_is_primary(lab) -> bool:
    """Whether this lab's posts go to Slack or Teams instead of Discord."""
    workspace = lab_workspace(lab) if _enabled() else None
    team = lab_team(lab) if _teams_enabled() else None
    return bool(
        (workspace and workspace.reports_primary) or (team and team.reports_primary)
    )


def _teams_enabled() -> bool:
    return bool(getattr(settings, "TEAMS_ENABLED", False))


def lab_team(lab):
    from apps.integrations.services import teams_resolve

    link = teams_resolve.link_for_lab(lab)
    return link if link is not None and link.updates_conversation_id else None


def teams_only(user) -> bool:
    from apps.integrations.services import resolve, slack_resolve, teams_resolve

    return (
        teams_resolve.identity_for(user) is not None
        and resolve.active_identity_for_user(user) is None
        and slack_resolve.identity_for(user) is None
    )


def embed_to_text(embed: dict, *, link: str = "") -> str:
    """A report embed as Teams text (markdown). Pure."""
    lines = [f"**{embed.get('title', '')}**"]
    if embed.get("description"):
        lines.append(str(embed["description"]))
    for field in embed.get("fields") or []:
        lines.append(f"**{field.get('name', '')}**\n{field.get('value', '')}")
    if link:
        lines.append(f"[Read the full report]({link})")
    return "\n\n".join(lines)[:25000]


def _lab_on_slack(lab) -> bool:
    from apps.integrations.services import resolve

    workspace = lab_workspace(lab)
    if workspace is None:
        return False
    return workspace.reports_primary or not resolve.get_updates_channel_for_lab(lab)


def send(*, on: date | None = None) -> dict:
    """Queue today's Slack reports. Never raises; a no-op while Slack is off."""
    if not _enabled() and not _teams_enabled():
        return {"enabled": False}
    counts = {"people": 0, "labs": 0, "errors": 0}
    if _enabled():
        _people(on, counts)
        _labs(on, counts)
    if _teams_enabled():
        _teams_people(on, counts)
        _teams_labs(on, counts)
    return counts


def _report_for(target, *, is_lab: bool, on):
    """``(embed, dedupe suffix, local date)`` for today's push, or None."""
    from apps.content import discord_embeds
    from apps.content.daily_report import (
        compile_report_for_lab,
        compile_report_for_user,
    )
    from apps.content.weekly_send import _monday, _weekly_body

    local = on or delivery.local_today(target)
    cadence = delivery.lab_cadence(target) if is_lab else delivery.user_cadence(target)
    kinds = delivery.push_kinds(cadence, local)
    build = (
        discord_embeds.lab_post_embed
        if is_lab
        else discord_embeds.personal_report_embed
    )
    if delivery.WEEKLY in kinds:
        data, weekly = _weekly_body(target, is_lab=is_lab)
        if weekly is None:
            return None
        return build(data, data.stats, "weekly"), f"weekly:{_monday(local)}", local
    if delivery.DAILY in kinds:
        data = (
            compile_report_for_lab(target)
            if is_lab
            else compile_report_for_user(target)
        )
        if data.stats.is_quiet:
            return None
        return build(data, data.stats), f"daily:{local}", local
    return None


def _teams_people(on, counts) -> None:
    from tools.recommendation.tasks import select_users

    from apps.integrations.services import teams_outbox

    for user in select_users(None):
        try:
            if not teams_only(user):
                continue
            report = _report_for(user, is_lab=False, on=on)
            if report is None:
                continue
            embed, suffix, local = report
            _row, created = teams_outbox.enqueue_dm(
                user=user,
                dedupe_key=f"teams_report:{user.pk}:{suffix}",
                kind="report",
                text=embed_to_text(embed, link=_report_link()),
                not_before=delivery.send_time(user, local),
            )
            counts["people"] += int(created)
        except Exception:  # noqa: BLE001
            counts["errors"] += 1
            logger.warning("teams report failed for %s", user, exc_info=True)


def _teams_labs(on, counts) -> None:
    from apps.accounts.models import Lab
    from apps.billing.entitlements import Feature, lab_has_feature
    from apps.integrations.services import resolve, teams_outbox

    for lab in Lab.objects.filter(teams_links__active=True).distinct():
        try:
            team = lab_team(lab)
            if team is None or not lab_has_feature(lab, Feature.BOT_SERVER):
                continue
            if not (
                team.reports_primary or not resolve.get_updates_channel_for_lab(lab)
            ):
                continue
            report = _report_for(lab, is_lab=True, on=on)
            if report is None:
                continue
            embed, suffix, local = report
            _row, created = teams_outbox.enqueue(
                dedupe_key=f"teams_lab_report:{lab.pk}:{suffix}",
                kind="lab_report",
                service_url=team.service_url,
                conversation_id=team.updates_conversation_id,
                text=embed_to_text(embed, link=_report_link()),
                not_before=delivery.send_time(lab, local),
            )
            counts["labs"] += int(created)
        except Exception:  # noqa: BLE001
            counts["errors"] += 1
            logger.warning("teams lab report failed for %s", lab, exc_info=True)


def _people(on, counts) -> None:
    from tools.recommendation.tasks import select_users

    from apps.content import discord_embeds
    from apps.content.daily_report import compile_report_for_user
    from apps.content.weekly_send import _monday, _weekly_body
    from apps.integrations.services.slack_outbox import enqueue_dm

    for user in select_users(None):
        try:
            if not slack_only(user):
                continue
            local = on or delivery.local_today(user)
            kinds = delivery.push_kinds(delivery.user_cadence(user), local)
            if delivery.WEEKLY in kinds:
                data, weekly = _weekly_body(user, is_lab=False)
                if weekly is None:
                    continue
                embed = discord_embeds.personal_report_embed(data, data.stats, "weekly")
                key = f"slack_weekly_report:{user.pk}:{_monday(local).isoformat()}"
            elif delivery.DAILY in kinds:
                data = compile_report_for_user(user)
                if data.stats.is_quiet:
                    continue
                embed = discord_embeds.personal_report_embed(data, data.stats)
                key = f"slack_daily_report:{user.pk}:{local.isoformat()}"
            else:
                continue
            _row, created = enqueue_dm(
                user=user,
                dedupe_key=key,
                kind="report",
                text=str(embed.get("title", "Your Mylo report")),
                blocks=embed_to_blocks(embed, link=_report_link()),
                subject_type="report",
                subject_id=str(user.pk),
                not_before=delivery.send_time(user, local),
            )
            counts["people"] += int(created)
        except Exception:  # noqa: BLE001 - one reader never sinks the batch
            counts["errors"] += 1
            logger.warning("slack report failed for %s", user, exc_info=True)


def _labs(on, counts) -> None:
    from apps.billing.entitlements import Feature, lab_has_feature
    from apps.content import discord_embeds
    from apps.content.daily_report import compile_report_for_lab
    from apps.content.weekly_send import _monday, _weekly_body
    from apps.integrations.services import slack_resolve
    from apps.integrations.services.slack_outbox import enqueue_channel

    for lab in slack_resolve.labs_with_workspaces():
        try:
            if not _lab_on_slack(lab) or not lab_has_feature(lab, Feature.BOT_SERVER):
                continue
            workspace = lab_workspace(lab)
            local = on or delivery.local_today(lab)
            kinds = delivery.push_kinds(delivery.lab_cadence(lab), local)
            if delivery.WEEKLY in kinds:
                data, weekly = _weekly_body(lab, is_lab=True)
                if weekly is None:
                    continue
                embed = discord_embeds.lab_post_embed(data, data.stats, "weekly")
                key = f"slack_lab_weekly:{lab.pk}:{_monday(local).isoformat()}"
            elif delivery.DAILY in kinds:
                data = compile_report_for_lab(lab)
                if data.stats.is_quiet:
                    continue
                embed = discord_embeds.lab_post_embed(data, data.stats)
                key = f"slack_lab_daily:{lab.pk}:{local.isoformat()}"
            else:
                continue
            _row, created = enqueue_channel(
                workspace=workspace,
                dedupe_key=key,
                kind="lab_report",
                text=str(embed.get("title", "Mylo report")),
                blocks=embed_to_blocks(embed, link=_report_link()),
                subject_type="lab_report",
                subject_id=str(lab.pk),
                not_before=delivery.send_time(lab, local),
            )
            counts["labs"] += int(created)
        except Exception:  # noqa: BLE001
            counts["errors"] += 1
            logger.warning("slack lab report failed for %s", lab, exc_info=True)
