"""Is this a call only a department can take on? (plan "What a department sees").

A department channel carries calls a lab could not apply for alone. This module
reads an opportunity's record and returns the reasons it qualifies, each with the
sentence it matched, so a post can quote its evidence:

* **Institutional selection** — a limited submission or institutional nomination:
  someone above the lab has to choose who applies.
* **Department applicant** — the applying unit must be a department, school or
  institution, not an individual investigator's group.
* **Department-scale programme** — training programmes (traineeships, REU sites,
  institutional training grants), centres with a lead institution, and shared
  facilities run for the unit.

**Fit to two or more labs is not a reason**: labs can apply for those themselves.
Detection is code, never the model. Precision was measured before departments
switched on (EXP-2026-11-001): every firing on the corpus snapshot was labelled,
and the five rules that misfired (a per-PI or per-project "no more than", a "no
limit" sentence, a passing mention of core facilities, of Science and Technology
Centers, or of T32 eligibility) were removed rather than tuned to pass. This is
detector v2.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

INSTITUTIONAL = "institutional_selection"
APPLICANT = "department_applicant"
PROGRAMME = "department_programme"

LABELS = {
    INSTITUTIONAL: "Institutional selection",
    APPLICANT: "Department applicant",
    PROGRAMME: "Department-scale programme",
}

#: Detector version, recorded with each stored reason.
VERSION = "v2"

_NUM = r"(?:one|two|three|four|five|six|\d+|\(\d+\)|one \(1\)|two \(2\)|three \(3\))"

_INSTITUTIONAL = [
    (
        "limited_submission",
        re.compile(
            r"\blimited[- ]submission\b",
            re.IGNORECASE,
        ),
    ),
    (
        "institutional_limits",
        re.compile(
            r"institutional submission limits?",
            re.IGNORECASE,
        ),
    ),
    (
        "org_may_submit",
        re.compile(
            r"(?:organizations?|institutions?|universit(?:y|ies)|campus(?:es)?) "
            r"(?:may|can) (?:only )?(?:submit|nominate) (?:no more than |up to |only )?"
            + _NUM,
            re.IGNORECASE,
        ),
    ),
    (
        "each_org_may_submit",
        re.compile(
            r"(?:each|an?) (?:eligible )?(?:organization|institution|university) "
            r"(?:may|can) (?:submit|nominate) (?:no more than |up to |only )?" + _NUM,
            re.IGNORECASE,
        ),
    ),
    (
        "nominated_by",
        re.compile(
            r"nominated by (?:the|their|your|an?) (?:home )?(?:institution|university|"
            r"dean|provost|president|department chair)",
            re.IGNORECASE,
        ),
    ),
    (
        "internal_competition",
        re.compile(
            r"internal (?:competition|selection|pre-?proposal)",
            re.IGNORECASE,
        ),
    ),
]
_APPLICANT = [
    (
        "applicant_must_be_unit",
        re.compile(
            r"applicants? must be (?:a |an )?(?:academic )?(?:departments?|schools?|"
            r"colleges?|academic units?)",
            re.IGNORECASE,
        ),
    ),
    (
        "head_as_pi",
        re.compile(
            r"(?:the )?(?:department|program) (?:head|chair) (?:must|should) "
            r"(?:serve|be) (?:as )?(?:the )?(?:PI|principal investigator)",
            re.IGNORECASE,
        ),
    ),
    (
        "awards_to_departments",
        re.compile(
            r"awards? (?:are|will be) made to (?:academic )?departments",
            re.IGNORECASE,
        ),
    ),
    (
        "department_level",
        re.compile(
            r"\bdepartment(?:al)?[- ]level (?:award|grant|transformation|change)",
            re.IGNORECASE,
        ),
    ),
    (
        "red_program",
        re.compile(
            r"revolutionizing engineering departments",
            re.IGNORECASE,
        ),
    ),
]
_PROGRAMME_TEXT = [
    (
        "research_traineeship",
        re.compile(
            r"\bresearch traineeships?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "traineeship_program",
        re.compile(
            r"\btraineeship program",
            re.IGNORECASE,
        ),
    ),
    (
        "reu_site",
        re.compile(
            r"\bREU sites?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "erc",
        re.compile(
            r"\bengineering research centers?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "shared_instrumentation",
        re.compile(
            r"\bshared (?:instrumentation|instruments?|research facilit(?:y|ies))\b",
            re.IGNORECASE,
        ),
    ),
]
#: NIH activity codes for institutional training, centres and shared instruments.
_PROGRAMME_CODES = {
    "T32": "an institutional research training grant (T32)",
    "T35": "a short-term institutional training grant (T35)",
    "T34": "an undergraduate institutional training grant (T34)",
    "R25": "an education programme for the institution (R25)",
    "P30": "a centre core grant (P30)",
    "P50": "a specialised centre (P50)",
    "U54": "a specialised centre cooperative agreement (U54)",
    "S10": "a shared instrumentation grant (S10)",
}


@dataclass(frozen=True)
class Reason:
    key: str
    label: str
    evidence: str
    field: str
    rule: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def reasons(metadata: dict | None) -> list[Reason]:
    """Every reason this record is department-level, at most one per kind, each
    with the sentence that showed it. Empty for a call a lab could apply for."""
    meta = metadata or {}
    found: dict[str, Reason] = {}
    texts = _texts(meta)
    for field, text in texts:
        for key, patterns in ((INSTITUTIONAL, _INSTITUTIONAL), (APPLICANT, _APPLICANT)):
            if key in found:
                continue
            rule, sentence = _first_match(text, patterns)
            if sentence:
                found[key] = Reason(key, LABELS[key], sentence, field, rule)
    if PROGRAMME not in found:
        codes = [str(c).upper() for c in meta.get("activity_codes") or []]
        hit = next((c for c in codes if c in _PROGRAMME_CODES), None)
        if hit:
            found[PROGRAMME] = Reason(
                PROGRAMME,
                LABELS[PROGRAMME],
                f"Funded as {_PROGRAMME_CODES[hit]}",
                "activity_codes",
                f"code_{hit.lower()}",
            )
    if PROGRAMME not in found:
        for field, text in texts:
            rule, sentence = _first_match(text, _PROGRAMME_TEXT)
            if sentence:
                found[PROGRAMME] = Reason(
                    PROGRAMME, LABELS[PROGRAMME], sentence, field, rule
                )
                break
    order = (INSTITUTIONAL, APPLICANT, PROGRAMME)
    return [found[k] for k in order if k in found]


def _texts(meta: dict) -> list[tuple[str, str]]:
    out = []
    for field in ("title", "name", "eligibility", "description", "cfp_text"):
        value = meta.get(field)
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        if isinstance(value, str) and value.strip():
            out.append((field, value))
    ai = meta.get("ai_fields") or {}
    if isinstance(ai, dict) and isinstance(ai.get("eligibility"), str):
        out.append(("ai_fields.eligibility", ai["eligibility"]))
    return out


_SENTENCE = re.compile(r"[^.!?\n]*[.!?\n]?")


def _first_match(text: str, patterns: list[tuple[str, re.Pattern]]) -> tuple[str, str]:
    """``(rule, sentence)`` for the first pattern that matches; ``("", "")``."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    for rule, pattern in patterns:
        m = pattern.search(clean)
        if not m:
            continue
        stop = clean.rfind(". ", 0, m.start())
        start = 0 if stop == -1 else stop + 2
        end = clean.find(". ", m.end())
        end = len(clean) if end == -1 else end + 1
        sentence = clean[start:end].strip()
        if len(sentence) > 300:
            left = max(m.start() - 120, start)
            sentence = "…" + clean[left : left + 280].strip() + "…"
        return rule, sentence
    return "", ""
