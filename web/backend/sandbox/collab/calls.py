"""Planted funding calls: plan CN-03's sandbox validation.

Adds calls to an already-seeded world (EXP-2026-09-005's people, labs and read
papers stay as they are), has the local model write each call from a plan of
its slots, reads the calls with the real slot extractor, writes the team-fit
line for every lab and every person against every call, and scores both the
slots and the coverage against what was planted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import world as world_mod

logger = logging.getLogger(__name__)

ROLES = [
    "a local government authority as a partner",
    "a patient advocacy organisation as a partner",
    "an industry partner",
    "a community organisation as a partner",
    "a minority-serving institution as the lead",
]
FUNDERS = [
    "Northwind Research Foundation",
    "Harbour Science Trust",
    "Meridian Fund for Discovery",
    "Cedar Grove Institute",
    "Lantern Philanthropies",
]
SOURCE = "sandbox"


@dataclass
class PlantedSlot:
    facet: str
    text: str
    required: bool
    method: str = ""  # world Method.key for method slots
    variant: bool = False  # named by a variant rather than the canonical name


@dataclass
class PlantedCall:
    key: str
    field: str
    funder: str
    slots: list[PlantedSlot] = field(default_factory=list)


def build(*, seed: int = 20260918, n: int = 150) -> list[PlantedCall]:
    rng = random.Random(seed * 7 + 3)
    keys = [key for key, _, _ in world_mod.FIELDS]
    calls = []
    for index in range(n):
        home = keys[index % len(keys)]
        call = PlantedCall(key=f"c{index:04d}", field=home, funder=rng.choice(FUNDERS))
        call.slots.append(
            PlantedSlot("problem", rng.choice(world_mod.PROBLEMS[home]), False)
        )
        for method in rng.sample(world_mod.METHODS, k=rng.choice([1, 2])):
            variant = len(method.names) > 1 and rng.random() < 0.3
            name = rng.choice(method.names[1:]) if variant else method.names[0]
            call.slots.append(
                PlantedSlot("method", name, rng.random() < 0.6, method.key, variant)
            )
        if rng.random() < 0.6:
            call.slots.append(
                PlantedSlot("data", rng.choice(world_mod.SETTINGS[home]), False)
            )
        if rng.random() < 0.4:
            call.slots.append(PlantedSlot("role", rng.choice(ROLES), True))
        calls.append(call)
    return calls


SYSTEM = (
    "You write realistic but entirely fictional research funding calls for a "
    "software test. Reply with one JSON object and nothing else."
)

PROMPT = """Write a fictional research funding call from "{funder}".

Plan — every item must appear in the text under exactly the wording given:
{plan}

Rules:
- A 150 to 250 word description in the style of a real call for proposals,
  and a separate one or two sentence eligibility statement.
- Say plainly that applicant teams MUST include each item marked REQUIRED, and
  describe items marked WELCOME as welcome but not required.
- Name no other method, technique, dataset, or partner requirement.
- No real organisations, no URLs, no amounts, no dates.

Reply as {{"title": "...", "description": "...", "eligibility": "..."}}"""


def _plan(call: PlantedCall) -> str:
    lines = []
    for slot in call.slots:
        if slot.facet == "problem":
            lines.append(f'- It funds work on: "{slot.text}"')
        elif slot.facet == "method":
            need = "REQUIRED" if slot.required else "WELCOME"
            lines.append(f'- Expertise in "{slot.text}" ({need})')
        elif slot.facet == "data":
            lines.append(f'- Projects should use "{slot.text}" (WELCOME)')
        else:
            lines.append(f'- It requires "{slot.text}" (REQUIRED)')
    return "\n".join(lines)


def _spec(call: PlantedCall) -> str:
    raw = json.dumps(asdict(call), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def check(call: PlantedCall, text: str) -> list[str]:
    lowered = text.lower()
    return [f"missing {s.text!r}" for s in call.slots if s.text.lower() not in lowered]


def generate(calls, path: Path, *, complete=None, workers: int = 12) -> dict:
    from .corpus import _default_complete

    path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(path.read_text()) if path.exists() else {}
    todo = [c for c in calls if cache.get(c.key, {}).get("spec") != _spec(c)]
    if todo:
        ask = complete or _default_complete()

        def one(call):
            last: dict = {}
            prompt = PROMPT.format(funder=call.funder, plan=_plan(call))
            for _ in range(2):
                try:
                    raw = ask(SYSTEM, prompt) or ""
                    start, end = raw.find("{"), raw.rfind("}")
                    data = json.loads(raw[start : end + 1])
                except Exception as exc:  # noqa: BLE001 - recorded
                    last = {"error": str(exc)}
                    continue
                entry = {
                    "title": " ".join(str(data.get("title") or "").split()),
                    "description": " ".join(str(data.get("description") or "").split()),
                    "eligibility": " ".join(str(data.get("eligibility") or "").split()),
                }
                entry["problems"] = check(
                    call,
                    f"{entry['title']} {entry['description']} {entry['eligibility']}",
                )
                last = entry
                if not entry["problems"]:
                    break
            return last

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for call, result in zip(todo, pool.map(one, todo), strict=True):
                cache[call.key] = {**result, "spec": _spec(call)}
        path.write_text(json.dumps(cache, indent=1, sort_keys=True))
    return {c.key: cache[c.key] for c in calls}


def seed(calls, texts) -> dict:
    from apps.content.models import ContentItem

    from .bootstrap import assert_sandboxed

    assert_sandboxed()
    ContentItem.objects.filter(source=SOURCE).delete()
    items = {}
    for call in calls:
        text = texts.get(call.key) or {}
        items[call.key] = ContentItem.objects.create(
            type="grant",
            source=SOURCE,
            external_id=call.key,
            metadata={
                "title": text.get("title") or call.key,
                "funder": call.funder,
                "description": text.get("description") or "",
                "eligibility": text.get("eligibility") or "",
            },
        )
    return items


def run(items: dict, world) -> dict:
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Lab
    from apps.collab import slots, team_fit
    from apps.content.models import RelevanceScore
    from apps.content.targets import target_for_lab, target_for_user

    from .run import CountingModel

    out: dict = {}
    model = CountingModel(slots._settings_complete)
    started = time.monotonic()
    out["slots_first"] = slots.read_calls(
        list(items.values()), complete=model
    ).as_dict()
    out["slots_seconds"] = round(time.monotonic() - started, 1)
    out["slots_model_calls"] = model.calls
    out["slots_model_failures"] = model.failures
    second = CountingModel(slots._settings_complete)
    out["slots_second"] = slots.read_calls(
        list(items.values()), complete=second
    ).as_dict()
    out["slots_second_model_calls"] = second.calls

    users = list(get_user_model().objects.filter(username__startswith="p"))
    labs = list(Lab.objects.filter(slug__startswith="sandbox-"))
    RelevanceScore.objects.filter(content__source=SOURCE).delete()
    rows = [
        RelevanceScore(content=item, score=0.5, target_user=user)
        for user in users
        for item in items.values()
    ] + [
        RelevanceScore(content=item, score=0.5, target_lab=lab)
        for lab in labs
        for item in items.values()
    ]
    RelevanceScore.objects.bulk_create(rows, batch_size=2000)
    out["score_rows"] = len(rows)

    started = time.monotonic()
    changed = sum(team_fit.annotate_target(target_for_lab(lab)) for lab in labs)
    out["team_fit_labs_seconds"] = round(time.monotonic() - started, 1)
    started = time.monotonic()
    changed += sum(team_fit.annotate_target(target_for_user(user)) for user in users)
    out["team_fit_people_seconds"] = round(time.monotonic() - started, 1)
    out["team_fit_rows_changed"] = changed
    again = sum(team_fit.annotate_target(target_for_lab(lab)) for lab in labs)
    out["team_fit_second_changes"] = again
    return out


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().replace("-", " ").split())


def _words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if len(w) > 2}


def _names_method(text: str) -> set[str]:
    lowered = f" {str(text).lower()} "
    return {
        m.key for m in world_mod.METHODS if any(sig in lowered for sig in m.signature)
    }


def _matches(planted: PlantedSlot, slot: dict) -> bool:
    if slot["facet"] != planted.facet:
        return False
    if _norm(slot["text"]) == _norm(planted.text):
        return True
    if planted.facet == "method":
        return planted.method in _names_method(slot["text"])
    a, b = _words(planted.text), _words(slot["text"])
    return bool(a) and len(a & b) / len(a | b) >= 0.5


def _rate(n: int, d: int):
    return round(n / d, 4) if d else None


def score(world, calls, texts, items, run: dict) -> dict:
    from apps.collab.models import RequirementSlots
    from apps.content.models import RelevanceScore

    people = {p.key: p for p in world.people}
    labs = {lab.key: lab for lab in world.labs}
    rows = {
        str(r.content_id): r
        for r in RequirementSlots.objects.filter(content__source=SOURCE)
    }
    clean = [c for c in calls if not (texts.get(c.key) or {}).get("problems")]

    # --- slots against the plan -------------------------------------------
    by_facet = {
        f: {"planted": 0, "found": 0} for f in ("problem", "method", "data", "role")
    }
    extracted_total = extracted_matched = 0
    required_right = required_total = 0
    matched_slot: dict[tuple[str, int], dict] = {}  # (call key, planted index) -> slot
    role_vectors = 0
    for call in clean:
        row = rows.get(str(items[call.key].pk))
        extracted = list(row.slots) if row else []
        role_vectors += sum(
            1 for s in extracted if s["facet"] == "role" and s.get("vector")
        )
        used: set[int] = set()
        for index, planted in enumerate(call.slots):
            by_facet[planted.facet]["planted"] += 1
            for position, slot in enumerate(extracted):
                if position not in used and _matches(planted, slot):
                    used.add(position)
                    by_facet[planted.facet]["found"] += 1
                    matched_slot[(call.key, index)] = slot
                    required_total += 1
                    required_right += int(
                        bool(slot.get("required")) == planted.required
                    )
                    break
        extracted_total += len(extracted)
        extracted_matched += len(used)

    non_role_planted = sum(v["planted"] for f, v in by_facet.items() if f != "role")
    non_role_found = sum(v["found"] for f, v in by_facet.items() if f != "role")

    # --- coverage against the planted profiles ------------------------------
    def fit_for(item, **target):
        score_row = RelevanceScore.objects.filter(content=item, **target).first()
        return (score_row.signals or {}).get("team_fit") if score_row else None

    def slot_state(fit, slot_text):
        for s in (fit or {}).get("slots") or []:
            if s["text"] == slot_text:
                return s
        return None

    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = {u.username: u for u in User.objects.filter(username__in=list(people))}
    from apps.accounts.models import Lab

    lab_rows = {
        lab.slug.removeprefix("sandbox-"): lab
        for lab in Lab.objects.filter(slug__startswith="sandbox-")
    }

    agree = {
        "lab_canonical": [0, 0],
        "lab_variant": [0, 0],
        "person_canonical": [0, 0],
        "person_variant": [0, 0],
        "person_problem_data": [0, 0],
        "lab_problem_data": [0, 0],
    }
    near_miss = [0, 0]
    role_covered = 0
    named_non_member = 0
    near_of = {}
    for m in world_mod.METHODS:
        if m.near_miss_of:
            near_of.setdefault(m.key, set()).add(m.near_miss_of)
            near_of.setdefault(m.near_miss_of, set()).add(m.key)
    members = {key: {people[k].key for k in lab.members} for key, lab in labs.items()}
    for call in clean:
        item = items[call.key]
        lab_fits = {key: fit_for(item, target_lab=lab) for key, lab in lab_rows.items()}
        person_fits = {
            key: fit_for(item, target_user=user) for key, user in users.items()
        }
        for fits in (lab_fits, person_fits):
            for fit in fits.values():
                for s in (fit or {}).get("slots") or []:
                    role_covered += int(
                        s["facet"] == "role" and s.get("covered_by") is not None
                    )
        for lab_key, fit in lab_fits.items():
            for s in (fit or {}).get("slots") or []:
                named_non_member += sum(
                    1 for who in s.get("people") or [] if who not in members[lab_key]
                )
        for index, planted in enumerate(call.slots):
            slot = matched_slot.get((call.key, index))
            if slot is None or planted.facet == "role":
                continue
            for lab_key, fit in lab_fits.items():
                state = slot_state(fit, slot["text"])
                got = bool(state and state.get("covered_by") == "lab")
                if planted.facet == "method":
                    expected = any(
                        planted.method in people[k].methods[:2]
                        for k in labs[lab_key].members
                    )
                    bucket = "lab_variant" if planted.variant else "lab_canonical"
                    held = {
                        m for k in labs[lab_key].members for m in people[k].methods[:2]
                    }
                else:
                    expected = any(
                        _norm(people[k].declared_only) == _norm(planted.text)
                        for k in labs[lab_key].members
                    )
                    bucket = "lab_problem_data"
                    held = set()
                agree[bucket][0] += int(got == expected)
                agree[bucket][1] += 1
                if (
                    planted.facet == "method"
                    and got
                    and not expected
                    and (near_of.get(planted.method, set()) & held)
                ):
                    near_miss[0] += 1
            for person_key, fit in person_fits.items():
                person = people[person_key]
                state = slot_state(fit, slot["text"])
                got = bool(state and state.get("covered_by") == "you")
                if planted.facet == "method":
                    expected = planted.method in person.methods
                    bucket = "person_variant" if planted.variant else "person_canonical"
                    held = set(person.methods)
                elif planted.facet == "problem":
                    expected = any(
                        _norm(p.problem) == _norm(planted.text) for p in person.papers
                    ) or _norm(person.declared_only) == _norm(planted.text)
                    bucket, held = "person_problem_data", set()
                else:
                    expected = any(
                        _norm(p.setting) == _norm(planted.text) for p in person.papers
                    )
                    bucket, held = "person_problem_data", set()
                agree[bucket][0] += int(got == expected)
                agree[bucket][1] += 1
                if (
                    planted.facet == "method"
                    and got
                    and not expected
                    and (near_of.get(planted.method, set()) & held)
                ):
                    near_miss[0] += 1
                if planted.facet == "method":
                    near_miss[1] += 1

    invariants = {
        "role_slots_covered": role_covered,
        "role_slots_with_a_vector": role_vectors,
        "lab_named_non_member": named_non_member,
        "slots_second_pass_reads": run.get("slots_second", {}).get("read", -1),
        "slots_second_pass_model_calls": run.get("slots_second_model_calls", -1),
        "team_fit_second_pass_changes": run.get("team_fit_second_changes", -1),
    }
    return {
        "calls": len(calls),
        "calls_clean": len(clean),
        "generator_slips": len(calls) - len(clean),
        "slot_recall_non_role": _rate(non_role_found, non_role_planted),
        "slot_precision": _rate(extracted_matched, extracted_total),
        "slot_recall_by_facet": {
            f: _rate(v["found"], v["planted"]) for f, v in by_facet.items()
        },
        "slot_required_agreement": _rate(required_right, required_total),
        "coverage_agreement": {k: _rate(*v) for k, v in agree.items()},
        "coverage_pairs": {k: v[1] for k, v in agree.items()},
        "coverage_agreement_lab_canonical": _rate(*agree["lab_canonical"]),
        "near_miss_false_cover": near_miss[0],
        "near_miss_false_cover_rate": _rate(*near_miss),
        "invariants": invariants,
        "run": run,
    }


def failures(metrics: dict) -> list[str]:
    return [f"{k} = {v}" for k, v in metrics["invariants"].items() if v != 0]
