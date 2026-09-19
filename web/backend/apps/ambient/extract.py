"""Conversation in, grounded observations out (Plan 04, extraction).

The pattern the codebase trusts (``state_extract.py``, ``collab/slots.py``): a
fixed schema, deterministic validation, a grounding check, one bounded repair
naming what failed, then refusal of whatever still fails. There is **no
rule-based fallback** (README principle 18): when the model cannot be reached
the window stays unread and the next hour tries again, within the buffer's TTL.

Three checks carry the privacy promise, and each is a line of code rather than
an instruction to the model:

* **Grounding.** The model copies the sentence each observation rests on. That
  sentence must appear, after case, whitespace and punctuation are folded, in
  one of the window's own messages. It is used for the check and then dropped;
  only ``grounded = true`` survives (Plan 01, OD-01c).
* **The speaker is the message's, never the model's.** Whoever wrote the
  matching message is the speaker, so a colleague's words can never be filed
  under somebody else's name by a model that lost track of who said what.
* **No quotes.** The account Mylo keeps is its own words. An account that
  contains the sentence, or shares a run of ``QUOTE_WORDS`` words with any
  message in the window, is refused — "messages are not saved" includes
  fragments of them.

Mylo's own lines, replies to Mylo and reactions on its posts are shown to the
model so the conversation reads coherently, and can never be cited.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from .models import Force, Subject, UnderstandingKind
from .windows import Conversation, Line

logger = logging.getLogger(__name__)

COMPONENT = "ambient_extract"
#: Bump whenever the prompt or the validation changes.
PROMPT_VERSION = "a1"
MAX_ATTEMPTS = 2
MAX_OBSERVATIONS = 8
MAX_TOPIC_WORDS = 6
MAX_TOPIC_CHARS = 80
MIN_ACCOUNT_CHARS = 12
MAX_ACCOUNT_CHARS = 300
MIN_SENTENCE_WORDS = 3
#: A shared run this long between Mylo's account and a message is a quote.
QUOTE_WORDS = 6
MAX_LINE_CHARS = 1200

FACETS = ("problem", "method", "setting", "area")

CompleteFn = Callable[[str, str], str | None]

SYSTEM = (
    "You read a short stretch of a research lab's conversation and note what it "
    "shows about the people in it and their projects. You write your own short "
    "account of each thing, in the third person, and never quote anybody. You "
    "note only what someone actually said; an empty list is a normal answer. "
    "Reply with one JSON object and nothing else."
)

PROMPT = """Below is one conversation. Each numbered line was written by a
person; lines marked (context) were written by Mylo, the lab's assistant, or
are replies and reactions to Mylo — read them for context but never cite them.

Note what the numbered lines show. Reply as
{{"observations": [
  {{"line": the number of the line it rests on,
    "sentence": the exact sentence from that line, copied character for character,
    "kind": one of {kinds},
    "force": one of {forces},
    "subject": one of {subjects},
    "facet": one of {facets},
    "topic": the topic as a short noun phrase of at most {topic_words} words,
    "account": one sentence in your own words saying what the speaker said,
               e.g. "Said they want to try conformal prediction on the imaging
               data." Never copy their wording.,
    "confidence": how sure you are you read it correctly, 0 to 1}}
]}}

kind:
  enduring_interest    a lasting research interest of the speaker's own
  current_curiosity    something the speaker is curious about lately
  work_preference      how the speaker likes to work ("prefers empirical work")
  career_direction     where the speaker wants their career to go
  capability           something the speaker says they have done or can do
                       ("I ran the kriging again", "I built the loader")
  learning_goal        something the speaker wants to learn — not a skill
  project_intent       what a project is trying to show or achieve
  project_development  a concrete change in a project: data arrived, an
                       experiment failed, a venue or deadline moved, a method
                       was dropped or adopted, a blocker opened or closed
A method the speaker discusses because their project needs it, without saying
they want it, is a project_development or project_intent, not an interest.

force: fact (it happened), question, preference, possibility (might, should,
could, next week), decision (we will, we decided), rejection (we dropped it,
not doing that).

subject: self when the speaker is talking about their own view or work;
colleague when they discuss someone else's idea, a paper's claim or a talk;
project or lab when it is about the project or the lab; unknown otherwise.

facet: problem (what is being solved), method (a technique), setting (data, a
population, an instrument, a place), area (a broad field, or none of these).

At most {max_obs} observations. Skip small talk, logistics and anything you
would have to guess.

CONVERSATION
------------
{transcript}
"""

REPAIR = """Your previous answer had these problems:
{failures}

Answer again in the same shape. Drop anything the conversation does not
support rather than rewording it to pass."""


# -- text folding -----------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the and for with that this from are was were our its into than then they "
    "them their there which while will would can could has have had not but all "
    "any use used using new also may these those such been more most other some "
    "when of in on to a an by as at or is be it we i you he she my me so do did "
    "just about what".split()
)


def fold(text: str) -> str:
    """Case, width, punctuation and whitespace folded away — for comparing."""
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    folded = folded.replace("’", "'").replace("‘", "'")
    folded = _PUNCT.sub(" ", folded)
    return _SPACE.sub(" ", folded).strip()


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(fold(text)) if w not in _STOP and len(w) > 1}


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = fold(text).split()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


# -- the result -------------------------------------------------------------------


@dataclass(frozen=True)
class Extracted:
    """One validated observation, still carrying the line it rests on."""

    line: Line
    kind: str
    force: str
    subject: str
    facet: str
    topic: str
    account: str
    confidence: float


@dataclass
class Outcome:
    observations: list[Extracted] = field(default_factory=list)
    #: Validator codes only. Never the messages, which name the sentence.
    refused: list[str] = field(default_factory=list)
    attempts: int = 0
    unavailable: bool = False


# -- the prompt -------------------------------------------------------------------


def _when(line: Line) -> str:
    return f"{line.sent_at:%d %b %H:%M}"


def transcript(conversation: Conversation) -> tuple[str, dict[int, Line]]:
    """The window as numbered lines, and which number is which line.

    Speakers are letters, not names: the model needs to know who is who, not
    who anybody is.
    """
    letters: dict[int, str] = {}
    numbered: dict[int, Line] = {}
    rows: list[str] = []
    evidence = {line.ref_id for line in conversation.evidence}
    number = 0
    for line in conversation.readable:
        text = " ".join((line.text or "").split())[:MAX_LINE_CHARS]
        where = f"#{line.place_label}" if line.place_label else line.place_kind
        if line.ref_id not in evidence:
            who = "Mylo" if line.from_mylo else _letter(letters, line.speaker_id)
            rows.append(f"(context) {who}, {_when(line)}: {text}")
            continue
        number += 1
        numbered[number] = line
        who = _letter(letters, line.speaker_id)
        extra = (
            f", names {line.mentions_count} other person(s)"
            if line.mentions_count
            else ""
        )
        rows.append(f"[{number}] Speaker {who} ({_when(line)}, {where}{extra}): {text}")
    return "\n".join(rows), numbered


def _letter(letters: dict[int, str], speaker_id: int | None) -> str:
    if speaker_id is None:
        return "?"
    if speaker_id not in letters:
        index = len(letters)
        letters[speaker_id] = chr(ord("A") + index) if index < 26 else f"P{index + 1}"
    return letters[speaker_id]


def prompt_for(conversation: Conversation) -> tuple[str, dict[int, Line]]:
    text, numbered = transcript(conversation)
    return (
        PROMPT.format(
            kinds=", ".join(UnderstandingKind.values),
            forces=", ".join(Force.values),
            subjects=", ".join(Subject.values),
            facets=", ".join(FACETS),
            topic_words=MAX_TOPIC_WORDS,
            max_obs=MAX_OBSERVATIONS,
            transcript=text,
        ),
        numbered,
    )


# -- validation -------------------------------------------------------------------


def _parse(raw: str | None) -> dict | None:
    """The first JSON object in the reply; prose and fences around it ignored."""
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _grounded_line(sentence: str, cited: Line | None, lines: list[Line]) -> Line | None:
    """The line the sentence was copied from: the cited one if it is there,
    otherwise whichever line holds it. The speaker comes from this line."""
    needle = fold(sentence)
    if len(needle.split()) < MIN_SENTENCE_WORDS:
        return None
    if cited is not None and needle in fold(cited.text or ""):
        return cited
    for line in lines:
        if needle in fold(line.text or ""):
            return line
    return None


def _quotes(account: str, sentence: str, lines: list[Line]) -> bool:
    folded = fold(account)
    if fold(sentence) and fold(sentence) in folded:
        return True
    grams = _ngrams(account, QUOTE_WORDS)
    if not grams:
        return False
    return any(grams & _ngrams(line.text or "", QUOTE_WORDS) for line in lines)


def validate(
    payload: dict, numbered: dict[int, Line], conversation: Conversation
) -> tuple[list[Extracted], list[str], list[str]]:
    """``(kept, failure messages for the repair, failure codes to store)``."""
    raw = payload.get("observations")
    if not isinstance(raw, list):
        return [], ["observations is not a list"], ["not_a_list"]
    lines = list(numbered.values())
    window_words = (
        set().union(*(_content_words(line.text or "") for line in lines))
        if lines
        else set()
    )
    kept: list[Extracted] = []
    messages: list[str] = []
    codes: list[str] = []
    seen: set[tuple] = set()

    def refuse(code: str, message: str) -> None:
        codes.append(code)
        messages.append(message)

    for entry in raw[: MAX_OBSERVATIONS * 2]:
        if not isinstance(entry, dict):
            refuse("not_an_object", "an observation is not an object")
            continue
        kind = str(entry.get("kind") or "").strip().lower()
        force = str(entry.get("force") or "").strip().lower()
        subject = str(entry.get("subject") or "").strip().lower()
        facet = str(entry.get("facet") or "").strip().lower() or "area"
        topic = " ".join(str(entry.get("topic") or "").split()).strip(" .,;:\"'")
        account = " ".join(str(entry.get("account") or "").split())
        sentence = str(entry.get("sentence") or "")
        try:
            number = int(entry.get("line"))
        except (TypeError, ValueError):
            number = -1
        label = f"line {number}"
        if kind not in UnderstandingKind.values:
            refuse("bad_kind", f"{label}: unknown kind {kind!r}")
            continue
        if force not in Force.values:
            refuse("bad_force", f"{label}: unknown force {force!r}")
            continue
        if subject not in Subject.values:
            refuse("bad_subject", f"{label}: unknown subject {subject!r}")
            continue
        if facet not in FACETS:
            refuse("bad_facet", f"{label}: unknown facet {facet!r}")
            continue
        if (
            not topic
            or len(topic.split()) > MAX_TOPIC_WORDS
            or len(topic) > MAX_TOPIC_CHARS
        ):
            refuse("bad_topic", f"{label}: the topic must be a short noun phrase")
            continue
        if not (_content_words(topic) & window_words):
            refuse(
                "topic_not_in_window",
                f"{label}: the topic {topic!r} is not in the conversation",
            )
            continue
        line = _grounded_line(sentence, numbered.get(number), lines)
        if line is None:
            refuse(
                "not_grounded",
                f"{label}: the sentence is not copied exactly from a numbered line",
            )
            continue
        if not (MIN_ACCOUNT_CHARS <= len(account) <= MAX_ACCOUNT_CHARS):
            refuse("bad_account", f"{label}: the account must be one short sentence")
            continue
        if _quotes(account, sentence, lines):
            refuse(
                "quote_in_account",
                f"{label}: the account copies the speaker's words; say it in your own",
            )
            continue
        try:
            confidence = float(entry.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        key = (line.ref_id, kind, topic.casefold())
        if key in seen:
            continue
        seen.add(key)
        kept.append(
            Extracted(
                line=line,
                kind=kind,
                force=force,
                subject=subject,
                facet=facet,
                topic=topic,
                account=account,
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    if len(kept) > MAX_OBSERVATIONS:
        kept = kept[:MAX_OBSERVATIONS]
        codes.append("too_many")
    return kept, messages, codes


# -- the call ---------------------------------------------------------------------


def _settings_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component=COMPONENT)
    return client.complete(
        [LLMMessage("system", system), LLMMessage("user", user)]
    ).content


def extract(
    conversation: Conversation, *, complete: CompleteFn | None = None
) -> Outcome:
    """Read one conversation. Never raises; ``unavailable`` means try again."""
    if not conversation.evidence:
        return Outcome()
    ask = complete if complete is not None else _settings_complete
    prompt, numbered = prompt_for(conversation)
    base = prompt
    best: Outcome | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = ask(SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001 - unavailable, not broken
            logger.warning("ambient extraction unavailable (%s)", type(exc).__name__)
            if best is None:
                return Outcome(unavailable=True, attempts=attempt)
            break
        payload = _parse(raw)
        if payload is None:
            kept, messages, codes = (
                [],
                ["the reply was not a JSON object"],
                ["not_json"],
            )
        else:
            kept, messages, codes = validate(payload, numbered, conversation)
        outcome = Outcome(observations=kept, refused=codes, attempts=attempt)
        if best is None or len(outcome.observations) >= len(best.observations):
            best = outcome
        if not messages:
            break
        prompt = (
            base + "\n" + REPAIR.format(failures="\n".join(f"- {m}" for m in messages))
        )
    return best or Outcome()
