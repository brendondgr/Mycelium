"""The report body's markdown grammar, in one place.

The report body is GitHub-flavored markdown in a deliberately narrow grammar,
parsed by **two** renderers that must agree exactly: the PDF's flowable builder
(:mod:`apps.content.daily_report_pdf`) and the app's ``MarkdownProse``. They are
in different languages, so the grammar cannot be shared as code — but the rules
can be stated once, here, and each renderer's own tests point at this module.

Three constructs are new in daily v2 (plan 4.2), and each exists because the
report now carries something it did not before:

``[P#]``
    A citation into the references block. Every model-written factual sentence
    about an item carries one (plan H1), and the verifier removes any sentence
    whose citation does not resolve. Rendered as a small marker, not as literal
    brackets in the middle of a sentence.

``[S:path]``
    A project-state marker — "this sentence rests on ``slow.claimed_contribution``".
    It is the state equivalent of a citation and it is **not displayed**: a reader
    does not need to be told which JSON key a sentence came from, but the verifier
    does, and stripping it at render time keeps one body serving both.

``- **Label:** text``
    A labelled beat belonging to the numbered item above it. Previously any
    bullet flushed the open ordered list, which split an alert's four beats away
    from the item they are about and left the title stranded above them.

Everything else is unchanged: ``##``/``###``/``####`` headings, ``N.`` numbered
items whose following plain line is that item's rationale, plain ``-`` bullets,
and blank-line paragraphs. Anything that fails to parse degrades to a paragraph,
which is existing behaviour and the reason a structural deviation never withholds
a report (plan §4.2).
"""

from __future__ import annotations

import re

#: ``[P12]`` — a citation into the references block.
CITATION = re.compile(r"\[P(\d{1,3})\]")

#: ``[S:fast.milestones.m1]`` — a project-state marker. Never displayed.
STATE_MARKER = re.compile(r"\[S:[A-Za-z0-9_.\-\[\]]+\]")

#: ``- **Where you still differ:** …`` — a labelled beat under a numbered item.
LABELLED_BEAT = re.compile(r"^[-*]\s+\*\*([^*]+?):\*\*\s*(.*)$")

#: The heading the code-rendered references block carries. Matched by both
#: renderers so neither treats it as an ordinary heading with a list under it.
REFERENCES_HEADING = "References"


def citations(text: str) -> list[int]:
    """Every citation number in ``text``, in order of appearance, deduped."""
    seen: list[int] = []
    for match in CITATION.finditer(text or ""):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def state_paths(text: str) -> list[str]:
    """Every project-state path ``text`` leans on."""
    return [
        marker[3:-1] for marker in STATE_MARKER.findall(text or "")
    ]


def strip_markers(text: str) -> str:
    """Remove the state markers and tidy the spacing they leave behind.

    Applied by both renderers before display. The markers are grammar for the
    verifier, not prose for the reader.
    """
    out = STATE_MARKER.sub("", text or "")
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def references_block(references: list[dict]) -> str:
    """The code-rendered references block (plan H6).

    ``references`` is ``[{n, title, source, kind}]``. Written by code and never by
    the model: the numbers are the link between a sentence and the item it is
    about, and a model renumbering them would silently re-point every citation in
    the document.
    """
    if not references:
        return ""
    lines = [f"## {REFERENCES_HEADING}"]
    for reference in references:
        bits = [
            str(reference.get("source") or ""),
            str(reference.get("kind") or ""),
        ]
        tail = " · ".join(bit for bit in bits if bit)
        title = str(reference.get("title") or "(untitled)")
        lines.append(
            f"- **[P{reference['n']}]** {title}" + (f" · {tail}" if tail else "")
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The no-scores rule (plan H3 / invariant 4)
# --------------------------------------------------------------------------- #
#: A markdown link, label and target. Both are stripped before the rule below is
#: applied, and for different reasons: a **target** is percent-encoded so often
#: that checking it finds ``%2F`` on half the conference corpus, and a **label**
#: is the source's own title, which Mylo neither wrote nor may censor — a paper
#: genuinely called *Do Multi-Hop QA Scores Track Graph Quality?* has to be
#: nameable.
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")

#: A percentage as a reader reads one: a number, then a sign.
_PERCENT = re.compile(r"\d(?:[\d,.]*)\s*%")

#: The vocabulary of a measurement Mylo did not make. "Score" is included because
#: the percent match it replaced is exactly the thing that must not come back in
#: another spelling.
_SCORE_WORDS = re.compile(r"\b(?:cosine|similarity score|relevance score|scored)\b")


def mylo_prose(text: str) -> str:
    """What Mylo itself wrote — link labels and targets removed.

    The rule below is about Mylo quoting a number as a judgement, not about the
    corpus. Applying it to a title the source chose would mean refusing to name
    real papers, which is a worse failure than the one being prevented.
    """
    return _LINK.sub(" ", text or "")


def score_violations(text: str) -> list[str]:
    """Every place a report states a measurement it is not allowed to state.

    Empty means the text obeys plan H3. Used by the smoke checklist and by the
    renderers' own lint, so there is one definition of the rule rather than three
    that drift.
    """
    prose = mylo_prose(text)
    found = [match.group(0).strip() for match in _PERCENT.finditer(prose)]
    found += [match.group(0) for match in _SCORE_WORDS.finditer(prose.casefold())]
    return found
