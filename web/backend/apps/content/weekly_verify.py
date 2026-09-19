"""Remove any sentence the packet does not support.

The weekly is the only report where a model writes at length about a project, and
a report that is confidently wrong about a project's own work is worse than no
report: it is wrong in the reader's own domain, where they will notice, and it
takes the correct sentences down with it.

So every model-written sentence is checked against the closed packet it was
written from, and a failing sentence is **removed** rather than flagged or
repaired. Three checks, cheapest first (plan H1/H2):

1. **Resolution.** Every ``[P#]`` in a sentence must be a number the packet
   actually contains. A citation to nothing is worse than no citation, because it
   looks checked.
2. **Citation.** A sentence making a factual claim about an item must carry one.
   "Factual" is decided conservatively — a sentence naming no item and asserting
   no number is prose, and prose is allowed to be uncited.
3. **Numbers and dates.** Every number and every date in a cited sentence must
   appear in the packet. This is the check that stops the single most damaging
   failure mode, which is not a false claim but a *plausible* one: "about four
   awards per cycle" reads exactly like something the source said.

Entailment — whether the packet actually supports the *meaning* — is a fourth
check and is deliberately a seam rather than an implementation (open decision
OD4). It costs a model call per report and its agreement with hand labels has not
been measured, so it is injected by the caller and absent by default. The three
deterministic checks run always and catch the failures that cost the most.

Removal is at sentence granularity, and whole sentences only. A half-removed
sentence reads as a rendering fault, and the reader cannot tell which half was
the problem.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from apps.content.report_grammar import CHANGE_CITATION, CITATION

#: Splits prose into sentences. Deliberately simple: the cost of an occasional
#: bad split is one sentence removed with its neighbour, and the cost of a
#: sophisticated splitter is a dependency in the path that decides what a reader
#: is allowed to read.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")

#: A number the packet must contain: money, a year, an ordinal, a bare integer or
#: decimal. Percentages are handled by the renderer's own lint (plan H3) — they
#: are forbidden outright rather than checked against the packet.
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")

#: An ISO date. Checked separately because a date is the claim most likely to be
#: right in form and wrong in fact.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

#: Numbers a sentence may use without the packet saying them. Small counts of
#: things the sentence itself enumerates ("two of your three benchmarks") are
#: not claims about the source, and requiring the packet to contain "three" would
#: remove correct sentences for using English.
_FREE_NUMBERS = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}

#: What a sentence has to look like before it needs a citation. A sentence with a
#: number or a quoted title is asserting something; one without is prose.
_ASSERTIVE = re.compile(r"\d|\bit (?:reports|releases|tests|finds|shows|uses)\b")


@dataclass
class Removal:
    """One sentence that did not survive, and which check it failed."""

    text: str
    check: str

    def as_dict(self) -> dict:
        return {"text": self.text, "check": self.check}


@dataclass
class Verification:
    """The record stored on the briefing and shown as a one-line footer."""

    claims: int = 0
    supported: int = 0
    removed: int = 0
    unresolved: int = 0
    removed_sentences: list[Removal] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "claims": self.claims,
            "supported": self.supported,
            "removed": self.removed,
            "unresolved": self.unresolved,
            "removed_sentences": [row.as_dict() for row in self.removed_sentences],
        }

    def footer(self) -> str:
        """The one line the report carries about its own checking."""
        if not self.claims:
            return ""
        removed = (
            f" · {self.removed} removed as unsupported" if self.removed else ""
        )
        return (
            f"Checked: {self.claims} claims · {self.supported} supported{removed}. "
            "Dates, day counts, and time zones are computed, not written by the "
            "model."
        )


#: ``(sentence, citations) -> bool``. See the module docstring on why this is a
#: seam rather than an implementation.
EntailmentFn = Callable[[str, list[int]], bool]


def packet_numbers(packet) -> set[str]:
    """Every number and date the packet contains, as strings.

    Normalised the way a reader would read them — commas and currency symbols
    dropped — so "1,200" in the source supports "1200" in the sentence, which is
    the same claim written differently rather than a different claim.
    """
    import json

    text = json.dumps(packet.as_dict() if hasattr(packet, "as_dict") else packet)
    found = {
        match.group(0).replace(",", "").lstrip("$").rstrip("%").rstrip(".")
        for match in _NUMBER.finditer(text)
    }
    found |= set(_DATE.findall(text))
    return {value for value in found if value}


def sentences(text: str) -> list[str]:
    """Prose split into sentences, preserving the text between them exactly."""
    return [part for part in _SENTENCE.split(text or "") if part.strip()]


def verify_line(
    line: str,
    *,
    allowed: set[int],
    numbers: set[str],
    entails: EntailmentFn | None = None,
    changes: set[int] | None = None,
) -> tuple[str, list[Removal]]:
    """One line of prose, with its unsupported sentences removed."""
    kept: list[str] = []
    removed: list[Removal] = []
    changes = changes or set()
    for sentence in sentences(line):
        cited = [int(match.group(1)) for match in CITATION.finditer(sentence)]
        # ``[O#]`` cites a "What changed" row (ambient Plan 09).
        cited_changes = [
            int(match.group(1)) for match in CHANGE_CITATION.finditer(sentence)
        ]
        unresolved = [number for number in cited if number not in allowed] + [
            number for number in cited_changes if number not in changes
        ]
        if unresolved:
            removed.append(Removal(sentence.strip(), "unresolved_citation"))
            continue
        if cited or cited_changes or _ASSERTIVE.search(sentence):
            stated = {
                match.group(0).replace(",", "").lstrip("$").rstrip("%").rstrip(".")
                for match in _NUMBER.finditer(sentence)
            } | set(_DATE.findall(sentence))
            invented = {
                value
                for value in stated
                if value and value not in numbers and value not in _FREE_NUMBERS
            }
            if invented:
                removed.append(Removal(sentence.strip(), "numbers_in_packet"))
                continue
        if cited and entails is not None and not entails(sentence, cited):
            removed.append(Removal(sentence.strip(), "entailment"))
            continue
        kept.append(sentence)
    return " ".join(kept).strip(), removed


def verify_body(
    body: str,
    packet,
    *,
    entails: EntailmentFn | None = None,
) -> tuple[str, Verification]:
    """Check a whole weekly body against its packet. Returns ``(body, record)``.

    Structure is preserved exactly: headings, list markers, blank lines and the
    code-rendered blocks pass through untouched, and only the prose inside a line
    is checked. The alternative — reflowing what survives — would mean the
    verifier decides the document's shape, which is the renderer's job.
    """
    allowed = packet.numbers() if hasattr(packet, "numbers") else set()
    changes = packet.change_numbers() if hasattr(packet, "change_numbers") else set()
    numbers = packet_numbers(packet)
    record = Verification()
    out: list[str] = []

    for raw in (body or "").splitlines():
        stripped = raw.strip()
        # Headings and the code-rendered frame are not model-written prose.
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            out.append(raw)
            continue
        prefix, prose = _split_marker(raw)
        if not prose.strip():
            out.append(raw)
            continue
        record.claims += len(sentences(prose))
        kept, removed = verify_line(
            prose, allowed=allowed, numbers=numbers, entails=entails, changes=changes
        )
        record.removed += len(removed)
        record.unresolved += sum(
            1 for row in removed if row.check == "unresolved_citation"
        )
        record.removed_sentences.extend(removed)
        if kept:
            out.append(f"{prefix}{kept}")
        elif prefix.strip():
            # The marker survives its prose: a numbered item whose every sentence
            # failed still has a title, and dropping the line entirely would
            # renumber everything after it.
            out.append(prefix.rstrip())
    record.supported = max(record.claims - record.removed, 0)
    return "\n".join(out), record


def _split_marker(line: str) -> tuple[str, str]:
    """``("1. ", "the prose")`` — the list marker, and what to check.

    A marker is structure. Checking it would mean an item's number could be
    removed for not appearing in the packet, which is exactly backwards.
    """
    match = re.match(r"^(\s*(?:[-*]\s+|\d{1,3}[.)]\s+)?(?:\*\*[^*]+:\*\*\s*)?)(.*)$",
                     line)
    if match is None:  # pragma: no cover - the pattern matches every string
        return "", line
    return match.group(1), match.group(2)
