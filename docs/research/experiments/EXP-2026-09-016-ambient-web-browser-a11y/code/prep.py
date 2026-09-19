"""EXP-2026-09-016's data: one sandbox person's real ambient history, made
browsable. Uses the real functions wherever they exist; every planted row is
listed in the JSON this prints (saved as ``data/prep.json``).

Run inside the backend container against the copy, never the development db:

    DATABASE_URL=.../mycelium_sandbox_ambweb uv run --project web/backend \
        python web/backend/manage.py shell < .../code/prep.py
"""

import io
import json
from contextlib import redirect_stdout
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.accounts.models import LabMembership
from apps.ambient import apply, review
from apps.ambient.models import AppliedChange, PendingSuggestion, ProjectDevelopment
from apps.content.models import Notification, ReflectionProposal
from apps.research.models import Project, ProjectState

assert connection.settings_dict["NAME"] == "mycelium_sandbox_ambweb", connection.settings_dict["NAME"]

PERSON = "amb_b3_cyra"
now = timezone.now()
out = {"person": PERSON, "planted": {}, "real": {}}
cyra = User.objects.get(username=PERSON)
b2 = Project.objects.get(name="Project B2", members=cyra)
lab = b2.scope_lab
out["project_id"] = str(b2.pk)
out["lab_slug"] = lab.slug

# Planted: the world has no memberships; she is the lab's PI.
membership, _ = LabMembership.objects.get_or_create(
    user=cyra, lab=lab, defaults={"role": LabMembership.Role.OWNER, "is_lead": True}
)
out["planted"]["lab_membership"] = membership.pk

# Planted (added after run 1): the lab's profile, without which its overview
# is the setup form and the lab's "What changed" card never shows.
lab.profile.statement = "We study how markets and mechanisms behave under strategic agents."
lab.profile.areas = ["mechanism design", "algorithmic pricing"]
lab.profile.save()
out["planted"]["lab_profile"] = str(lab.profile.pk)

# Real: the nightly applier carries out her answered yeses.
out["real"]["apply_answers"] = apply.apply_answers()

# Planted: two fresh open questions, copies of two real ones she answered.
reasked = []
for source in PendingSuggestion.objects.filter(user=cyra).order_by("pk")[:2]:
    copy = PendingSuggestion.objects.create(
        user=cyra,
        kind=source.kind,
        finding=source.finding,
        concept=source.concept,
        relation=source.relation,
        project=source.project,
        topic=f"{source.topic} (again)",
        explanation=source.explanation,
        reason=source.reason,
        choices=source.choices,
        state=PendingSuggestion.State.ASKED,
        asked_at=now,
        expires_at=now + timedelta(days=14),
    )
    reasked.append(copy.pk)
out["planted"]["reasked_questions"] = reasked

# Planted: a project fact she told Mylo, recorded as the nightly run does.
told = review.record(
    cyra,
    AppliedChange.Kind.DEVELOPMENT_RECORDED,
    "the annotation budget came through",
    project=b2,
    surface="told",
    explanation="You told Mylo in the lab channel on Tuesday that the annotation budget came through.",
    visibility="lab",
)
out["planted"]["told_fact_change"] = told.pk

# Planted: a stated blocker, and a confirmed lab development that closes it.
state, _ = ProjectState.objects.get_or_create(project=b2)
state.apply({"slow": {"blockers": [{"text": "no annotation budget"}, {"text": "waiting for GPUs"}]}})
state.save()
development = ProjectDevelopment.objects.create(
    project=b2,
    speaker=cyra,
    change="blocker_closed",
    topic="annotation budget",
    text="Said in #b2-imaging that the annotation budget came through.",
    explanation="You said in the lab channel on Tuesday that the annotation budget came through, and confirmed it.",
    force="fact",
    occurred_on=timezone.localdate() - timedelta(days=2),
    status="confirmed",
    origin="conversation",
    visibility="lab",
)
out["planted"]["development"] = development.pk

# Real: tonight's delivery — DMs queued, the bell, announcements, proposals.
buffer = io.StringIO()
with redirect_stdout(buffer):
    call_command("deliver_ambient_questions", stdout=buffer)
out["real"]["deliver_ambient_questions"] = json.loads(buffer.getvalue().strip().splitlines()[-1])

out["counts"] = {
    "open_questions": PendingSuggestion.objects.filter(user=cyra, state="asked").count(),
    "changes": AppliedChange.objects.filter(user=cyra).count(),
    "profile_edits": AppliedChange.objects.filter(user=cyra, kind="profile_edit").count(),
    "notifications": Notification.objects.filter(user=cyra).count(),
    "proposals": ReflectionProposal.objects.filter(target_user=cyra, status="pending").count(),
    "heard": len((cyra.profile.interests.get("sources") or {}).get("ambient") or []),
}
print("PREP " + json.dumps(out))
