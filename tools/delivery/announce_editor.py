"""The bounded editor behind each announcement (plan D4).

Code decides the facts — dates, amounts, eligibility, who suits it — and hands the
editor a closed packet. The editor decides whether the item is worth a post and
writes four things: a headline, *Why it matters*, *Who should look* and *Next step*.
It sees nothing else: no web, no other target's data.

*Who should look* names project teams or people from the packet, and says in plain
words what the opportunity would do for them: for a project team, what it serves in
that project's work; for a person not reached through a project, why it fits their
own stated interests. The packet carries only projects the lab shares in its
reports, each with its focus and its team, and each person's interests and shared
projects, so the sentence can be specific without the editor inventing anything.

A verifier then holds it to that:

* every project or person it names must be one the packet offered;
* its prose may contain **no digit at all**, so a date or an amount can only ever
  come from code, never from the model's memory — with one exception: the headline
  may repeat a word of the item's own title that holds a digit ("AACL 2026",
  "13th"), since that came from the record, not the model;
* every field must be present and short.

Anything that fails, or a model that is unavailable, falls back to a template
built from the same packet. A write-up is keyed on (item, target, rubric version,
theme-areas fingerprint, item text), so a re-run with nothing changed costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

RUBRIC_VERSION = "ann-2"
_DIGIT = re.compile(r"\d")
_LIMITS = {"headline": 120, "why_it_matters": 420, "next_step": 220, "why": 200}
#: How many entries *Who should look* holds (projects and people together).
MAX_LOOKERS = 4

SYSTEM_PROMPT = """You edit Mylo's opportunity announcements for a research lab or \
department. You get one opportunity and facts about it that code has already checked.

Decide whether it deserves its own post, then write it. Rules:
- Write plain, specific sentences for researchers. No hype, no exclamation marks.
- Never write a digit: no dates, amounts, counts or percentages. Code adds those.
- The headline is not the title: do not repeat the title, its year or its edition.
- Say why it matters to this team's stated theme and projects, not in general.
- "who_should_look" holds up to four entries, each naming one project (its "j" \
id) or one person (their "p" id) from the lists given; for a department, labs \
(their "l" id). Never invent anyone, and never name a person in a department post.
  - When the opportunity fits a listed project, name the project and say in one \
sentence what it would do for that project's work: a venue for its results, money \
for its next stage, training or a fellowship for someone on it. Name the part of \
the project's focus it serves.
  - Name a person only when they are not already reached through a project you \
named, and ground their sentence in their own stated interests.
  - Write why they would want it, not that they match. Never write "X's research \
on A matches the B focus of C", and do not copy Mylo's matching notes.
- "next_step" is one concrete action the team could take this week.
- If a check failed or the fit is weak, set "announce" to false and give a short \
"skip_reason".

Reply with JSON only:
{"announce": true, "headline": "...", "why_it_matters": "...", \
"who_should_look": [{"id": "j1", "why": "..."}, {"id": "p2", "why": "..."}], \
"next_step": "...", \
"skip_reason": ""}"""


@dataclass
class Packet:
    """Everything the editor may see about one item for one target."""

    item_id: str
    kind: str
    title: str
    funder: str
    summary: str
    target_name: str
    target_kind: str  # "lab" | "department"
    label: str
    theme: str
    theme_notes: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    #: [{"id", "name", "why", "projects"?, "interests"?}] — "why" is Mylo's matching
    #: note; "projects" are the shared projects they are on.
    people: list[dict] = field(default_factory=list)
    #: Shared lab projects this item touches: [{"id", "name", "focus", "members"}].
    project_teams: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)  # usability checks
    next_step_hint: str = ""
    #: Department posts: why only a department can take this on, with evidence.
    dept_reasons: list[dict] = field(default_factory=list)

    def prompt(self) -> str:
        lines = [
            f"TEAM: {self.target_name} ({self.target_kind})",
            f"THEME: {self.theme or '(none named)'}",
        ]
        if self.theme_notes:
            lines.append("WHY MYLO MATCHED IT: " + " ".join(self.theme_notes))
        if self.project_teams:
            lines.append("PROJECTS IT TOUCHES (name one by its id):")
            for t in self.project_teams:
                line = f"  - {t['id']}: {t['name']}"
                if t.get("focus"):
                    line += f" — focus: {t['focus']}"
                if t.get("members"):
                    line += f". Team: {', '.join(t['members'])}"
                lines.append(line)
        elif self.projects:
            lines.append("PROJECTS IT TOUCHES: " + "; ".join(self.projects))
        lines += [
            f"OPPORTUNITY ({self.kind}, {self.label}): {self.title}",
            f"FUNDER/HOST: {self.funder or 'not listed'}",
            f"SUMMARY: {self.summary or 'none'}",
            "CHECKS (already verified by code):",
        ]
        lines += [f"  - {c['status']}: {c['label']}" for c in self.checks]
        if self.dept_reasons:
            lines.append("WHY ONLY A DEPARTMENT CAN TAKE IT ON:")
            lines += [f"  - {r['label']}: {r['evidence']}" for r in self.dept_reasons]
        # A department post names labs, never people; the list is labelled so.
        dept = self.target_kind == "department"
        lines.append("LABS THAT COULD LEAD:" if dept else "PEOPLE:")
        if self.people:
            for p in self.people:
                line = f"  - {p['id']}: {p['name']}"
                if p.get("projects"):
                    line += f" — on projects: {', '.join(p['projects'])}"
                if p.get("interests"):
                    line += f" — interests: {p['interests']}"
                lines.append(line + f" — Mylo's matching note: {p['why']}")
        else:
            lines.append("  (none)")
        return "\n".join(lines)


@dataclass(frozen=True)
class WriteUp:
    announce: bool
    headline: str
    why_it_matters: str
    #: [{"id", "name", "why"}], plus "kind": "project" and "members" for a project.
    who_should_look: tuple[dict, ...]
    next_step: str
    skip_reason: str = ""
    source: str = "template"  # "editor" | "template"

    def as_dict(self) -> dict:
        return {
            "announce": self.announce,
            "headline": self.headline,
            "why_it_matters": self.why_it_matters,
            "who_should_look": [dict(p) for p in self.who_should_look],
            "next_step": self.next_step,
            "skip_reason": self.skip_reason,
            "source": self.source,
            "rubric_version": RUBRIC_VERSION,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WriteUp:
        return cls(
            announce=bool(data.get("announce", True)),
            headline=data.get("headline", ""),
            why_it_matters=data.get("why_it_matters", ""),
            who_should_look=tuple(data.get("who_should_look") or ()),
            next_step=data.get("next_step", ""),
            skip_reason=data.get("skip_reason", ""),
            source=data.get("source", "template"),
        )


def write_up_key(
    packet: Packet, *, target_key: str, areas_fp: str, text_fp: str
) -> str:
    payload = "␟".join(
        [packet.item_id, target_key, RUBRIC_VERSION, areas_fp, text_fp, packet.label]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Verifier
# --------------------------------------------------------------------------- #
class Rejected(ValueError):
    """The editor's output broke a rule; the reason is the message."""


def verify(raw: str | None, packet: Packet) -> WriteUp:
    """Parse and check the editor's reply, or raise :class:`Rejected`."""
    if not raw:
        raise Rejected("empty reply")
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end < start:
        raise Rejected("no JSON object")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise Rejected(f"bad JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise Rejected("not an object")

    announce = data.get("announce")
    if not isinstance(announce, bool):
        raise Rejected("announce must be true or false")
    if not announce:
        reason = _clean(data.get("skip_reason"))
        if not reason:
            raise Rejected("a skip needs a reason")
        _no_digits("skip_reason", reason)
        return WriteUp(False, "", "", (), "", skip_reason=reason[:200], source="editor")

    out = {}
    for key in ("headline", "why_it_matters", "next_step"):
        value = _clean(data.get(key))
        if not value:
            raise Rejected(f"{key} is missing")
        if len(value) > _LIMITS[key]:
            raise Rejected(f"{key} is too long")
        _no_digits(
            key,
            _without_title_words(value, packet.title) if key == "headline" else value,
        )
        out[key] = value

    offered = {p["id"]: p for p in packet.people}
    teams = {t["id"]: t for t in packet.project_teams}
    people = []
    for row in data.get("who_should_look") or []:
        if not isinstance(row, dict):
            raise Rejected("who_should_look rows must be objects")
        pid = str(row.get("id") or "")
        if pid not in offered and pid not in teams:
            raise Rejected(f"names someone not in the packet: {pid!r}")
        why = _shorten(_clean(row.get("why")), _LIMITS["why"])
        _no_digits("who_should_look", why)
        if any(p["id"] == pid for p in people):
            continue  # named twice: once says it
        people.append(_looker(pid, why, offered, teams))
    # Someone already reached through a project named above is not listed again:
    # the project's sentence says why they would want it.
    reached = {m for p in people if p.get("kind") == "project" for m in p["members"]}
    people = [
        p for p in people if p.get("kind") == "project" or p["name"] not in reached
    ]
    people = people[:MAX_LOOKERS]
    return WriteUp(
        True,
        out["headline"],
        out["why_it_matters"],
        tuple(people),
        out["next_step"],
        source="editor",
    )


def _looker(pid: str, why: str, offered: dict, teams: dict) -> dict:
    if pid in teams:
        team = teams[pid]
        return {
            "id": pid,
            "kind": "project",
            "name": team["name"],
            "members": list(team.get("members") or []),
            "why": why,
        }
    return {"id": pid, "name": offered[pid]["name"], "why": why}


def looker_label(entry: dict, *, bold: bool = True) -> str:
    """How one *Who should look* entry is named on a surface: a project as
    ``Name project (Ana, Ben)``, a person or a lab by name."""
    name = entry.get("name") or ""
    name = f"**{name}**" if bold and name else name
    if entry.get("kind") == "project":
        members = ", ".join(entry.get("members") or [])
        return f"{name} project" + (f" ({members})" if members else "")
    return name


def _shorten(text: str, limit: int) -> str:
    """A reason that runs long is trimmed at a word, not thrown away with the rest
    of a good write-up."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _without_title_words(text: str, title: str) -> str:
    """``text`` with every word that also appears in ``title`` removed, so a digit
    the headline copied from the item's own title ("AACL 2026") is not held against
    it; any other digit still is."""
    words = {w.casefold() for w in re.findall(r"[\w'’-]+", title or "")}
    return re.sub(
        r"[\w'’-]+",
        lambda m: "" if m.group(0).casefold() in words else m.group(0),
        text,
    )


def _no_digits(key: str, value: str) -> None:
    if _DIGIT.search(value):
        raise Rejected(f"{key} contains a digit")


# --------------------------------------------------------------------------- #
# Template — the fallback, built from the same packet
# --------------------------------------------------------------------------- #
def template(packet: Packet) -> WriteUp:
    reach = f"your **{packet.theme}** theme" if packet.theme else "your research"
    why = f"Fits {reach}"
    if packet.projects:
        named = ", ".join(f"**{p}**" for p in packet.projects[:2])
        why += f" and the {named} project{'s' if len(packet.projects) > 1 else ''}"
    why += "."
    if packet.summary:
        why += " " + _first_sentence(packet.summary)
    lookers: list[dict] = []
    reached: set[str] = set()
    for team in packet.project_teams:
        lookers.append(
            {
                "id": team["id"],
                "kind": "project",
                "name": team["name"],
                "members": list(team.get("members") or []),
                "why": "Mylo matched it to this project's work.",
            }
        )
        reached.update(team.get("members") or [])
    for p in packet.people:
        if p["name"] not in reached:
            lookers.append({"id": p["id"], "name": p["name"], "why": p["why"]})
    people = tuple(lookers[:MAX_LOOKERS])
    return WriteUp(
        True,
        packet.title[: _LIMITS["headline"]],
        why[: _LIMITS["why_it_matters"]],
        people,
        packet.next_step_hint or "Read the call and decide whether it is worth a team.",
        source="template",
    )


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    match = re.match(r"(.{20,300}?[.!?])(\s|$)", text)
    return match.group(1) if match else text[:300]


# --------------------------------------------------------------------------- #
# Running the editor
# --------------------------------------------------------------------------- #
def _model_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="announcements")
    response = client.complete(
        [LLMMessage("system", SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    return response.content


def edit(
    packet: Packet,
    *,
    complete: Callable[[str], str | None] | None = _model_complete,
) -> tuple[WriteUp, str]:
    """``(write_up, note)``. ``complete=None`` skips the model (dry runs, tests).

    The note says why the template was used, or is empty when the editor's reply
    passed the verifier.
    """
    if complete is None:
        return template(packet), "model not called"
    try:
        raw = complete(packet.prompt())
    except Exception as exc:  # noqa: BLE001 — any model failure means the template
        return template(packet), f"model unavailable: {type(exc).__name__}"
    try:
        return verify(raw, packet), ""
    except Rejected as exc:
        return template(packet), f"rejected: {exc}"
