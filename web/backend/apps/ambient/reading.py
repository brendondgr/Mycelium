"""The hourly read: ready conversations in, observations out (Plan 04).

For each conversation :mod:`.windows` says is ready:

1. attribution gets a second look with meaning similarity (Plan 03), while the
   text still exists;
2. a window whose text has all expired is recorded as ``expired`` and closed;
3. a window already read under the same content hash is closed unread — an
   unchanged window is never sent to the model twice;
4. the extractor reads it (:mod:`.extract`);
5. the observations are written — less anything about the life of a speaker
   who keeps personal information out (:mod:`.personal`) — each topic linked
   to a concept through the knowledge core, and the bodies are deleted.

If the model cannot be reached the window is left unread, bodies and all, and
the next hour tries again; once its bodies are within the expiry margin
:mod:`.windows` offers it regardless and, still unreachable, it simply expires.
Nothing rule-based stands in (README principle 18).

The day's calls are capped per lab (``AMBIENT_EXTRACT_DAILY_CAP_PER_LAB``) and,
for a person's DMs, per source. Model calls run in a thread pool of
``AMBIENT_EXTRACT_CONCURRENCY``; everything that touches the database runs on
the calling thread.
"""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import extract, personal, windows
from .eligibility import agent_chat_enabled, ambient_enabled
from .extract import Extracted, Outcome
from .models import (
    PERSONAL_KINDS,
    ExtractionRun,
    Observation,
    Origin,
    PlaceKind,
    RawMessageRef,
    Visibility,
)
from .windows import Conversation

logger = logging.getLogger(__name__)


@dataclass
class ReadRun:
    """What one pass did, in counts."""

    ready: int = 0
    read: int = 0
    unavailable: int = 0
    expired: int = 0
    duplicate: int = 0
    capped: int = 0
    observations: int = 0
    #: Not written: personal facts about people who opted out (Q-071).
    withheld: int = 0
    linked: int = 0
    refused: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        data = dict(self.__dict__)
        data["refused"] = dict(self.refused)
        return data


def _today_start(now) -> datetime:
    return timezone.make_aware(datetime.combine(timezone.localdate(now), time.min))


def _spent_today(conversation: Conversation, now) -> int:
    runs = ExtractionRun.objects.filter(
        created_at__gte=_today_start(now),
        outcome__in=[
            ExtractionRun.Outcome.READ,
            ExtractionRun.Outcome.EMPTY,
            ExtractionRun.Outcome.REFUSED,
        ],
    )
    if conversation.source.lab_id:
        return runs.filter(lab_id=conversation.source.lab_id).count()
    return runs.filter(source=conversation.source).count()


def _embedder():
    from apps.knowledge.read import embed_phrases

    return embed_phrases


def _attribute(conversation: Conversation) -> Conversation:
    """Plan 03's nightly pass, run here because this is when the text exists."""
    from .attribution import attribute_window

    try:
        attribute_window(conversation, embedder=_embedder())
    except Exception:  # noqa: BLE001 - attribution never costs the read
        logger.warning("ambient: attribution pass failed", exc_info=True)
        return conversation
    projects = dict(
        RawMessageRef.objects.filter(
            pk__in=[line.ref_id for line in conversation.lines]
        ).values_list("pk", "project_id")
    )
    conversation.lines = [
        replace(
            line,
            project_id=str(projects[line.ref_id])
            if projects.get(line.ref_id)
            else None,
        )
        for line in conversation.lines
    ]
    return conversation


def _visibility(item: Extracted, conversation: Conversation, projects: dict) -> str:
    """Visibility travels with the memory (README principle 7).

    Anything about the person themselves is personal. A project fact is lab
    only when it was said on the lab's own surface about one of the lab's
    projects whose scope reaches the lab; said about an ``invite_only``
    project it is ``project`` evidence, for that project's people only; said in
    a DM, it stays with the person who said it.
    """
    from apps.research import visibility as scope

    if item.kind in PERSONAL_KINDS:
        return Visibility.PERSONAL
    if item.line.place_kind == PlaceKind.DM or not conversation.source.lab_id:
        return Visibility.PERSONAL
    project = projects.get(item.line.project_id)
    if project is None or project.scope_user_id is not None:
        # A personal project's talk stays with the person who said it.
        return Visibility.PERSONAL
    if scope.stays_with_people(project):
        return Visibility.PROJECT
    if project.scope_lab_id == conversation.source.lab_id:
        return Visibility.LAB
    return Visibility.PERSONAL


def _owner(item: Extracted, speaker, projects: dict):
    """Whose scope a topic's concept is born in: the person for anything about
    them, the lab for a lab project's development — unless the project is
    ``invite_only``, whose themes stay with the person who said them."""
    from apps.research import visibility as scope

    if item.kind not in PERSONAL_KINDS:
        project = projects.get(item.line.project_id)
        if (
            project is not None
            and project.scope_lab_id
            and not scope.stays_with_people(project)
        ):
            return project.scope_lab
    return speaker


def _store(
    conversation: Conversation, outcome: Outcome, digest: str, now
) -> ExtractionRun:
    from django.contrib.auth import get_user_model

    from apps.research.models import Project

    if conversation.source.kind == "transcript":
        # Plan 11, step 10: a meeting yields its project's developments only.
        from .transcripts import keep_only_developments

        outcome.observations = keep_only_developments(outcome.observations)
    opted_out = personal.withheld_ids(
        {item.line.speaker_id for item in outcome.observations}
    )
    kept = [item for item in outcome.observations if personal.keep(item, opted_out)]
    withheld = len(outcome.observations) - len(kept)
    outcome.observations = kept
    if outcome.observations:
        result = ExtractionRun.Outcome.READ
    elif outcome.refused:
        result = ExtractionRun.Outcome.REFUSED
    else:
        result = ExtractionRun.Outcome.EMPTY
    speakers = {
        u.pk: u
        for u in get_user_model().objects.filter(
            pk__in={item.line.speaker_id for item in outcome.observations}
        )
    }
    projects = {
        str(p.pk): p
        for p in Project.objects.filter(
            pk__in={
                i.line.project_id for i in outcome.observations if i.line.project_id
            }
        ).select_related("scope_lab")
    }
    with transaction.atomic():
        run = ExtractionRun.objects.create(
            source=conversation.source,
            lab_id=conversation.source.lab_id,
            place_id=conversation.spec.place_id,
            conversation_key=conversation.spec.key,
            window_start=conversation.spec.since,
            window_end=conversation.spec.until,
            content_hash=digest,
            messages=len(conversation.lines),
            readable=len(conversation.readable),
            outcome=result,
            observations_kept=len(outcome.observations),
            refused=sorted(set(outcome.refused)),
            withheld=withheld,
            engagement=sum(1 for line in conversation.readable if line.engagement),
            attempts=outcome.attempts,
            prompt_version=extract.PROMPT_VERSION,
        )
        rows = []
        for item in outcome.observations:
            speaker = speakers.get(item.line.speaker_id)
            if speaker is None:
                continue
            project = projects.get(item.line.project_id)
            rows.append(
                (
                    item,
                    speaker,
                    Observation.objects.create(
                        source=conversation.source,
                        external_message_ids=[item.line.external_id],
                        observed_at=item.line.sent_at,
                        speaker=speaker,
                        text=item.account,
                        subject=item.subject,
                        understanding_kind=item.kind,
                        force=item.force,
                        project=project,
                        project_confidence=None,
                        grounded=True,
                        place_kind=item.line.place_kind,
                        place_label=item.line.place_label,
                        extraction_confidence=item.confidence,
                        visibility=_visibility(item, conversation, projects),
                        origin=Origin.MODEL,
                        facet=item.facet,
                        topic=item.topic,
                        change=item.change,
                        personal_life=item.personal,
                        explicit=item.line.explicit
                        or item.line.place_kind == PlaceKind.DM,
                        conversation_key=conversation.spec.key,
                        run=run,
                    ),
                )
            )
        windows.mark_read(conversation, now=now)
    link(
        [observation for _, _, observation in rows],
        owners={
            observation.pk: _owner(item, speaker, projects)
            for item, speaker, observation in rows
        },
    )
    return run


def link(observations: list[Observation], *, owners: dict | None = None) -> int:
    """Link each observation's topic to a concept; returns how many linked.

    Model-free (the knowledge core's linker). With the embedder down a new
    wording cannot be linked safely, so it stays unlinked and deliberation
    retries tonight.
    """
    from apps.knowledge.service import link_conversation

    todo = [o for o in observations if o.concept_id is None and o.topic]
    if not todo:
        return 0
    owners = owners or {}
    requests = []
    for observation in todo:
        owner = owners.get(observation.pk)
        if owner is None:
            owner = observation.speaker
            if (
                observation.understanding_kind not in PERSONAL_KINDS
                and observation.project_id
                and observation.project.scope_lab_id
            ):
                owner = observation.project.scope_lab
        requests.append((observation.topic, observation.facet or "area", owner))
    try:
        ids = link_conversation(requests)
    except Exception:  # noqa: BLE001 - linking waits for the next run
        logger.warning("ambient: concept linking failed", exc_info=True)
        return 0
    linked = 0
    for observation, concept_id in zip(todo, ids, strict=True):
        if concept_id is not None:
            Observation.objects.filter(pk=observation.pk).update(concept_id=concept_id)
            linked += 1
    return linked


def _closed_expired(conversation: Conversation, digest: str, now) -> None:
    ExtractionRun.objects.create(
        source=conversation.source,
        lab_id=conversation.source.lab_id,
        place_id=conversation.spec.place_id,
        conversation_key=conversation.spec.key,
        window_start=conversation.spec.since,
        window_end=conversation.spec.until,
        content_hash=digest,
        messages=len(conversation.lines),
        readable=0,
        outcome=ExtractionRun.Outcome.EXPIRED,
        prompt_version=extract.PROMPT_VERSION,
    )
    windows.mark_read(conversation, now=now)


def read_ready(
    *, now=None, complete=None, sources=None, limit: int | None = None
) -> ReadRun:
    """Read every conversation that is ready. Safe to run at any time."""
    run = ReadRun()
    if not ambient_enabled():
        # Mylo chats have their own switch (agent plan D-3): with ambient off,
        # only their conversations are read.
        if not agent_chat_enabled():
            return run
        from .models import Source

        chat_sources = Source.objects.filter(kind=Source.Kind.AGENT_CHAT)
        sources = (chat_sources if sources is None
                   else [s for s in sources if s.kind == Source.Kind.AGENT_CHAT])
    now = now or timezone.now()
    specs = windows.ready(now=now, sources=sources)
    run.ready = len(specs)
    cap = int(settings.AMBIENT_EXTRACT_DAILY_CAP_PER_LAB)

    todo: list[tuple[Conversation, str]] = []
    spent: Counter = Counter()
    for spec in specs:
        if limit is not None and len(todo) >= limit:
            break
        conversation = windows.assemble(spec)
        if conversation is None:
            continue
        if not conversation.lines:
            continue
        digest = conversation.content_hash()
        if not conversation.readable:
            _closed_expired(conversation, digest, now)
            run.expired += 1
            continue
        if ExtractionRun.objects.filter(
            source=conversation.source,
            content_hash=digest,
            prompt_version=extract.PROMPT_VERSION,
            outcome__in=[
                ExtractionRun.Outcome.READ,
                ExtractionRun.Outcome.EMPTY,
                ExtractionRun.Outcome.REFUSED,
            ],
        ).exists():
            windows.mark_read(conversation, now=now)
            run.duplicate += 1
            continue
        bucket = conversation.source.lab_id or f"source:{conversation.source.pk}"
        if bucket not in spent:
            spent[bucket] = _spent_today(conversation, now)
        if spent[bucket] >= cap:
            run.capped += 1
            continue
        spent[bucket] += 1
        todo.append((_attribute(conversation), digest))

    if not todo:
        return run
    workers = max(1, min(int(settings.AMBIENT_EXTRACT_CONCURRENCY), len(todo)))
    if workers == 1:
        outcomes = [extract.extract(c, complete=complete) for c, _ in todo]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(
                pool.map(lambda pair: extract.extract(pair[0], complete=complete), todo)
            )

    for (conversation, digest), outcome in zip(todo, outcomes, strict=True):
        if outcome.unavailable:
            run.unavailable += 1
            continue
        stored = _store(conversation, outcome, digest, now)
        run.read += 1
        run.observations += stored.observations_kept
        run.withheld += stored.withheld
        run.linked += Observation.objects.filter(
            run=stored, concept__isnull=False
        ).count()
        run.refused.update(outcome.refused)
    return run
