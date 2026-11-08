"""Send tonight's ambient questions, and ring the bell for what took effect.

Ambient Plan 06, step 5 (and the bell of Plan 07, step 1). Run by
``manual_all.py`` after the day's reports are queued, and non-fatal there:
each question goes out as a DM with its buttons at the person's own send hour
(:func:`apps.content.delivery.send_time`) and appears on the bell at once; each
confirmed change that took effect gets one bell notification, the morning after.

The questions themselves — who, what, the words and the choices — are decided
on the ambient side (:mod:`apps.ambient.dialogue`) and read through
``apps.ambient.read``; this command only delivers them.
"""

import json

from django.core.management.base import BaseCommand
from django.utils import timezone
from tools.retrieval.models import Notification

from apps.ambient.read import (
    changes_to_announce,
    facts_to_announce,
    mark_announced,
    mark_asked,
    mark_transcripts_announced,
    questions_to_deliver,
    transcripts_to_announce,
)
from apps.content.delivery import send_time
from apps.integrations.services.outbox import enqueue_dm

QUESTION_TITLES = {
    "interest": "Mylo has a question about {topic}",
    "skill": "Add {topic} to your skills?",
    "development": "Did this happen: {topic}?",
    "intent": "Has a project's aim changed? ({topic})",
    "clarify": "A quick question about {topic}",
    "review": "Keep exploring {topic}?",
}
APPLIED_TITLES = {
    "reports": "{topic} is now in your reports — you confirmed it",
    "keep": "Still exploring {topic} — you kept it",
    "drop": "Stopped exploring {topic}",
    "yes": "Noted on the project: {topic}",
    # Plan 08: a yes that edits the profile, applied at the nightly run.
    "interests": "{topic} is now in your interests — you said yes",
    "theme": "{topic} is now a theme in your profile — you said yes",
    "swap": "{topic} replaced a quiet theme in your profile — you said yes",
    "skill": "{topic} is now in your skills — you said yes",
    "learning": "{topic} is now a learning goal — you said yes",
    "preference": "Noted as a preference: {topic}",
    "direction": "Noted as your direction: {topic}",
}


class Command(BaseCommand):
    help = "Deliver ambient questions and announce the changes people confirmed."

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate(now)
        sent = 0
        delivered = []
        for question in questions_to_deliver():
            if _on_teams_only(question.user):
                # Ambient Plan 11: a person linked on Teams only is asked there.
                from apps.integrations.services.teams_outbox import (
                    enqueue_dm as enqueue_teams_dm,
                )

                enqueue_teams_dm(
                    user=question.user,
                    dedupe_key=f"ambient-question-{question.id}",
                    kind="ambient_question",
                    text=_slack_text(question.content)[:2900],
                    attachments=teams_card(question.content, question.components),
                    not_before=send_time(question.user, today),
                )
            elif not _on_slack_only(question.user):
                enqueue_dm(
                    dedupe_key=f"ambient-question-{question.id}",
                    kind="ambient_question",
                    user=question.user,
                    content=question.content[:1900],
                    components=question.components,
                    subject_type="ambient_suggestion",
                    subject_id=str(question.id),
                    not_before=send_time(question.user, today),
                )
            else:
                # Ambient Plan 11: a person linked on Slack only is asked there.
                from apps.integrations.services.slack_outbox import (
                    enqueue_dm as enqueue_slack_dm,
                )

                enqueue_slack_dm(
                    user=question.user,
                    dedupe_key=f"ambient-question-{question.id}",
                    kind="ambient_question",
                    text=_slack_text(question.content)[:2900],
                    blocks=slack_blocks(question.content, question.components),
                    subject_type="ambient_suggestion",
                    subject_id=str(question.id),
                    not_before=send_time(question.user, today),
                )
            Notification.objects.get_or_create(
                dedupe_key=f"ambient-suggestion-{question.id}",
                defaults={
                    "user": question.user,
                    "kind": Notification.Kind.SUGGESTION_PENDING,
                    "title": QUESTION_TITLES.get(
                        question.kind, "Mylo has a question"
                    ).format(topic=question.topic)[:500],
                    "url": "/app/mylo-and-you",
                },
            )
            delivered.append(question.id)
            sent += 1
        mark_asked(delivered, now=now)

        announced = []
        for suggestion in changes_to_announce():
            key = suggestion.choice.split(":", 1)[0]
            title = APPLIED_TITLES.get(
                key, "A change you confirmed took effect: {topic}"
            )
            Notification.objects.get_or_create(
                dedupe_key=f"ambient-applied-{suggestion.pk}",
                defaults={
                    "user": suggestion.user,
                    "kind": Notification.Kind.CHANGE_APPLIED,
                    "title": title.format(
                        topic=suggestion.correction or suggestion.topic
                    )[:500],
                    "url": "/app/mylo-and-you",
                },
            )
            announced.append(suggestion.pk)
        mark_announced(announced, now=now)
        # Plan 08 step 3 (OD-08a): a project fact someone told Mylo is recorded
        # without a question, so it is always echoed on the bell, once.
        facts = 0
        for change in facts_to_announce(now=now):
            _, made = Notification.objects.get_or_create(
                dedupe_key=f"ambient-fact-{change.pk}",
                defaults={
                    "user": change.user,
                    "kind": Notification.Kind.CHANGE_APPLIED,
                    "title": (
                        f"Noted on {change.project.name}: {change.topic} — "
                        "you told Mylo. Undo it on Mylo & you."
                        if change.project_id
                        else f"Noted: {change.topic} — you told Mylo."
                    )[:500],
                    "url": "/app/mylo-and-you",
                },
            )
            facts += made
        # Plan 11, step 11: everyone named in a meeting transcript is told it was
        # read — whether or not their own turns could be used.
        told = []
        for meeting_id, title, participant_ids in transcripts_to_announce():
            for user_id in participant_ids:
                Notification.objects.get_or_create(
                    dedupe_key=f"ambient-transcript-{meeting_id}-{user_id}",
                    defaults={
                        "user_id": user_id,
                        "kind": Notification.Kind.CHANGE_APPLIED,
                        "title": f"Mylo read the meeting “{title}”"[:500],
                        "body": (
                            "Only your turns, and only if you opted in to "
                            "transcripts; only project decisions and blockers "
                            "are kept. The transcript itself is not kept."
                        ),
                        "url": "/app/mylo-and-you",
                    },
                )
            told.append(meeting_id)
        mark_transcripts_announced(told, now=now)
        # Plan 08: developments that make a project's stated state out of date,
        # proposed to its editors on the project page.
        from apps.content.ambient_proposals import propose

        proposed = propose(today=today)
        self.stdout.write(
            json.dumps(
                {
                    "questions": sent,
                    "announced": len(announced),
                    "facts": facts,
                    "proposed": proposed,
                }
            )
        )


def _on_slack_only(user) -> bool:
    """Linked on Slack and not on Discord: asked on Slack (Plan 11). Anyone
    else keeps Discord, whose outbox resolves the identity at send time."""
    from apps.integrations.models import DiscordIdentity, SlackIdentity

    return (
        SlackIdentity.objects.filter(user=user, state="active").exists()
        and not DiscordIdentity.objects.filter(
            user=user, state=DiscordIdentity.State.ACTIVE
        ).exists()
    )


def _on_teams_only(user) -> bool:
    from apps.integrations.models import (
        DiscordIdentity,
        SlackIdentity,
        TeamsIdentity,
    )

    return (
        TeamsIdentity.objects.filter(user=user, state="active").exists()
        and not DiscordIdentity.objects.filter(user=user, state="active").exists()
        and not SlackIdentity.objects.filter(user=user, state="active").exists()
    )


def teams_card(content: str, components) -> list[dict]:
    """The question as an Adaptive Card: the text, then one submit button per
    choice carrying ``{"ambient": "<id>:<choice>"}``."""
    actions = [
        {
            "type": "Action.Submit",
            "title": str(button.get("label", ""))[:80],
            "data": {"ambient": str(button.get("custom_id", "")).split(":", 1)[1]},
        }
        for row in (components or [])
        for button in (row.get("components") or [])
        if str(button.get("custom_id", "")).startswith("ambient:")
    ]
    return [
        {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": _slack_text(content)[:2900],
                        "wrap": True,
                    }
                ],
                "actions": actions[:6],
            },
        }
    ]


def _slack_text(content: str) -> str:
    """Discord's ``**bold**`` as Slack's ``*bold*``; nothing else differs."""
    import re

    return re.sub(r"\*\*([^*]+)\*\*", r"*\1*", content or "")


def slack_blocks(content: str, components) -> list[dict]:
    """The question as Block Kit: the text, then one button per choice, with
    the same ``ambient:<id>:<choice>`` ids the Discord buttons carry."""
    buttons = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": str(button.get("label", ""))[:75]},
            "action_id": str(button.get("custom_id", "")),
            "value": str(button.get("custom_id", "")).rsplit(":", 1)[-1],
        }
        for row in (components or [])
        for button in (row.get("components") or [])
        if str(button.get("custom_id", "")).startswith("ambient:")
    ]
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": _slack_text(content)[:2900]},
        }
    ]
    if buttons:
        blocks.append({"type": "actions", "elements": buttons[:25]})
    return blocks
