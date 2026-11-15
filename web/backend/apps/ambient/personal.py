"""The personal-information opt-out (Q-071).

A person can keep facts about their life — health, immigration or a visa,
family, pregnancy, money, relationships and conflicts with people, plans to
leave — out of what Mylo learns, while their research, projects, skills and
interests are still noted.

How it is decided. The extractor answers ``personal`` for every observation in
the same call that reads the conversation (:mod:`.extract`, prompt ``a5``), so
new messages cost no second call. The answer is stored on every row
(``Observation.personal_life``), whether or not anybody opted out, so a person
who opts out later is covered from what was already decided.

What the switch does.

* **On**, nothing the extractor marks personal — or leaves unmarked — is
  written for that speaker (:func:`keep`; ``ExtractionRun.withheld`` counts
  them). Their rows already marked personal are **deleted** at once, through
  :func:`apps.ambient.reconcile.forget_observations`, so what was built on
  them goes too and a ``Retraction`` says so.
* Rows written before ``a5`` carry no answer (``personal_life`` null). For a
  person who opted out, :func:`sweep` asks the model once per batch of Mylo's
  own notes (never the messages, which are gone) and deletes the ones it marks
  personal. It runs at the start of every hourly read; when the model cannot be
  reached the rows wait for the next hour.
* **Off**, behaviour is as before: personal facts are recorded, ``personal``.
  Turning it off brings nothing back.

Deleted, not hidden: about ten places read observations (recall, "What Mylo
knows", deliberation, explanations, evaluation, the dataset export), and a
filter each of them must remember is one a future reader can forget. Deletion
also matches what the person asked for — not to have these kept.

Not covered: Mylo chats themselves and their recall digests, which stay until
the person deletes the chat (Q-072); facts a person said about somebody else,
which are filed under the speaker and follow the speaker's switch.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from django.utils import timezone

from .models import ListeningConsent, Observation, Platform

logger = logging.getLogger(__name__)

COMPONENT = "ambient_personal"
#: Notes per model call in :func:`sweep`, and calls per hourly pass.
BATCH = 25
MAX_CALLS = 8

CompleteFn = Callable[[str, str], str | None]

SYSTEM = (
    "You sort short notes a research assistant kept about people. "
    "Reply with one JSON object and nothing else."
)

PROMPT = """Each numbered note is the assistant's own account of something a
person said. Say which notes are about the person's life rather than their
work: health or a medical condition, immigration or a visa, family, pregnancy
or caring for someone, money or salary, a relationship or a conflict with a
person, or a plan to leave the lab or job — even when it is mentioned because it
affects the work. Research, projects, methods, tools, skills, interests and
career direction in a field are work.

Reply as {{"personal": [the numbers of the notes about a life, possibly none]}}

NOTES
-----
{notes}
"""


# -- the switch ------------------------------------------------------------------


def withheld(user) -> bool:
    """Whether this person keeps personal information out. Default off."""
    return ListeningConsent.objects.filter(
        user=user, platform=Platform.DISCORD, personal_withheld=True
    ).exists()


def withheld_ids(user_ids) -> set[int]:
    """Which of these people keep personal information out."""
    ids = {int(pk) for pk in user_ids if pk is not None}
    if not ids:
        return set()
    return set(
        ListeningConsent.objects.filter(
            user_id__in=ids, platform=Platform.DISCORD, personal_withheld=True
        ).values_list("user_id", flat=True)
    )


def set_withheld(user, *, on: bool, now=None) -> int:
    """Flip the switch; turning it on deletes what is already marked personal.

    Returns how many observations were deleted. Rows not yet marked wait for
    the next :func:`sweep`.
    """
    now = now or timezone.now()
    consent, _ = ListeningConsent.objects.get_or_create(
        user=user, platform=Platform.DISCORD
    )
    consent.personal_withheld = bool(on)
    consent.personal_withheld_at = now if on else None
    consent.save(
        update_fields=["personal_withheld", "personal_withheld_at", "updated_at"]
    )
    return forget_marked(user) if on else 0


def forget_marked(user) -> int:
    """Delete this person's observations marked personal; returns how many."""
    from .reconcile import forget_observations

    ids = list(
        Observation.objects.filter(speaker=user, personal_life=True).values_list(
            "pk", flat=True
        )
    )
    if not ids:
        return 0
    forget_observations(user, ids)
    return len(ids)


# -- at extraction ---------------------------------------------------------------


def keep(item, withheld_speakers: set[int]) -> bool:
    """Whether an extracted observation may be written.

    For a speaker who opted out only an explicit "not personal" is kept: an
    observation the model left unmarked is dropped rather than guessed at.
    """
    if item.line.speaker_id not in withheld_speakers:
        return True
    return item.personal is False


# -- rows written before the extractor was asked --------------------------------


def _settings_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component=COMPONENT)
    return client.complete(
        [LLMMessage("system", system), LLMMessage("user", user)]
    ).content


def _numbers(raw: str | None, size: int) -> set[int] | None:
    """The note numbers the reply marks personal, or None if it is unusable."""
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    values = data.get("personal") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return None
    marked = set()
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if not 1 <= number <= size:
            return None
        marked.add(number)
    return marked


def sweep(*, complete: CompleteFn | None = None, max_calls: int = MAX_CALLS) -> dict:
    """Mark unmarked rows of people who opted out, and delete the personal ones.

    Never raises. Returns counts: ``marked``, ``deleted``, ``unavailable``.
    """
    counts = {"marked": 0, "deleted": 0, "unavailable": 0}
    people = list(
        ListeningConsent.objects.filter(
            platform=Platform.DISCORD, personal_withheld=True
        ).values_list("user_id", flat=True)
    )
    if not people:
        return counts
    ask = complete if complete is not None else _settings_complete
    rows = Observation.objects.filter(
        speaker_id__in=people, personal_life__isnull=True
    ).order_by("pk")
    touched: set[int] = set()
    for _ in range(max_calls):
        batch = list(rows.values("pk", "speaker_id", "topic", "text")[:BATCH])
        if not batch:
            break
        notes = "\n".join(
            f"[{n}] ({row['topic']}) {row['text']}" for n, row in enumerate(batch, 1)
        )
        try:
            raw = ask(SYSTEM, PROMPT.format(notes=notes))
        except Exception as exc:  # noqa: BLE001 - the next hour tries again
            logger.warning(
                "ambient personal sweep unavailable (%s)", type(exc).__name__
            )
            counts["unavailable"] += 1
            break
        marked = _numbers(raw, len(batch))
        if marked is None:
            counts["unavailable"] += 1
            break
        personal = [row["pk"] for n, row in enumerate(batch, 1) if n in marked]
        work = [row["pk"] for n, row in enumerate(batch, 1) if n not in marked]
        Observation.objects.filter(pk__in=personal).update(personal_life=True)
        Observation.objects.filter(pk__in=work).update(personal_life=False)
        counts["marked"] += len(batch)
        touched |= {row["speaker_id"] for row in batch}
    from django.contrib.auth import get_user_model

    for user in get_user_model().objects.filter(pk__in=touched):
        counts["deleted"] += forget_marked(user)
    return counts
