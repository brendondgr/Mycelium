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

from apps.ambient.read import (
    changes_to_announce,
    facts_to_announce,
    mark_announced,
    mark_asked,
    questions_to_deliver,
)
from apps.content.delivery import send_time
from apps.content.models import Notification
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
                    "title": title.format(topic=suggestion.topic)[:500],
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
