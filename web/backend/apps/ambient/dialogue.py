"""The confirmation dialogue (Plan 06): ask once, respect the answer.

Nightly, :func:`schedule` turns what deliberation decided into questions —
:class:`~.models.PendingSuggestion` rows — for the people it concerns, strongest
evidence first, at most ``AMBIENT_QUESTIONS_PER_DAY`` a day, never on a weekend,
never in a quiet period, never once someone has said "shut off". Only a
finding whose explanation the model has written is asked about: nothing is put
to a person that Mylo cannot explain in its own words.

The same question is answered on Discord (buttons, or words — read by the
model) or on the web; the first answer wins. :func:`answer` is the one place
an answer takes effect, and every answer, and every question that expires
unanswered, leaves a :class:`~.models.ValidationRecord` and an
``ObservationFeedback`` for each observation behind it — the labelled dataset
Plan 10 measures.

What an answer does, at once and nowhere else:

* a yes to *include it in my reports* confirms the conversational edge, as an
  exploration reviewed in ``AMBIENT_EXPLORATION_REVIEW_DAYS``; ranking reads
  it from the next nightly run, and the person is told so;
* a yes that edits the declared profile — an interest, a theme, a swap, a
  skill, a preference, a direction, a learning goal — confirms the edge and
  leaves the profile edit to Plan 08's applier, which writes it as the
  person's own (stated) choice at the next nightly run;
* a no rejects the edge: it rests 30 days (deliberation) and is never raised
  again unless the person comes back to it;
* "not now" leaves everything as it is for 30 days.

Replies in words are read by the model (:func:`read_reply`); there is no
rule-based reading of free text (README principle 18). A reply that is
exactly a choice's label or its number is a button pressed by hand, and is
taken as one. When the model cannot read a reply, Mylo says so and asks for a
button — it does not guess.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    Finding,
    ListeningConsent,
    Observation,
    ObservationFeedback,
    PendingSuggestion,
    Platform,
    ProjectDevelopment,
    UnderstandingKind,
    ValidationRecord,
)

logger = logging.getLogger(__name__)

COMPONENT = "ambient_dialogue"
EXPIRY_DAYS = 14
DEFER_DAYS = 30
MAX_TURNS = 3  # the question and two follow-ups
FOOTER = (
    "Reply in your own words or use the buttons. Say “stop asking” any time and I will."
)

Kind = PendingSuggestion.Kind
Verdict = PendingSuggestion.Verdict


# -- who may be asked ----------------------------------------------------------


def askable(user, *, now=None) -> tuple[bool, str]:
    """Whether Mylo may put a question to this person today, and why not.

    Paid effective tier, an active linked Discord identity (Plan 06, step 15),
    questions not shut off, not in a quiet period, and not a weekend.
    """
    from apps.integrations.models import DiscordIdentity

    from .eligibility import ambient_enabled, tier_is_paid

    now = now or timezone.now()
    if not ambient_enabled():
        return False, "ambient_disabled"
    if not tier_is_paid(user):
        return False, "tier_free"
    if not DiscordIdentity.objects.filter(
        user=user, state=DiscordIdentity.State.ACTIVE
    ).exists():
        return False, "unlinked"
    consent = ListeningConsent.objects.filter(
        user=user, platform=Platform.DISCORD
    ).first()
    if consent is not None and consent.questions_muted:
        return False, "shut_off"
    today = timezone.localdate(now)
    if (
        consent is not None
        and consent.questions_quiet_until
        and consent.questions_quiet_until >= today
    ):
        return False, "quiet"
    if today.weekday() >= 5:
        return False, "weekend"
    return True, ""


def lab_managers(lab) -> list:
    """Who answers for a lab project: its PI and its owners and admins."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from apps.accounts.models import LabMembership

    ids = (
        LabMembership.objects.filter(lab=lab)
        .filter(
            Q(is_lead=True)
            | Q(role__in=[LabMembership.Role.OWNER, LabMembership.Role.ADMIN])
        )
        .values_list("user_id", flat=True)
    )
    return list(get_user_model().objects.filter(pk__in=list(ids)))


# -- the choices that exist for this person ------------------------------------


def _choice(key: str, label: str) -> dict:
    return {"key": key, "label": label}


def choices_for(
    kind: str, *, finding: Finding | None = None, user=None, reason: str = ""
) -> list[dict]:
    """Only the choices that actually exist for this person, today."""
    out: list[dict] = []
    if kind == Kind.INTEREST and finding is not None:
        understanding = finding.understanding_kind
        if understanding == UnderstandingKind.LEARNING_GOAL:
            out.append(_choice("learning", "Yes — note it as something I'm learning"))
        elif understanding == UnderstandingKind.WORK_PREFERENCE:
            out.append(_choice("preference", "Yes — that's how I like to work"))
        elif understanding == UnderstandingKind.CAREER_DIRECTION:
            out.append(_choice("direction", "Yes — that's where I'm heading"))
        else:
            out.append(_choice("reports", "Include it in my reports"))
            budget = finding.budget or {}
            if budget.get("room_for_topic", True):
                out.append(_choice("interests", "Add it to my interests"))
            if budget.get("room_for_cluster"):
                out.append(_choice("theme", "Make it a new theme"))
            elif (budget.get("swap_candidate") or {}).get("label"):
                label = budget["swap_candidate"]["label"]
                out.append(_choice("swap", f"Swap it for “{label}”"))
        if user is not None:
            from apps.research.models import Project

            for project in (
                Project.objects.active().filter(members=user).order_by("name")[:3]
            ):
                out.append(
                    _choice(f"project:{project.pk}", f"It's for {project.name}, not me")
                )
        out.append(_choice("later", "Not now"))
        out.append(_choice("no", "No, and don't ask about this"))
    elif kind == Kind.SKILL:
        out = [
            _choice("skill", "Add it to my skills"),
            _choice("later", "Not now"),
            _choice("no", "No"),
        ]
    elif kind == Kind.DEVELOPMENT:
        out = [
            _choice("yes", "Yes, that happened"),
            _choice("no", "No"),
            _choice("later", "Not sure yet"),
        ]
    elif kind == Kind.INTENT:
        out = [
            _choice("yes", "Yes, update the project's aims"),
            _choice("no", "No, it hasn't changed"),
            _choice("later", "Not now"),
        ]
    elif kind == Kind.CLARIFY:
        if reason == "attribution_unresolved" and user is not None:
            from apps.research.models import Project

            for project in (
                Project.objects.active().filter(members=user).order_by("name")[:4]
            ):
                out.append(_choice(f"project:{project.pk}", project.name))
            out.append(_choice("none", "None of my projects"))
        elif reason == "subject_unclear":
            out = [
                _choice("self", "Yes, my own interest"),
                _choice("other", "No, someone else's idea"),
            ]
        else:  # never_decided
            out = [
                _choice("decided", "Yes, we decided"),
                _choice("open", "No, still open"),
            ]
    elif kind == Kind.REVIEW:
        out = [
            _choice("keep", "Keep exploring it"),
            _choice("drop", "Let it go"),
        ]
    return out


# -- the words -----------------------------------------------------------------


def question_text(s: PendingSuggestion) -> str:
    """The question, in plain language (``docs/styles.md``): specific, short,
    one question, and always "shall I?" — never "I updated"."""
    topic = f"**{s.topic}**"
    lead = (s.explanation or "").strip()
    project = s.project.name if s.project_id else "the project"
    if s.kind == Kind.INTEREST:
        ask = (
            f"Shall I start looking for {topic} for you? Nothing changes unless "
            "you say so; a yes takes effect from tomorrow morning's run."
        )
    elif s.kind == Kind.SKILL:
        ask = f"Shall I add {topic} to your skills? Only if you say so."
    elif s.kind == Kind.DEVELOPMENT:
        ask = (
            f"Did that happen in **{project}**? If it did, I'll note it on the "
            "project from tomorrow's run."
        )
    elif s.kind == Kind.INTENT:
        ask = (
            f"Has what **{project}** is trying to do changed to include {topic}? "
            "I won't touch the project's stated aims unless you say so."
        )
    elif s.kind == Kind.CLARIFY and s.reason == "attribution_unresolved":
        ask = f"Which of your projects was {topic} about?"
    elif s.kind == Kind.CLARIFY and s.reason == "subject_unclear":
        ask = (
            f"Was {topic} your own interest, or someone else's idea you were "
            "discussing?"
        )
    elif s.kind == Kind.CLARIFY:
        ask = f"Did you decide on {topic}, or is it still open?"
    else:  # review
        ask = (
            f"A while ago you asked me to include {topic} in your reports. Keep "
            "exploring it?"
        )
    return f"{lead}\n\n{ask}".strip()


def message(s: PendingSuggestion) -> dict:
    """The Discord payload: the question, and one button per choice."""
    buttons = [
        {
            "type": 2,  # button
            "style": 1 if index == 0 else 2,
            "label": choice["label"][:80],
            "custom_id": f"ambient:{s.pk}:{choice['key']}"[:100],
        }
        for index, choice in enumerate(s.choices[:10])
    ]
    rows = [
        {"type": 1, "components": buttons[i : i + 5]} for i in range(0, len(buttons), 5)
    ]
    return {"content": f"{question_text(s)}\n\n{FOOTER}", "components": rows}


CLOSE = {
    "reports": "Done — I'll include {topic} in your reports from tomorrow morning's run, and ask again in a month whether to keep it.",  # noqa: E501
    "interests": "Done — I'll add {topic} to your interests at tonight's run. You'll see it on your profile, marked as your choice.",  # noqa: E501
    "theme": "Done — {topic} becomes a theme of its own at tonight's run.",
    "swap": "Done — at tonight's run {topic} takes the place of the theme you haven't used. Undo is on your profile page.",  # noqa: E501
    "learning": "Noted — {topic} as something you're learning, from tomorrow's run.",
    "preference": "Noted — I'll keep that in mind when I explain why something fits, from tomorrow's run.",  # noqa: E501
    "direction": "Noted — I'll weigh that when matching fellowships and funding, from tomorrow's run.",  # noqa: E501
    "skill": "Done — I'll add {topic} to your skills at tonight's run.",
    "project": "Got it — I'll note {topic} on that project, not on you.",
    "yes": "Noted on the project from tomorrow's run.",
    "decided": "Thanks — noted as decided.",
    "open": "Thanks — I'll treat it as still open.",
    "self": "Thanks — I'll read it as your own interest.",
    "other": "Thanks — I won't count it as yours.",
    "none": "Thanks — I'll leave it off your projects.",
    "keep": "Done — I'll keep {topic} in your reports and check back in a month.",
    "drop": "Done — {topic} stops being searched for from tomorrow's run. It stays on your page if you change your mind.",  # noqa: E501
    "later": "No problem — I'll leave {topic} alone for a month.",
    "no": "Understood — I won't ask about {topic} again unless you keep coming back to it.",  # noqa: E501
    "unclear": "No problem — I'll leave {topic} as it is for now.",
}


def close_line(choice: str, topic: str) -> str:
    key = choice.split(":", 1)[0]
    return CLOSE.get(key, "Thanks.").format(topic=f"**{topic}**")


# -- reading a reply -----------------------------------------------------------

_SYSTEM = (
    "You read one short reply to a question Mylo, a research lab's assistant, "
    "asked. You decide which of the offered choices the person meant. You never "
    "guess: if the reply does not say, it is unclear. Reply with one JSON object "
    "and nothing else."
)

#: Bump when the reply prompt or its reading changes (EXP-2026-09-015).
READ_VERSION = "r4"

_PROMPT = """Mylo asked:
{question}

The choices were:
{choices}

The person replied:
{reply}

Which choice did they pick? Reply as
{{"choice": one of the choice keys above, or "unclear",
  "correction": if they said yes but want the topic worded differently, their
                wording in at most 8 words, else ""}}

Rules:
- A soft no ("nah, I'm good", "don't worry about it") is "no" — and so is
  anything saying not to bring it up, track it or check in on it again, even
  with "for now".
- Naming a choice is not picking it when they also say to drop it, that they
  are not pursuing it, or not to note or track it: that is "no".
- "Not now", "maybe later", "check back another time" is "later".
- If they do not clearly pick one — undecided, asking a question back, or
  talking about something else — answer "unclear". Never guess a yes."""


@dataclass(frozen=True)
class Reply:
    verdict: str
    choice: str = ""
    correction: str = ""


_YES_KEYS = {
    "reports",
    "interests",
    "theme",
    "swap",
    "learning",
    "preference",
    "direction",
    "skill",
    "yes",
    "decided",
    "self",
    "keep",
}


def verdict_for(choice: str) -> str:
    key = choice.split(":", 1)[0]
    if key in ("no", "drop", "other", "open", "none"):
        return Verdict.REJECTED
    if key == "later":
        return Verdict.DEFER
    return Verdict.CONFIRMED


def direct(s: PendingSuggestion, text: str) -> Reply | None:
    """A reply that *is* a choice — its label or its number — is a button."""
    folded = " ".join((text or "").casefold().split()).strip(" .!")
    for index, choice in enumerate(s.choices, start=1):
        if folded in (
            choice["label"].casefold().strip(" .!"),
            str(index),
            choice["key"],
        ):
            return Reply(verdict_for(choice["key"]), choice["key"])
    return None


def _settings_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component=COMPONENT)
    return client.complete(
        [LLMMessage("system", system), LLMMessage("user", user)]
    ).content


_FILLER = frozenset(
    "a an the it as my me i in on of to for and or as is it's that this".split()
)


def _echoes_a_choice(correction: str, choices: list[dict]) -> bool:
    """Whether a "correction" is only the wording of one of the choices."""
    words = set(re.findall(r"[a-z0-9]+", correction.casefold())) - _FILLER
    if not words:
        return False  # "RL", "GNNs": short names are still names
    labels = set(
        re.findall(r"[a-z0-9]+", " ".join(c["label"] for c in choices).casefold())
    )
    return sum(1 for w in words if w in labels) * 2 >= len(words)


def read_reply(s: PendingSuggestion, text: str, *, complete=None) -> Reply | None:
    """The model's reading of a free-text reply; ``None`` when it cannot be
    reached (the caller asks for a button rather than guessing)."""
    shortcut = direct(s, text)
    if shortcut is not None:
        return shortcut
    ask = complete if complete is not None else _settings_complete
    prompt = _PROMPT.format(
        question=question_text(s),
        choices="\n".join(f"- {c['key']}: {c['label']}" for c in s.choices),
        reply=" ".join((text or "").split())[:600],
    )
    try:
        raw = ask(_SYSTEM, prompt)
    except Exception as exc:  # noqa: BLE001 - unavailable, not broken
        logger.warning("ambient reply reading unavailable (%s)", type(exc).__name__)
        return None
    start = (raw or "").find("{")
    try:
        data, _ = (
            json.JSONDecoder().raw_decode((raw or "")[start:])
            if start >= 0
            else ({}, 0)
        )
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    choice = str(data.get("choice") or "").strip()
    keys = {c["key"] for c in s.choices}
    if choice not in keys:
        return Reply(Verdict.UNCLEAR)
    # The verdict follows the choice, never the other way round: a model that
    # said "confirmed" while picking "no" must not turn a no into a yes
    # (EXP-2026-09-015).
    verdict = verdict_for(choice)
    correction = " ".join(str(data.get("correction") or "").split())[:200]
    if correction and _echoes_a_choice(correction, s.choices):
        # "Mark it down as something I'm learning" picks a choice; it does not
        # rename the topic (EXP-2026-09-015 run 2).
        correction = ""
    if correction and verdict == Verdict.CONFIRMED:
        return Reply(Verdict.CORRECTED, choice, correction)
    return Reply(verdict, choice, "")


# -- shut off ------------------------------------------------------------------

#: "Stop asking about it" answers one question; "stop asking" is a setting.
_ABOUT_ONE = r"(?!\s+(me\s+)?(about|on|re)\s+(it|this|that|them|the)\b)"
_SHUT_OFF = re.compile(
    rf"\b(stop asking{_ABOUT_ONE}|shut (it|them|the questions) off|"
    r"shut off (the |your |these |all )?questions|no more questions|"
    r"leave my interests alone|stop the questions|don'?t ask me"
    rf"{_ABOUT_ONE})\b",
    re.I,
)
_LISTEN_OFF = re.compile(r"\b(stop listening|stop reading|don'?t listen)\b", re.I)
_TURN_ON = re.compile(
    r"\b(start asking( again)?|questions back on|turn (the )?questions (back )?on|"
    r"you can ask (me )?again)\b",
    re.I,
)


def shut_off_request(text: str) -> str | None:
    """``"off"``, ``"off_listening"``, ``"on"``, or None — a control phrase
    said to Mylo, matched literally. This is a switch, not a reading of what
    somebody meant, so a fixed phrase list is the right tool."""
    if _TURN_ON.search(text or ""):
        return "on"
    if _LISTEN_OFF.search(text or ""):
        return "off_listening"
    if _SHUT_OFF.search(text or ""):
        return "off"
    return None


_CONTROL_HINT = re.compile(
    r"\b(question|questions|ask|asking|stop|quit|chill|enough|quiet|pause|"
    r"listen|listening|leave me|off|back on|again)\b",
    re.I,
)

_CONTROL_SYSTEM = (
    "You read one short message a person sent Mylo, their research lab's "
    "assistant, and decide whether it changes a setting. You never guess. "
    "Reply with one JSON object and nothing else."
)

_CONTROL_PROMPT = """The person wrote to Mylo:
{text}

Does this ask Mylo to change how it treats them? Reply as
{{"intent": "stop_questions" | "stop_listening" | "resume" | "none"}}

- stop_questions: stop asking them questions (about their interests, what they
  said) in general — not just about one topic.
- stop_listening: stop reading or listening to what they say in their
  conversations (questions stop too).
- resume: start asking again / turn the questions back on.
- none: anything else, including "stop asking about this one" (that is an
  answer to one question, not a setting), and asking Mylo to stop, pause or
  turn off some other thing — a data sync, a job, a pull, an experiment, a
  reminder."""


def read_control(text: str, *, complete=None) -> str | None:
    """A request, in the person's own words, to stop Mylo's questions, stop
    listening, or resume: ``"off"``, ``"off_listening"``, ``"on"`` or None.

    The literal list (:func:`shut_off_request`) answers first and needs no
    model; this reads the many other ways people say it (EXP-2026-09-015:
    the literal list alone caught none of 40). A message with none of the
    words such a request would use is not sent to the model at all.
    """
    literal = shut_off_request(text)
    if literal is not None:
        return literal
    if not _CONTROL_HINT.search(text or ""):
        return None
    ask = complete if complete is not None else _settings_complete
    try:
        raw = ask(
            _CONTROL_SYSTEM, _CONTROL_PROMPT.format(text=" ".join(text.split())[:600])
        )
    except Exception:  # noqa: BLE001 - without the model, only the literal list
        return None
    start = (raw or "").find("{")
    try:
        data, _ = (
            json.JSONDecoder().raw_decode((raw or "")[start:])
            if start >= 0
            else ({}, 0)
        )
    except ValueError:
        return None
    intent = str((data or {}).get("intent") or "") if isinstance(data, dict) else ""
    return {
        "stop_questions": "off",
        "stop_listening": "off_listening",
        "resume": "on",
    }.get(intent)


def set_questions(user, *, on: bool, listening_too: bool = False, now=None) -> None:
    now = now or timezone.now()
    consent, _ = ListeningConsent.objects.get_or_create(
        user=user, platform=Platform.DISCORD
    )
    consent.questions_muted = not on
    consent.questions_muted_at = now if not on else None
    fields = ["questions_muted", "questions_muted_at", "updated_at"]
    if listening_too and not on:
        consent.enabled = False
        consent.disabled_at = now
        fields += ["enabled", "disabled_at"]
    consent.save(update_fields=fields)
    if not on:
        # Shut off stops the questions at once — including the open ones.
        PendingSuggestion.objects.filter(
            user=user, state__in=PendingSuggestion.OPEN
        ).update(state=PendingSuggestion.State.WITHDRAWN, updated_at=now)


# -- scheduling ----------------------------------------------------------------


def _recently_deferred(user, topic: str, now) -> bool:
    return PendingSuggestion.objects.filter(
        user=user,
        topic=topic,
        verdict=Verdict.DEFER,
        answered_at__gte=now - timedelta(days=DEFER_DAYS),
    ).exists()


def _already_open(user, kind: str, topic: str) -> bool:
    return PendingSuggestion.objects.filter(
        user=user, kind=kind, topic=topic, state__in=PendingSuggestion.OPEN
    ).exists()


def _edge_pending(user, finding: Finding) -> bool:
    from apps.knowledge.read import own_edges

    for edge in own_edges(user):
        if (
            edge.tier == "conversational"
            and edge.relation == finding.relation
            and edge.concept_id == finding.concept_id
        ):
            return edge.status == "pending"
    return False


def _candidates(now) -> list[tuple[object, PendingSuggestion]]:
    """Every question that could be asked tonight, before caps and gates."""
    from apps.knowledge.service import due_for_review

    expires = now + timedelta(days=EXPIRY_DAYS)
    out = []
    explained = Finding.objects.filter(
        explained=Finding.Explained.WRITTEN
    ).select_related("user", "project", "project__scope_lab", "concept")
    for finding in explained.filter(
        outcome__in=[Finding.Outcome.SUGGEST, Finding.Outcome.CAPABILITY],
        user__isnull=False,
        project__isnull=True,
    ):
        if not _edge_pending(finding.user, finding):
            continue  # answered already, or the evidence was withdrawn
        kind = (
            Kind.SKILL
            if finding.outcome == Finding.Outcome.CAPABILITY
            else Kind.INTEREST
        )
        out.append(
            (
                finding.user,
                PendingSuggestion(
                    user=finding.user,
                    kind=kind,
                    finding=finding,
                    concept=finding.concept,
                    relation=finding.relation,
                    topic=finding.topic,
                    explanation=finding.explanation,
                    choices=choices_for(kind, finding=finding, user=finding.user),
                    influence=finding.influence,
                    expires_at=expires,
                ),
            )
        )
    for finding in explained.filter(outcome=Finding.Outcome.ASK, user__isnull=False):
        out.append(
            (
                finding.user,
                PendingSuggestion(
                    user=finding.user,
                    kind=Kind.CLARIFY,
                    finding=finding,
                    concept=finding.concept,
                    relation=finding.relation,
                    topic=finding.topic,
                    reason=finding.reason,
                    explanation=finding.explanation,
                    choices=choices_for(
                        Kind.CLARIFY, user=finding.user, reason=finding.reason
                    ),
                    influence=finding.influence,
                    expires_at=expires,
                ),
            )
        )
    for finding in explained.filter(
        outcome=Finding.Outcome.PROPOSE, project__isnull=False
    ):
        if finding.handled_outcome == Finding.Outcome.PROPOSE:
            continue
        askers = (
            [finding.user]
            if finding.user_id
            else (
                lab_managers(finding.project.scope_lab)
                if finding.project.scope_lab_id
                else []
            )
        )
        for person in askers:
            out.append(
                (
                    person,
                    PendingSuggestion(
                        user=person,
                        kind=Kind.INTENT,
                        finding=finding,
                        project=finding.project,
                        concept=finding.concept,
                        relation=finding.relation,
                        topic=finding.topic,
                        explanation=finding.explanation,
                        choices=choices_for(Kind.INTENT),
                        influence=finding.influence,
                        expires_at=expires,
                    ),
                )
            )
    for development in ProjectDevelopment.objects.filter(
        status=ProjectDevelopment.Status.PENDING
    ).select_related("project", "project__scope_lab", "finding", "speaker"):
        explanation = development.finding.explanation if development.finding_id else ""
        if not explanation:
            continue
        if development.visibility == "lab" and development.project.scope_lab_id:
            askers = lab_managers(development.project.scope_lab)
        else:
            askers = [development.speaker] if development.speaker_id else []
        for person in askers:
            out.append(
                (
                    person,
                    PendingSuggestion(
                        user=person,
                        kind=Kind.DEVELOPMENT,
                        development=development,
                        finding=development.finding,
                        project=development.project,
                        concept=development.concept,
                        topic=development.topic,
                        explanation=explanation,
                        choices=choices_for(Kind.DEVELOPMENT),
                        influence=development.finding.influence
                        if development.finding_id
                        else 0.0,
                        expires_at=expires,
                    ),
                )
            )
    for view, user in due_for_review(timezone.localdate(now)):
        out.append(
            (
                user,
                PendingSuggestion(
                    user=user,
                    kind=Kind.REVIEW,
                    concept_id=view.concept_id,
                    relation=view.relation,
                    topic=view.surface or view.label,
                    choices=choices_for(Kind.REVIEW),
                    influence=view.weight,
                    expires_at=expires,
                ),
            )
        )
    return out


def schedule(*, now=None) -> dict:
    """Tonight's questions: gated, capped, strongest first. Idempotent."""
    now = now or timezone.now()
    counts = {"candidates": 0, "created": 0, "skipped": {}}
    per_day = int(getattr(settings, "AMBIENT_QUESTIONS_PER_DAY", 2))
    today_start = now - timedelta(hours=20)
    candidates = _candidates(now)
    counts["candidates"] = len(candidates)
    candidates.sort(key=lambda pair: -pair[1].influence)
    gate: dict[int, tuple[bool, str]] = {}
    asked_today: dict[int, int] = {}
    for user, suggestion in candidates:
        if user.pk not in gate:
            gate[user.pk] = askable(user, now=now)
            asked_today[user.pk] = PendingSuggestion.objects.filter(
                user=user, created_at__gte=today_start
            ).count()
        ok, why = gate[user.pk]
        if not ok:
            counts["skipped"][why] = counts["skipped"].get(why, 0) + 1
            continue
        if _already_open(user, suggestion.kind, suggestion.topic):
            continue
        if _recently_deferred(user, suggestion.topic, now):
            counts["skipped"]["deferred"] = counts["skipped"].get("deferred", 0) + 1
            continue
        if asked_today[user.pk] >= per_day:
            counts["skipped"]["daily_cap"] = counts["skipped"].get("daily_cap", 0) + 1
            continue
        suggestion.save()
        asked_today[user.pk] += 1
        counts["created"] += 1
    return counts


def expire(*, now=None) -> int:
    """Questions nobody answered in 14 days: closed, and recorded as ignored."""
    now = now or timezone.now()
    stale = list(
        PendingSuggestion.objects.filter(
            state__in=PendingSuggestion.OPEN, expires_at__lt=now
        )
    )
    for suggestion in stale:
        suggestion.state = PendingSuggestion.State.EXPIRED
        suggestion.save(update_fields=["state", "updated_at"])
        _record(suggestion, verdict="ignored", now=now)
    return len(stale)


# -- answering -----------------------------------------------------------------


def _record(suggestion: PendingSuggestion, *, verdict: str, now) -> None:
    finding = suggestion.finding
    ValidationRecord.objects.create(
        suggestion=suggestion,
        user=suggestion.user,
        kind=suggestion.kind,
        understanding_kind=finding.understanding_kind if finding else "",
        topic=suggestion.topic,
        finding_snapshot=(
            {
                "finding": finding.pk,
                "outcome": finding.outcome,
                "reason": finding.reason,
                "facts": finding.facts,
                "influence": finding.influence,
                "trace": finding.trace,
            }
            if finding
            else {}
        ),
        explanation=suggestion.explanation,
        choices=suggestion.choices,
        surface=suggestion.answered_on,
        verdict=verdict,
        choice=suggestion.choice,
        correction=suggestion.correction,
        asked_at=suggestion.asked_at,
        answered_at=suggestion.answered_at,
    )
    feedback = {
        Verdict.CONFIRMED: ObservationFeedback.Verdict.CONFIRMED,
        Verdict.REJECTED: ObservationFeedback.Verdict.REJECTED,
        Verdict.CORRECTED: ObservationFeedback.Verdict.CORRECTED,
        "ignored": ObservationFeedback.Verdict.IGNORED,
        Verdict.DEFER: ObservationFeedback.Verdict.IGNORED,
    }.get(verdict)
    if feedback is None or finding is None:
        return
    channel = (
        ObservationFeedback.Channel.WEB_REVIEW
        if suggestion.answered_on == PendingSuggestion.Surface.WEB
        else ObservationFeedback.Channel.DM_DIALOGUE
    )
    for observation in Observation.objects.filter(pk__in=finding.observation_ids):
        ObservationFeedback.objects.create(
            observation=observation,
            user=suggestion.user,
            verdict=feedback,
            corrected_text=suggestion.correction
            if verdict == Verdict.CORRECTED
            else "",
            channel=channel,
        )


def _apply(suggestion: PendingSuggestion, now) -> None:
    """What the answer does, at once. Profile edits are Plan 08's, tonight."""
    from apps.knowledge import service

    user = suggestion.user
    key = suggestion.choice.split(":", 1)[0]
    verdict = suggestion.verdict
    finding = suggestion.finding
    review = timezone.localdate(now) + timedelta(
        days=int(getattr(settings, "AMBIENT_EXPLORATION_REVIEW_DAYS", 30))
    )
    applied = True
    if suggestion.kind in (Kind.INTEREST, Kind.SKILL) and suggestion.concept_id:
        if verdict in (Verdict.CONFIRMED, Verdict.CORRECTED) and key != "project":
            service.confirm(
                user,
                suggestion.concept_id,
                suggestion.relation,
                review_on=review if key == "reports" else None,
            )
            if verdict == Verdict.CORRECTED and suggestion.correction:
                service.edit_conversational(
                    user,
                    suggestion.concept_id,
                    suggestion.relation,
                    surface=suggestion.correction,
                )
            # An edit to the declared profile waits for Plan 08's applier.
            applied = key == "reports"
            _changed(
                suggestion,
                "exploration_confirmed"
                if key == "reports"
                else "understanding_confirmed",
            )
        elif key == "project" or verdict == Verdict.REJECTED:
            service.reject(user, suggestion.concept_id, suggestion.relation)
            if key == "project" and finding is not None:
                _as_project_fact(suggestion, now)
        else:
            applied = False  # defer / unclear: nothing changes
    elif suggestion.kind == Kind.DEVELOPMENT and suggestion.development_id:
        development = suggestion.development
        if (
            development.status == ProjectDevelopment.Status.PENDING
            and verdict != Verdict.DEFER
        ):
            development.status = (
                ProjectDevelopment.Status.CONFIRMED
                if verdict == Verdict.CONFIRMED
                else ProjectDevelopment.Status.REJECTED
            )
            development.decided_by = suggestion.answered_by or user
            development.decided_at = now
            development.save(
                update_fields=["status", "decided_by", "decided_at", "updated_at"]
            )
            if verdict == Verdict.CONFIRMED:
                _changed(suggestion, "development_confirmed", development=development)
        # The first answer on a lab project closes the question for everyone.
        PendingSuggestion.objects.filter(
            development=development, state__in=PendingSuggestion.OPEN
        ).exclude(pk=suggestion.pk).update(
            state=PendingSuggestion.State.WITHDRAWN, updated_at=now
        )
    elif suggestion.kind == Kind.INTENT:
        applied = verdict != Verdict.CONFIRMED  # a yes is a proposal: Plan 08
        if finding is not None and verdict != Verdict.DEFER:
            Finding.objects.filter(pk=finding.pk).update(
                handled_outcome=Finding.Outcome.PROPOSE, handled_at=now
            )
        if finding is not None:
            PendingSuggestion.objects.filter(
                finding=finding, kind=Kind.INTENT, state__in=PendingSuggestion.OPEN
            ).exclude(pk=suggestion.pk).update(
                state=PendingSuggestion.State.WITHDRAWN, updated_at=now
            )
    elif suggestion.kind == Kind.CLARIFY and finding is not None:
        _clarify(suggestion, key)
    elif suggestion.kind == Kind.REVIEW and suggestion.concept_id:
        if key == "keep":
            service.keep(
                user, suggestion.concept_id, suggestion.relation, review_on=review
            )
            _changed(suggestion, "exploration_kept")
        elif key == "drop":
            service.fade(user, suggestion.concept_id, suggestion.relation)
            _changed(suggestion, "exploration_dropped")
    if applied:
        suggestion.applied_at = now


def _changed(suggestion: PendingSuggestion, kind: str, *, development=None) -> None:
    """What took effect, for the "What changed" feed (Plan 07)."""
    from .review import record

    record(
        suggestion.answered_by or suggestion.user
        if development is not None
        else suggestion.user,
        kind,
        suggestion.correction or suggestion.topic,
        project=development.project if development is not None else suggestion.project,
        surface=suggestion.answered_on,
        suggestion=suggestion,
        development=development,
        finding=suggestion.finding,
        concept_id=suggestion.concept_id,
        relation=suggestion.relation,
        explanation=suggestion.explanation,
        visibility=development.visibility if development is not None else "personal",
    )


def _as_project_fact(suggestion: PendingSuggestion, now) -> None:
    """ "It's for a project, not me": the person placed it; record it there."""
    from apps.research.models import Project

    finding = suggestion.finding
    project_id = suggestion.choice.split(":", 1)[1] if ":" in suggestion.choice else ""
    project = Project.objects.filter(pk=project_id, members=suggestion.user).first()
    if project is None:
        return
    latest = (
        Observation.objects.filter(pk__in=finding.observation_ids)
        .order_by("-observed_at")
        .first()
    )
    if latest is None:
        return
    placed = ProjectDevelopment.objects.create(
        project=project,
        speaker=suggestion.user,
        change="other",
        topic=suggestion.topic,
        concept=suggestion.concept,
        text=latest.text,
        explanation=finding.explanation,
        force=latest.force,
        occurred_on=timezone.localtime(latest.observed_at).date(),
        status=ProjectDevelopment.Status.CONFIRMED,
        origin=ProjectDevelopment.Origin.CONVERSATION,
        visibility="personal",
        finding=finding,
        observation_ids=list(finding.observation_ids),
        decided_by=suggestion.user,
        decided_at=now,
    )
    _changed(suggestion, "development_confirmed", development=placed)


def _clarify(suggestion: PendingSuggestion, key: str) -> None:
    """A clarifying answer corrects Mylo's reading of the observations; the
    next night decides again from the corrected ledger."""
    from apps.research.models import Project

    rows = Observation.objects.filter(pk__in=suggestion.finding.observation_ids)
    if suggestion.reason == "attribution_unresolved" and key == "project":
        project_id = suggestion.choice.split(":", 1)[1]
        project = Project.objects.filter(pk=project_id, members=suggestion.user).first()
        if project is not None:
            rows.filter(speaker=suggestion.user).update(project=project)
    elif suggestion.reason == "subject_unclear":
        rows.filter(speaker=suggestion.user).update(
            subject="self" if key == "self" else "colleague"
        )
    elif key == "decided":
        latest = rows.order_by("-observed_at").first()
        if latest is not None:
            Observation.objects.filter(pk=latest.pk).update(force="decision")


def _reconciled(verdict: str, choice: str) -> str:
    """The verdict an answer is recorded under: the chosen option's, always.

    A caller may say "corrected" for a yes with new wording, or "unclear" for
    no choice at all; it can never make a chosen no or not-now into a yes.
    """
    if not choice:
        return verdict or Verdict.UNCLEAR
    derived = verdict_for(choice)
    if verdict == Verdict.CORRECTED and derived == Verdict.CONFIRMED:
        return Verdict.CORRECTED
    return derived


def answer(
    suggestion: PendingSuggestion,
    *,
    choice: str = "",
    verdict: str = "",
    correction: str = "",
    surface: str,
    by=None,
    now=None,
) -> tuple[bool, str]:
    """Record an answer and apply it. ``(taken, the line to say back)``.

    The first answer wins: a question already answered elsewhere says where.
    """
    now = now or timezone.now()
    with transaction.atomic():
        s = PendingSuggestion.objects.select_for_update().get(pk=suggestion.pk)
        if not s.is_open:
            where = {"dm": "on Discord", "web": "on the web"}.get(s.answered_on, "")
            return False, (
                f"That one's already answered{(' ' + where) if where else ''}."
                if s.state == PendingSuggestion.State.ANSWERED
                else "That question has closed."
            )
        keys = {c["key"].split(":", 1)[0]: c["key"] for c in s.choices}
        full = {c["key"] for c in s.choices}
        if choice and choice not in full and choice.split(":", 1)[0] not in keys:
            return False, "That isn't one of the choices for this question."
        s.verdict = _reconciled(verdict, choice)
        s.choice = choice
        s.correction = correction[:200]
        s.answered_at = now
        s.answered_on = surface
        s.answered_by = by or s.user
        s.state = PendingSuggestion.State.ANSWERED
        _apply(s, now)
        s.save()
        _record(s, verdict=s.verdict, now=now)
    topic = s.correction or s.topic
    line = close_line(
        choice or ("unclear" if s.verdict == Verdict.UNCLEAR else "later"), topic
    )
    return True, line


def _open_asked(user, reply_to: str, now) -> PendingSuggestion | None:
    """The open question a message would be answering, if any."""
    if reply_to:
        from apps.integrations.models import DiscordOutboxMessage

        row = DiscordOutboxMessage.objects.filter(
            discord_message_id=str(reply_to), subject_type="ambient_suggestion"
        ).first()
        if row is not None:
            return PendingSuggestion.objects.filter(
                pk=row.subject_id, user=user
            ).first()
    return (
        PendingSuggestion.objects.filter(
            user=user,
            state=PendingSuggestion.State.ASKED,
            asked_at__gte=now - timedelta(days=3),
        )
        .order_by("-asked_at")
        .first()
    )


def open_for(user) -> list[PendingSuggestion]:
    return list(
        PendingSuggestion.objects.filter(user=user, state__in=PendingSuggestion.OPEN)
        .select_related("project")
        .order_by("-influence", "created_at")
    )


def turn(user, text: str, *, reply_to: str = "", complete=None, now=None) -> str | None:
    """One message a person sent Mylo directly. The reply, or None to stay quiet.

    Control phrases first ("stop asking", "stop listening too", "start asking
    again"). Then, if the message answers one of Mylo's open questions — a
    reply to it, or the latest question asked in the last three days — it is
    read as the answer. Anything else is ordinary conversation, and the
    dialogue says nothing.
    """
    now = now or timezone.now()
    request = shut_off_request(text)
    if request is None and _open_asked(user, reply_to, now) is None:
        # Not answering anything: it may be a request in the person's own words.
        request = read_control(text, complete=complete)
    if request == "on":
        set_questions(user, on=True, now=now)
        return "Questions are back on. I'll ask now and then, never on weekends."
    if request in ("off", "off_listening"):
        set_questions(user, on=False, listening_too=request == "off_listening", now=now)
        if request == "off_listening":
            return (
                "Done — no more questions, and I've stopped listening to your "
                "messages. "
                "Both switches are in your settings if you want them back."
            )
        return (
            "Done — no more questions from me. What I've already understood stays on "
            "your page, and you can turn questions back on in your settings or by "
            "saying “start asking again”."
        )
    target = None
    if reply_to:
        from apps.integrations.models import DiscordOutboxMessage

        row = DiscordOutboxMessage.objects.filter(
            discord_message_id=str(reply_to), subject_type="ambient_suggestion"
        ).first()
        if row is not None:
            target = PendingSuggestion.objects.filter(
                pk=row.subject_id, user=user
            ).first()
            if target is not None and not target.is_open:
                ok, line = answer(target, surface="dm", now=now)
                return line
    if target is None:
        target = (
            PendingSuggestion.objects.filter(
                user=user,
                state=PendingSuggestion.State.ASKED,
                asked_at__gte=now - timedelta(days=3),
            )
            .order_by("-asked_at")
            .first()
        )
    if target is None:
        return None
    PendingSuggestion.objects.filter(pk=target.pk).update(turns=target.turns + 1)
    target.turns += 1
    reply = read_reply(target, text, complete=complete)
    if reply is not None and reply.verdict == Verdict.UNCLEAR:
        # Not an answer to the question — perhaps a request about all of them.
        request = read_control(text, complete=complete)
        if request is not None:
            return turn(
                user,
                "stop asking"
                if request == "off"
                else (
                    "stop listening"
                    if request == "off_listening"
                    else "start asking again"
                ),
                now=now,
            )
    if reply is None:
        return (
            "I couldn't read that just now — could you use one of the buttons on my "
            "question? Nothing has changed."
        )
    if reply.verdict == Verdict.UNCLEAR:
        if target.turns < MAX_TURNS:
            options = ", ".join(c["label"] for c in target.choices[:4])
            return f"Sorry, I didn't follow. For **{target.topic}**: {options}?"
        answer(target, verdict=Verdict.UNCLEAR, surface="dm", now=now)
        return close_line("unclear", target.topic)
    _, line = answer(
        target,
        choice=reply.choice,
        verdict=reply.verdict,
        correction=reply.correction,
        surface="dm",
        now=now,
    )
    return line
