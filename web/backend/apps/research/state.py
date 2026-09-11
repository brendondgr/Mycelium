"""A project's state: what it claims, what is blocking it, and what is due when.

``Project.goals`` is free-form JSON whose help text promises "goals, methods,
datasets, deadlines" — and only the display fields and the research focus are ever
read. Everything a report would need in order to say something about a *project*
rather than about a topic has had nowhere to live: what the project actually
claims as its contribution, what is standing in its way, when its next milestone
is, and which venues it is aiming at.

This module is that shape. It is split in two because the halves change at
different speeds and for different reasons:

**slow** — the research identity. The problem, the claimed contribution, the
method, the planned components, the data, the open blockers. These move when the
work's direction moves, which is rarely, and every model-written project write-up
is keyed on a fingerprint of them (:func:`slow_fingerprint`). Editing a milestone
date must not re-bill the model for forty write-ups, and it does not, because the
fingerprint covers the slow half alone.

**fast** — the operational state. Stage, milestones, venue targets, constraints,
timeline overrides, expertise needs, and which literature the reader already
knows. These move weekly and are read by the deterministic matchers, which cost
nothing to re-run.

Two rules the rest of the system depends on:

* **Every field carries provenance** — ``stated`` (a person typed or accepted it)
  or ``inferred`` (Mylo proposed it and nobody has confirmed it). Surfaces show
  the difference, and a stated field is never auto-edited (plan H9 / invariant 9).
* **Validation is permissive about what it does not know and strict about shape.**
  Unknown keys are dropped rather than rejected: this state is written by a wizard,
  an extractor and an API, and a schema that 400s on an extra key turns a partial
  answer into no answer at all.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date

#: The slow half — the research identity. A change here invalidates write-ups.
SLOW_FIELDS = (
    "problem",
    "claimed_contribution",
    "method",
    "planned_components",
    "data",
    "blockers",
)

#: The fast half — operational state, read by the deterministic matchers.
FAST_FIELDS = (
    "stage",
    "milestones",
    "venue_targets",
    "constraints",
    "timeline_overrides",
    "needs",
    "known_literature",
    "exclusions",
)

#: Slow fields that are lists of plain strings.
_SLOW_LISTS = ("method", "planned_components", "data")

#: What a milestone can be, and what it means to the timeline matcher. An
#: abstract-only venue is judged against ``results_by`` (you need findings, not
#: prose); a full-paper venue against ``draft_by``.
MILESTONE_KINDS = ("results_by", "draft_by", "submit_by", "other")

#: What a constraint can forbid. ``earliest_start`` is the common real one — "no
#: publication before the industry pitch on 24 Oct" — and it makes a venue *not
#: viable* rather than merely tight, which is a different sentence in a report.
CONSTRAINT_KINDS = ("earliest_start", "latest_end", "embargo", "other")

#: Where a value came from. Nothing else is allowed: "probably" is not provenance.
PROVENANCE_VALUES = ("stated", "inferred")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_TEXT = 2000
_MAX_ITEMS = 40


# --------------------------------------------------------------------------- #
# Normalising
# --------------------------------------------------------------------------- #
def _text(value, limit: int = _MAX_TEXT) -> str:
    return " ".join(str(value or "").split())[:limit]


def _string_list(value) -> list[str]:
    """A clean, deduped list of strings, order preserved."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item, 400)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out[:_MAX_ITEMS]


def _iso_date(value) -> str:
    """An ISO date, or ``""``. Never a guess.

    A milestone Mylo cannot date is a milestone the timeline matcher declines to
    judge — ``no_milestone`` — which is a smaller and more useful answer than a
    date inferred from a phrase like "end of year".
    """
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()[:10]
    return text if _ISO_DATE.match(text) else ""


def _identified(rows, *, prefix: str, fields: dict) -> list[dict]:
    """Normalise a list of ``{id, …}`` records, minting stable ids where absent.

    Ids matter: an alert fires once per ``(target, project, item, trigger)`` and a
    blocker is part of what a trigger points at, so a blocker whose id changed on
    every save would re-fire every alert that mentions it. They are positional
    (``b1``, ``b2``) rather than random so a round-trip through the API is stable.
    """
    if not isinstance(rows, (list, tuple)):
        return []
    out: list[dict] = []
    for index, row in enumerate(rows[:_MAX_ITEMS], start=1):
        if isinstance(row, str):
            row = {"text": row}
        if not isinstance(row, dict):
            continue
        record = {"id": _text(row.get("id"), 40) or f"{prefix}{index}"}
        for name, kind in fields.items():
            raw = row.get(name)
            if kind == "date":
                record[name] = _iso_date(raw)
            elif kind == "provenance":
                record[name] = (
                    str(raw) if str(raw) in PROVENANCE_VALUES else "stated"
                )
            else:
                record[name] = _text(raw, 400)
        if any(record.get(name) for name in fields):
            out.append(record)
    return out


def normalise_slow(payload) -> dict:
    """The slow half, cleaned. Unknown keys are dropped, never rejected."""
    payload = payload if isinstance(payload, dict) else {}
    slow = {
        "problem": _text(payload.get("problem")),
        "claimed_contribution": _text(payload.get("claimed_contribution")),
        "blockers": _identified(
            payload.get("blockers"), prefix="b", fields={"text": "text"}
        ),
    }
    for name in _SLOW_LISTS:
        slow[name] = _string_list(payload.get(name))
    return slow


def normalise_fast(payload) -> dict:
    """The fast half, cleaned."""
    payload = payload if isinstance(payload, dict) else {}
    overrides = payload.get("timeline_overrides")
    overrides = overrides if isinstance(overrides, dict) else {}
    needs = payload.get("needs")
    needs = needs if isinstance(needs, dict) else {}
    known = payload.get("known_literature")
    known = known if isinstance(known, dict) else {}

    milestones = _identified(
        payload.get("milestones"),
        prefix="m",
        fields={"kind": "text", "what": "text", "date": "date", "source": "text"},
    )
    for row in milestones:
        if row["kind"] not in MILESTONE_KINDS:
            row["kind"] = "other"

    constraints = _identified(
        payload.get("constraints"),
        prefix="c",
        fields={
            "kind": "text",
            "applies_to": "text",
            "date": "date",
            "note": "text",
        },
    )
    for row in constraints:
        if row["kind"] not in CONSTRAINT_KINDS:
            row["kind"] = "other"

    return {
        "stage": _text(payload.get("stage"), 80),
        "milestones": milestones,
        "venue_targets": _venue_targets(payload.get("venue_targets")),
        "constraints": constraints,
        "timeline_overrides": {
            "deadline_buffer_days": _optional_int(
                overrides.get("deadline_buffer_days"), 0, 90
            ),
            "min_paper_window_days": _optional_int(
                overrides.get("min_paper_window_days"), 7, 365
            ),
        },
        "needs": {"expertise": _string_list(needs.get("expertise"))},
        "known_literature": {
            "collections": _string_list(known.get("collections")),
            "suppress_known": bool(known.get("suppress_known", True)),
        },
        "exclusions": _string_list(payload.get("exclusions")),
    }


def _venue_targets(value) -> list[dict]:
    """Venue targets as ``{venue, slot, fallback}``, accepting bare names.

    The wizard collects names ("TMLR", "CIKM 2027"); a project that has worked out
    its cycle carries dated slots. Both are the same field, because forcing the
    first shape into the second would mean inventing a date.
    """
    if not isinstance(value, (list, tuple)):
        return []
    out: list[dict] = []
    for item in value[:_MAX_ITEMS]:
        if isinstance(item, str):
            item = {"venue": item}
        if not isinstance(item, dict):
            continue
        venue = _text(item.get("venue"), 200)
        if not venue:
            continue
        out.append(
            {
                "venue": venue,
                "slot": _iso_date(item.get("slot")),
                "fallback": _iso_date(item.get("fallback")),
            }
        )
    return out


def _optional_int(value, low: int, high: int) -> int | None:
    """An in-range integer, or ``None`` meaning "inherit" — never a clamped guess.

    ``None`` is load-bearing: it is how a project says "use the lab's, or mine"
    rather than "use 14". Clamping an out-of-range value to the boundary would
    silently turn a typo into a setting.
    """
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def normalise_provenance(payload, slow: dict, fast: dict) -> dict:
    """``{field: stated|inferred}`` for every populated field, defaulting to stated.

    A field with no recorded provenance is treated as **stated**: the only way a
    value gets into this table without provenance is a hand edit or a migration,
    and both are a person's doing. Mylo's own proposals always record themselves.
    """
    payload = payload if isinstance(payload, dict) else {}
    out: dict[str, str] = {}
    for name in SLOW_FIELDS + FAST_FIELDS:
        value = slow.get(name, fast.get(name))
        if not value:
            continue
        recorded = str(payload.get(name) or "")
        out[name] = recorded if recorded in PROVENANCE_VALUES else "stated"
    return out


def normalise_state(payload: dict | None) -> dict:
    """``{slow, fast, provenance}``, cleaned and complete. Never raises."""
    payload = payload if isinstance(payload, dict) else {}
    slow = normalise_slow(payload.get("slow"))
    fast = normalise_fast(payload.get("fast"))
    return {
        "slow": slow,
        "fast": fast,
        "provenance": normalise_provenance(payload.get("provenance"), slow, fast),
    }


# --------------------------------------------------------------------------- #
# Fingerprinting
# --------------------------------------------------------------------------- #
def slow_fingerprint(slow: dict) -> str:
    """A stable hash of the **slow** half only.

    Stored write-ups record the fingerprint they were written against, and
    ``is_current`` invalidates on it. Hashing the whole state instead would mean
    that moving a milestone by a day re-bills the model for every write-up on the
    project — which is precisely the cost the slow/fast split exists to avoid.

    Sorted keys and a canonical separator, so two equal states always hash equal
    regardless of the order a client happened to send their keys in.
    """
    canonical = json.dumps(
        normalise_slow(slow), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


#: Fast keys that are always populated by normalisation, so their presence says
#: nothing about whether anybody has answered anything. ``needs`` is
#: ``{"expertise": []}`` and ``known_literature`` carries a default flag — both
#: are truthy containers holding nothing, which is exactly the trap a naive
#: ``any()`` falls into.
_STRUCTURAL_FAST_KEYS = ("timeline_overrides", "known_literature", "needs")


def is_empty(state: dict) -> bool:
    """Whether this state says anything at all.

    An all-empty state is not a project that has declared nothing about itself —
    it is a project that has not been **asked** yet, and the surfaces say those
    two things very differently: one is a prompt, the other is a finding.

    Emptiness is judged on content, not on key presence. Normalisation fills in
    every key, several of them with empty containers, so a truthiness test over
    the normalised dict reports "not empty" for a state nobody has touched.
    """
    normalised = normalise_state(state)
    if any(normalised["slow"].values()):
        return False
    for key, value in normalised["fast"].items():
        if key in _STRUCTURAL_FAST_KEYS:
            continue
        if value:
            return False
    # The structural keys count only when someone actually put something in one.
    overrides = normalised["fast"]["timeline_overrides"]
    if any(number is not None for number in overrides.values()):
        return False
    if normalised["fast"]["needs"]["expertise"]:
        return False
    return not normalised["fast"]["known_literature"]["collections"]
