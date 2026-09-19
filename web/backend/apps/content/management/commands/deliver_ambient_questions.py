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
                    "url": "/mylo-and-you",
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
                    "url": "/mylo-and-you",
                },
            )
            announced.append(suggestion.pk)
        mark_announced(announced, now=now)
        self.stdout.write(json.dumps({"questions": sent, "announced": len(announced)}))
