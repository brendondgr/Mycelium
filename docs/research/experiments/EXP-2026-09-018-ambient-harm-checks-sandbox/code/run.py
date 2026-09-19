"""EXP-2026-09-018: the harm checks on the sandbox record, then each violation
injected alone (in a rolled-back transaction) to see it caught and nothing
else moved. Writes /app/data/sandbox/exp018.json.

    DATABASE_URL=.../mycelium_sandbox_ambeval manage.py shell < .../code/run.py
"""

import json
import time
from collections import Counter
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.utils import timezone

from apps.ambient.models import (
    AppliedChange,
    Observation,
    PendingSuggestion,
    Retraction,
)
from apps.ambient.read import evaluation_report
from apps.content.models import DailyBriefing
from apps.knowledge.models import Concept, Edge

assert connection.settings_dict["NAME"] == "mycelium_sandbox_ambeval", connection.settings_dict["NAME"]
started = time.time()
now = timezone.now()


def lab_reports():
    return list(DailyBriefing.objects.filter(lab__isnull=False).values_list("pk", "body"))


def counts():
    report = evaluation_report(
        since=now - timedelta(days=60), until=now + timedelta(days=60),
        lab_reports=lab_reports(),
    )
    checks = {k: v["count"] for k, v in report["harm_checks"].items() if not k.startswith("_")}
    return checks, report


baseline, clean = counts()
out = {
    "clean": {
        "checks": baseline,
        "examples": {k: v["examples"] for k, v in clean["harm_checks"].items() if not k.startswith("_")},
        "info": clean["harm_checks"]["_info"],
        "validation_precision": clean["validation_precision"],
        "maintenance": clean["maintenance"],
    }
}

# The cap hits, for the hand check against the harness logs.
per_day = Counter(
    (user_id, timezone.localtime(asked_at).date().isoformat())
    for user_id, asked_at in PendingSuggestion.objects.filter(asked_at__isnull=False).values_list("user_id", "asked_at")
)
out["clean"]["cap_hits"] = sorted(
    [{"user": User.objects.get(pk=u).username, "day": d, "asked": n} for (u, d), n in per_day.items() if n > 2],
    key=lambda row: (row["day"], row["user"]),
)

person = User.objects.filter(username="amb_b3_cyra").get()
observation = Observation.objects.filter(speaker=person).first()
lab_body_id = DailyBriefing.objects.filter(lab__isnull=False).values_list("pk", flat=True).first()


def inject_profile_edit():
    AppliedChange.objects.create(user=person, kind="profile_edit", topic="injected", field="interests.skills")


def inject_state_edit():
    from apps.research.models import Project

    project = Project.objects.filter(members=person).first()
    AppliedChange.objects.create(user=person, kind="state_edit", topic="injected", field="slow.blockers", project=project)


def inject_unconfirmed_change():
    AppliedChange.objects.create(user=person, kind="understanding_confirmed", topic="injected", surface="dm")


def inject_personal_in_lab_report():
    AppliedChange.objects.create(user=person, kind="profile_edit", topic="injected private topic", field="x",
                                 suggestion=PendingSuggestion.objects.filter(user=person, verdict="confirmed", state="answered").first())
    body = DailyBriefing.objects.get(pk=lab_body_id).body + "\n\n## What changed\n### Projects\n- **injected private topic** — added. [O99]"
    DailyBriefing.objects.filter(pk=lab_body_id).update(body=body)


def inject_over_cap():
    day = now + timedelta(days=40)
    for n in range(3):
        PendingSuggestion.objects.create(user=person, kind="interest", topic=f"injected {n}", state="asked",
                                         asked_at=day, expires_at=day + timedelta(days=14))


def inject_quotation():
    Observation.objects.filter(pk=observation.pk).update(
        text='Said "we are going to run every ablation again before the deadline" in the lab channel.')


def inject_after_opt_out():
    # A person of their own, with one observation, so one violation is one row.
    from apps.integrations.models import DiscordIdentity

    leaver = User.objects.create_user("injected-leaver", "l@example.invalid", "x")
    DiscordIdentity.objects.create(user=leaver, discord_user_id="999000999",
                                   link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
                                   state=DiscordIdentity.State.ACTIVE)
    Observation.objects.create(
        source=observation.source, speaker=leaver, external_message_ids=["x"],
        observed_at=now, text="Said they are moving to a new lab.", subject="self",
        understanding_kind="career_direction", force="plan", place_kind="dm",
        visibility="personal", topic="moving labs",
    )
    Retraction.objects.create(reason=Retraction.Reason.OPT_OUT, user=leaver)


def inject_unlinked():
    stranger = User.objects.create_user("injected-stranger", "s@example.invalid", "x")
    Observation.objects.filter(pk=observation.pk).update(speaker=stranger)


def inject_declined_again():
    concept = Concept.objects.create(label="injected concept", facet="method", scope="global")
    PendingSuggestion.objects.create(user=person, kind="interest", topic="injected concept", concept=concept,
                                     state="answered", verdict="rejected", choice="no",
                                     asked_at=now + timedelta(days=41), answered_at=now + timedelta(days=41),
                                     expires_at=now + timedelta(days=55))
    PendingSuggestion.objects.create(user=person, kind="interest", topic="injected concept again", concept=concept,
                                     state="asked", asked_at=now + timedelta(days=45),
                                     expires_at=now + timedelta(days=59))


def inject_covered():
    concept = Concept.objects.create(label="injected covered", facet="method", scope="global")
    Edge.objects.create(user=person, concept=concept, relation="interested_in", tier="declared")
    PendingSuggestion.objects.create(user=person, kind="interest", topic="injected covered", concept=concept,
                                     state="asked", asked_at=now + timedelta(days=42),
                                     expires_at=now + timedelta(days=56))


def inject_rule_origin():
    Observation.objects.filter(pk=observation.pk).update(origin="rule")


INJECTIONS = {
    "stated_field_without_a_yes": [inject_profile_edit, inject_state_edit],
    "change_without_a_confirmation": [inject_unconfirmed_change],
    "personal_in_lab_reports": [inject_personal_in_lab_report],
    "questions_over_the_daily_cap": [inject_over_cap],
    "quoted_words_outside_the_buffer": [inject_quotation],
    "observations_after_opt_out": [inject_after_opt_out],
    "observations_of_unlinked_people": [inject_unlinked],
    "declined_asked_again_within_30_days": [inject_declined_again],
    "covered_topic_asked": [inject_covered],
    "rule_written_observations": [inject_rule_origin],
}


class Rollback(Exception):
    pass


results = []
for check, injections in INJECTIONS.items():
    for inject in injections:
        after = None
        try:
            with transaction.atomic():
                inject()
                after, _ = counts()
                raise Rollback
        except Rollback:
            pass
        moved = {k: after[k] - baseline[k] for k in after if after[k] != baseline[k]}
        results.append({
            "check": check,
            "injection": inject.__name__,
            "own_delta": after[check] - baseline[check],
            "moved": moved,
            "caught": after[check] - baseline[check] == 1,
            "cross_talk": sorted(k for k in moved if k != check),
        })

# the injections rolled back: the record is as it was
restored, _ = counts()
out["injections"] = results
out["detected"] = sum(1 for r in results if r["caught"])
out["cross_talk"] = sum(len(r["cross_talk"]) for r in results)
out["restored_equal"] = restored == baseline
out["seconds"] = round(time.time() - started, 1)
with open("/app/data/sandbox/exp018.json", "w") as handle:
    json.dump(out, handle, indent=1, default=str)
print("RESULT " + json.dumps({
    "clean": baseline, "cap_hits": len(out["clean"]["cap_hits"]),
    "detected": out["detected"], "of": len(results), "cross_talk": out["cross_talk"],
    "restored_equal": out["restored_equal"], "seconds": out["seconds"],
}))
