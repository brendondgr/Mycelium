"""EXP-2026-09-017: does "what changed" reach the right reports, and only them?

Run inside the backend container against ``mycelium_sandbox_ambrep`` (a copy of
EXP-2026-09-016's end state), never the development database:

    docker compose exec -T backend sh -c 'cd /app && export DATABASE_URL=${DATABASE_URL%/*}/mycelium_sandbox_ambrep && \
      uv run --project web/backend python web/backend/manage.py shell < .../code/run.py'

Plants shared/unshared projects and one lab-visible told fact per project
through the real recorder, generates every weekly with the real model (8
threads), the drift-on pass, and the dailies, then checks routing from the
stored bodies. Writes ``/app/data/sandbox/exp017.json``.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import review
from apps.ambient.models import AppliedChange, ProjectDevelopment
from apps.content.weekly_changes import PERSONAL_KINDS
from apps.research.models import Project

assert connection.settings_dict["NAME"] == "mycelium_sandbox_ambrep", connection.settings_dict["NAME"]

TODAY = date(2026, 9, 19)
WORKERS = 8
SHARED = {"Project A1", "Project B2", "Project C1"}
started = time.time()
timings = {}
out = {"today": TODAY.isoformat(), "planted": {}, "checks": {}, "violations": []}

# -- plant ----------------------------------------------------------------------
lab_projects = Project.objects.filter(scope_lab__slug__startswith="amb-")
lab_projects.update(share_in_lab_reports=False)
lab_projects.filter(name__in=SHARED).update(share_in_lab_reports=True)
planted = []
for project in lab_projects.order_by("name"):
    speaker = project.members.order_by("username").first()
    change = review.record(
        speaker,
        AppliedChange.Kind.DEVELOPMENT_RECORDED,
        f"{project.name} sandbox milestone reached",
        project=project,
        surface="told",
        visibility="lab",
        explanation="Planted by EXP-2026-09-017.",
    )
    planted.append(change.pk)
out["planted"] = {"shared": sorted(SHARED), "lab_facts": planted}

people = list(User.objects.filter(username__startswith="amb_").order_by("username"))
labs = list(Lab.objects.filter(slug__startswith="amb-").order_by("slug"))

# -- the weeklies, with the model -------------------------------------------------
from apps.content.weekly import generate_weekly_for_lab, generate_weekly_for_user  # noqa: E402


def _user_weekly(user, complete=None):
    close_old_connections()
    try:
        row = generate_weekly_for_user(user, complete=complete, today=TODAY)
        return ("user", user.username, row.body, row.verification or {}, row.origin)
    finally:
        connection.close()


def _lab_weekly(lab, complete=None):
    close_old_connections()
    try:
        row = generate_weekly_for_lab(lab, complete=complete, today=TODAY)
        return ("lab", lab.slug, row.body, row.verification or {}, row.origin)
    finally:
        connection.close()


settings.AMBIENT_DRIFT_ENABLED = False
t = time.time()
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    jobs = [pool.submit(_user_weekly, u) for u in people] + [
        pool.submit(_lab_weekly, lab) for lab in labs
    ]
    weeklies = [job.result() for job in jobs]
timings["weeklies_s"] = round(time.time() - t, 1)
close_old_connections()


def section(body: str) -> list[str]:
    """The "What changed" rows ("- … [O#]") of a body."""
    lines = body.splitlines()
    if "## What changed" not in lines:
        return []
    start = lines.index("## What changed") + 1
    rows = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        rows.append(line)
    return rows


def row_has(row: str, topic: str) -> bool:
    """Whether a "What changed" row is about exactly this topic. By the row's
    structure, never by substring: "Project C1 dataset" is inside "Project C1
    dataset arrival" (run 1's eleven false violations)."""
    return (
        f"**{topic}** —" in row
        or f"— {topic} —" in row
        or f"({topic}) —" in row
    )


# -- expectations, from the change rows and the membership tables ---------------------
since = timezone.make_aware(timezone.datetime.combine(TODAY - timedelta(days=TODAY.weekday()), timezone.datetime.min.time()))
changes = list(
    AppliedChange.objects.filter(created_at__gte=since).select_related("project")
)
# An undo of a change from the same week is shown as "(since undone)" on that
# change's row, not as a row of its own (added after run 1).
_ids = {c.pk for c in changes}
changes = [c for c in changes if not (c.kind == "undone" and c.undo_of_id in _ids)]
members = {
    project.pk: set(project.members.values_list("username", flat=True))
    | ({project.scope_user.username} if project.scope_user_id else set())
    for project in Project.objects.all().select_related("scope_user")
}
owner = {c.pk: c.user.username for c in changes}


def should_see(change, reader_kind, reader) -> bool:
    if reader_kind == "lab":
        return bool(
            change.visibility == "lab"
            and change.kind not in PERSONAL_KINDS
            and change.project_id
            and change.project.scope_lab_id
            and change.project.scope_lab.slug == reader
            and change.project.share_in_lab_reports
        )
    if owner[change.pk] == reader:
        return True
    return bool(
        change.visibility == "lab"
        and change.project_id
        and reader in members.get(change.project_id, set())
    )


by_body = {(kind, who): (body, verification, origin) for kind, who, body, verification, origin in weeklies}
routing = {"rows_expected": 0, "rows_found": 0, "missing": 0, "duplicated": 0, "leaked": 0}
for (kind, who), (body, _v, _o) in by_body.items():
    rows = section(body)
    text_rows = [row for row in rows if re.search(r"\[O\d+\]", row)]
    for change in changes:
        topic = change.topic
        found = sum(1 for row in text_rows if row_has(row, topic))
        want = should_see(change, kind, who)
        # Two people can have changes with the same topic; a row is a leak only
        # if nothing this reader may see carries that topic.
        visible_same_topic = [
            c for c in changes if c.topic == topic and should_see(c, kind, who)
        ]
        if want:
            routing["rows_expected"] += 1
            routing["rows_found"] += min(found, 1)
            if found == 0:
                routing["missing"] += 1
                out["violations"].append({"check": "missing", "reader": who, "topic": topic, "change": change.pk})
            elif found > len(visible_same_topic):
                routing["duplicated"] += 1
                out["violations"].append({"check": "duplicated", "reader": who, "topic": topic, "change": change.pk, "found": found})
        elif found and not visible_same_topic:
            routing["leaked"] += 1
            out["violations"].append({"check": "leaked", "reader": who, "reader_kind": kind, "topic": topic, "change": change.pk, "visibility": change.visibility})
out["checks"]["H1_routing"] = routing

# -- H2: every [O#] resolves; the verifier's record ---------------------------------------
citations = {"bodies": 0, "cited": 0, "unresolved": 0, "model_sentences_citing_O": 0,
             "verifier_removed_O": 0, "examples": []}
for (kind, who), (body, verification, _origin) in by_body.items():
    rows = section(body)
    defined = {int(n) for row in rows for n in re.findall(r"\[O(\d+)\]", row)}
    cited = {int(n) for n in re.findall(r"\[O(\d+)\]", body)}
    citations["bodies"] += 1
    citations["cited"] += len(cited)
    bad = cited - defined
    if bad:
        citations["unresolved"] += len(bad)
        out["violations"].append({"check": "unresolved_O", "reader": who, "numbers": sorted(bad)})
    outside = "\n".join(line for line in body.splitlines() if line not in rows)
    for sentence in re.split(r"(?<=[.!?])\s+", outside):
        if re.search(r"\[O\d+\]", sentence):
            citations["model_sentences_citing_O"] += 1
            if len(citations["examples"]) < 12:
                citations["examples"].append({"reader": who, "sentence": sentence.strip()[:400]})
    for removed in (verification or {}).get("removed_sentences", []):
        if "[O" in removed.get("text", ""):
            citations["verifier_removed_O"] += 1
            citations.setdefault("removed_examples", []).append(removed)
out["checks"]["H2_citations"] = citations

# -- H3: the interpretation line ---------------------------------------------------------
line = "You confirmed an exploration of"
off = sorted(who for (kind, who), (body, _v, _o) in by_body.items() if line in body)
explorers = sorted(
    {c.user.username for c in changes if c.kind == "exploration_confirmed" and c.undone_at is None}
)
settings.AMBIENT_DRIFT_ENABLED = True
t = time.time()
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    drift = [job.result() for job in [pool.submit(_user_weekly, u, lambda _s, _p: "") for u in people]]
timings["drift_pass_s"] = round(time.time() - t, 1)
settings.AMBIENT_DRIFT_ENABLED = False
close_old_connections()
on = sorted(who for _k, who, body, _v, _o in drift if line in body)
out["checks"]["H3_interpretation"] = {
    "drift_off_with_line": off,
    "drift_on_with_line": on,
    "expected": explorers,
    "ok": off == [] and on == explorers,
}
if not out["checks"]["H3_interpretation"]["ok"]:
    out["violations"].append({"check": "interpretation", "off": off, "on": on, "expected": explorers})

# -- H4: the dailies ---------------------------------------------------------------------------
from apps.content.briefing import generate_briefing_for_lab, generate_briefing_for_user  # noqa: E402

now = timezone.now()
day_since = now - timedelta(hours=24)
t = time.time()
dailies = {}
errors = []
for user in people:
    try:
        dailies[("user", user.username)] = generate_briefing_for_user(user, complete=lambda _s, _u: None).body
    except Exception as exc:  # noqa: BLE001 - recorded
        errors.append(f"{user.username}: {type(exc).__name__}: {exc}")
for lab in labs:
    try:
        dailies[("lab", lab.slug)] = generate_briefing_for_lab(lab, complete=lambda _s, _u: None).body
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{lab.slug}: {type(exc).__name__}: {exc}")
timings["dailies_s"] = round(time.time() - t, 1)

recent = [c for c in AppliedChange.objects.filter(created_at__gte=day_since).select_related("project") if c.undone_at is None]
effect_devs = list(
    ProjectDevelopment.objects.filter(change__in=["blocker_closed", "method_dropped"], status__in=["active", "confirmed"])
)


def daily_expected(kind, who) -> bool:
    for change in recent:
        if change.kind == "state_edit" and change.project_id:
            if kind == "lab":
                if change.visibility == "lab" and change.project.share_in_lab_reports and change.project.scope_lab and change.project.scope_lab.slug == who:
                    return True
            elif owner.get(change.pk) == who or (change.visibility == "lab" and who in members.get(change.project_id, set())):
                return True
        if change.kind == "profile_edit" and kind == "user" and change.user.username == who:
            return True
    if kind == "user":
        for dev in effect_devs:
            when = dev.decided_at if dev.status == "confirmed" else dev.recorded_on
            visible = dev.visibility == "lab" or dev.speaker.username == who
            if when and when >= day_since and visible and who in members.get(dev.project_id, set()):
                return True
    return False


daily = {"generated": len(dailies), "errors": errors, "mismatch": [], "lab_development_lines": 0}
for (kind, who), body in dailies.items():
    has = "### Changed today" in body
    if has != daily_expected(kind, who):
        daily["mismatch"].append({"reader": who, "kind": kind, "has": has})
    if kind == "lab" and has:
        block = body.split("### Changed today", 1)[1]
        if "no longer blocks" in block or "was dropped" in block:
            daily["lab_development_lines"] += 1
daily["with_line"] = sorted(who for (kind, who), body in dailies.items() if "### Changed today" in body)
out["checks"]["H4_dailies"] = daily
for row in daily["mismatch"]:
    out["violations"].append({"check": "daily", **row})
if daily["lab_development_lines"]:
    out["violations"].append({"check": "lab_development_line", "n": daily["lab_development_lines"]})

# -- record ------------------------------------------------------------------------------------
timings["total_s"] = round(time.time() - started, 1)
out["timings"] = timings
out["weeklies"] = [
    {"kind": kind, "reader": who, "origin": origin, "what_changed": section(body),
     "verification": {k: v for k, v in (verification or {}).items() if k != "removed_sentences"},
     "body_chars": len(body)}
    for kind, who, body, verification, origin in weeklies
]
out["counts"] = {
    "people": len(people), "labs": len(labs), "changes_this_week": len(changes),
    "weeklies_llm": sum(1 for w in weeklies if w[4] == "llm"),
}
out["violations_total"] = len(out["violations"])
with open("/app/data/sandbox/exp017.json", "w") as handle:
    json.dump(out, handle, indent=1, default=str)
print("RESULT " + json.dumps({"violations": out["violations_total"], "checks": {k: {kk: vv for kk, vv in v.items() if kk not in ("examples", "removed_examples")} for k, v in out["checks"].items()}, "timings": timings}, default=str))
