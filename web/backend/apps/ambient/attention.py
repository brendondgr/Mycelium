"""Which project a person is actually spending their conversation on.

From attributed messages, per speaker per project: the share of their
*attributed* conversation over the last 7 and 28 days. Unresolved messages are
left out of the denominator on purpose — "I don't know which project this was"
is not evidence of time spent on none of them — and so are repeats (one thought
pasted three times is one piece of attention) and Mylo's own lines.

Derived, recomputed nightly, never edited by hand. It is a measurement, and a
measurement somebody can type into is an opinion. Plan 05 reads it to put the
project a person is actually on first; Plan 09 reads it to say "you spent most
of this week on X". It describes one person and is read by that person.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ProjectAttention, RawMessageRef

SHORT_DAYS = 7
LONG_DAYS = 28


def recompute(now=None) -> int:
    """Rebuild every attention row from the last 28 days. Returns rows written."""
    now = now or timezone.now()
    short_start = now - timedelta(days=SHORT_DAYS)
    long_start = now - timedelta(days=LONG_DAYS)

    rows = RawMessageRef.objects.filter(
        speaker__isnull=False,
        project__isnull=False,
        deleted_at__isnull=True,
        repeat_of__isnull=True,
        sent_at__gte=long_start,
        sent_at__lte=now,
    ).values_list("speaker_id", "project_id", "sent_at")

    long_counts: dict[tuple[int, str], int] = defaultdict(int)
    short_counts: dict[tuple[int, str], int] = defaultdict(int)
    long_totals: dict[int, int] = defaultdict(int)
    short_totals: dict[int, int] = defaultdict(int)
    for speaker_id, project_id, sent_at in rows:
        key = (speaker_id, project_id)
        long_counts[key] += 1
        long_totals[speaker_id] += 1
        if sent_at >= short_start:
            short_counts[key] += 1
            short_totals[speaker_id] += 1

    with transaction.atomic():
        keep: set[tuple[int, str]] = set()
        for (speaker_id, project_id), count in long_counts.items():
            short = short_counts.get((speaker_id, project_id), 0)
            ProjectAttention.objects.update_or_create(
                user_id=speaker_id,
                project_id=project_id,
                defaults={
                    "messages_28d": count,
                    "messages_7d": short,
                    "share_28d": round(count / long_totals[speaker_id], 4),
                    "share_7d": (
                        round(short / short_totals[speaker_id], 4)
                        if short_totals.get(speaker_id)
                        else 0.0
                    ),
                    "computed_at": now,
                },
            )
            keep.add((speaker_id, str(project_id)))

        # A project nobody has talked about for four weeks has no attention
        # left to report; its row goes rather than lingering at zero.
        for row in ProjectAttention.objects.all().only("pk", "user_id", "project_id"):
            if (row.user_id, str(row.project_id)) not in keep:
                row.delete()
    return len(long_counts)
