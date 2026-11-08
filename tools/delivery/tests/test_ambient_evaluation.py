"""Ambient Plan 10's command: the measures and harm checks over the stored
record, with the lab reports read here (the ambient app may not)."""

import json
from io import StringIO

from apps.accounts.models import Lab
from apps.ambient.models import AppliedChange
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from tools.delivery.models import DailyBriefing


def test_the_command_reads_the_lab_reports_and_catches_a_leak(db):
    ada = User.objects.create_user("ada", "ada@example.org", "pw")
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    AppliedChange.objects.create(
        user=ada, kind="profile_edit", topic="clinical research", field="x"
    )
    DailyBriefing.objects.create(
        lab=lab,
        generated_on=timezone.localdate(),
        kind=DailyBriefing.Kind.WEEKLY,
        body="## What changed\n### Projects\n- **clinical research** — added. [O1]",
    )
    out, err = StringIO(), StringIO()
    call_command("evaluate_ambient", stdout=out, stderr=err)
    result = json.loads(out.getvalue())
    assert result["harm_checks"]["personal_in_lab_reports"]["count"] == 1
    assert "harm-check violation" in err.getvalue()


def test_a_clean_record_reports_zero(db):
    out = StringIO()
    call_command("evaluate_ambient", stdout=out)
    result = json.loads(out.getvalue())
    assert result["harm_checks"]["_total"] == 0
    assert result["validation_precision"]["precision"] is None
