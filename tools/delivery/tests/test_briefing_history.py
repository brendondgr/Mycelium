"""Dated briefing history: the day key, retention, and the Reports-page endpoints.

``DailyBriefing`` used to be one overwritten row per target. It is now one row per
target per ``generated_on``, bounded by ``prune_briefings``. These tests pin the
three things that change can quietly break: a same-day rerun must still replace
rather than accumulate, every "current briefing" reader must return the newest
day rather than an arbitrary one, and the new read endpoints must stay
object-scoped and body-free.
"""

from datetime import timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery.models import DailyBriefing

TODAY = timezone.localdate()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _briefing(target, on, **fields) -> DailyBriefing:
    fields.setdefault("body", f"Report for {on}.")
    fields.setdefault("counts", {"papers": 1})
    return DailyBriefing.objects.create(generated_on=on, **target, **fields)


# --------------------------------------------------------------------------- #
# The migration's backfill
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
def test_migration_backfills_generated_on_from_the_write_timestamp() -> None:
    """A pre-history row keeps its day: the local date it was last written.

    Runs the real migration backwards and forwards, so this covers the RunPython
    body *and* that 0018 reverses cleanly (the executor could not step back to
    0017 otherwise).
    """
    executor = MigrationExecutor(connection)
    before = ("content", "0017_remindersubscription_snoozed_until")
    after = ("content", "0018_dailybriefing_history")

    executor.migrate([before])
    old_apps = executor.loader.project_state([before]).apps
    OldUser = old_apps.get_model("auth", "User")
    OldBriefing = old_apps.get_model("content", "DailyBriefing")
    user = OldUser.objects.create(username="legacy")
    OldBriefing.objects.create(user_id=user.pk, body="Yesterday's news.")
    written_at = OldBriefing.objects.get(user_id=user.pk).generated_at

    executor.loader.build_graph()
    executor.migrate([after])
    new_apps = executor.loader.project_state([after]).apps
    NewBriefing = new_apps.get_model("content", "DailyBriefing")

    row = NewBriefing.objects.get(user_id=user.pk)
    assert row.generated_on == timezone.localtime(written_at).date()


# --------------------------------------------------------------------------- #
# The day key
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_second_day_adds_a_row_rather_than_overwriting() -> None:
    from tools.delivery.briefing import generate_briefing_for_user

    user = User.objects.create_user("historian", password="x")

    generate_briefing_for_user(user, complete=lambda s, u: "")
    # Age the first run so the next one lands on a different day, the way a real
    # overnight gap would.
    DailyBriefing.objects.filter(user=user).update(
        generated_on=TODAY - timedelta(days=1)
    )
    generate_briefing_for_user(user, complete=lambda s, u: "")

    days = list(
        DailyBriefing.objects.filter(user=user)
        .order_by("generated_on")
        .values_list("generated_on", flat=True)
    )
    assert days == [TODAY - timedelta(days=1), TODAY]


@pytest.mark.django_db
def test_a_same_day_rerun_still_replaces_that_day() -> None:
    from tools.delivery.briefing import generate_briefing_for_user

    user = User.objects.create_user("rerun", password="x")

    generate_briefing_for_user(user, complete=lambda s, u: "first pass")
    generate_briefing_for_user(user, complete=lambda s, u: "second pass")

    assert DailyBriefing.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_one_briefing_per_target_per_day() -> None:
    user = User.objects.create_user("dupe", password="x")
    _briefing({"user": user}, TODAY)

    with pytest.raises(IntegrityError), transaction.atomic():
        _briefing({"user": user}, TODAY)


@pytest.mark.django_db
def test_the_day_key_does_not_leak_across_the_null_target_side() -> None:
    """A user's day and a lab's day are separate rows, not a collision.

    The constraints are conditioned on the populated side precisely so the NULL
    column cannot make one target's uniqueness apply to the other's.
    """
    user = User.objects.create_user("both", password="x")
    lab = Lab.objects.create(name="Neuro", slug="neuro")

    _briefing({"user": user}, TODAY)
    _briefing({"lab": lab}, TODAY)

    assert DailyBriefing.objects.filter(generated_on=TODAY).count() == 2

    # Two labs may each hold the same day, too.
    other = Lab.objects.create(name="Optics", slug="optics")
    _briefing({"lab": other}, TODAY)
    lab_days = DailyBriefing.objects.filter(generated_on=TODAY, lab__isnull=False)
    assert lab_days.count() == 2


# --------------------------------------------------------------------------- #
# "The current briefing" once history exists
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_latest_for_returns_the_newest_day() -> None:
    user = User.objects.create_user("latest", password="x")
    lab = Lab.objects.create(name="Neuro", slug="neuro")
    for offset in (5, 0, 2):
        _briefing({"user": user}, TODAY - timedelta(days=offset))
        _briefing({"lab": lab}, TODAY - timedelta(days=offset))

    assert DailyBriefing.latest_for(user=user).generated_on == TODAY
    assert DailyBriefing.latest_for(lab=lab).generated_on == TODAY
    assert DailyBriefing.latest_for(user=User.objects.create_user("none")) is None


@pytest.mark.django_db
def test_the_daily_endpoint_serves_the_newest_day(client: APIClient) -> None:
    user = User.objects.create_user("reader", password="x")
    _briefing({"user": user}, TODAY - timedelta(days=3), body="Stale.")
    _briefing({"user": user}, TODAY, body="Fresh.")

    client.force_authenticate(user)
    resp = client.get("/api/daily-briefing/")

    assert resp.status_code == 200
    assert resp.data["generated_on"] == TODAY.isoformat()
    assert resp.data["briefing"]["body"] == "Fresh."


# --------------------------------------------------------------------------- #
# Retention
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_prune_deletes_strictly_older_and_keeps_the_boundary_day() -> None:
    user = User.objects.create_user("aged", password="x")
    for offset in (0, 1, 3, 4, 10):
        _briefing({"user": user}, TODAY - timedelta(days=offset))

    call_command("prune_briefings", "--days", "3")

    kept = set(
        DailyBriefing.objects.filter(user=user).values_list("generated_on", flat=True)
    )
    assert kept == {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=3)}


@pytest.mark.django_db
def test_prune_dry_run_deletes_nothing() -> None:
    user = User.objects.create_user("dry", password="x")
    _briefing({"user": user}, TODAY - timedelta(days=400))

    call_command("prune_briefings", "--dry-run")

    assert DailyBriefing.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_prune_uses_the_configured_window(settings) -> None:
    settings.BRIEFING_RETENTION_DAYS = 90
    user = User.objects.create_user("windowed", password="x")
    _briefing({"user": user}, TODAY - timedelta(days=90))
    _briefing({"user": user}, TODAY - timedelta(days=91))

    call_command("prune_briefings")

    assert list(
        DailyBriefing.objects.filter(user=user).values_list("generated_on", flat=True)
    ) == [TODAY - timedelta(days=90)]


# --------------------------------------------------------------------------- #
# The history endpoints
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_history_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/briefings/").status_code in (401, 403)


@pytest.mark.django_db
def test_history_lists_own_days_newest_first_without_bodies(client: APIClient) -> None:
    user = User.objects.create_user("owner", password="x")
    stranger = User.objects.create_user("stranger", password="x")
    _briefing({"user": user}, TODAY - timedelta(days=1))
    _briefing({"user": user}, TODAY, counts={"papers": 4})
    _briefing({"user": stranger}, TODAY)

    client.force_authenticate(user)
    resp = client.get("/api/briefings/")

    assert resp.status_code == 200
    assert [row["generated_on"] for row in resp.data] == [
        TODAY.isoformat(),
        (TODAY - timedelta(days=1)).isoformat(),
    ]
    assert resp.data[0]["counts"] == {"papers": 4}
    assert all("body" not in row for row in resp.data)


@pytest.mark.django_db
def test_a_day_serves_the_full_envelope_and_404s_otherwise(client: APIClient) -> None:
    user = User.objects.create_user("dated", password="x")
    _briefing({"user": user}, TODAY, body="That day's report.")

    client.force_authenticate(user)

    resp = client.get(f"/api/briefings/{TODAY.isoformat()}/")
    assert resp.status_code == 200
    assert resp.data["briefing"]["body"] == "That day's report."
    assert resp.data["generated_on"] == TODAY.isoformat()

    missing = (TODAY - timedelta(days=1)).isoformat()
    assert client.get(f"/api/briefings/{missing}/").status_code == 404
    # A malformed date does not resolve at all rather than reaching the ORM.
    assert client.get("/api/briefings/not-a-date/").status_code == 404


@pytest.mark.django_db
def test_a_day_belonging_to_someone_else_is_not_readable(client: APIClient) -> None:
    owner = User.objects.create_user("mine", password="x")
    stranger = User.objects.create_user("theirs", password="x")
    _briefing({"user": owner}, TODAY, body="Private.")

    client.force_authenticate(stranger)
    resp = client.get(f"/api/briefings/{TODAY.isoformat()}/")

    assert resp.status_code == 404


@pytest.mark.django_db
def test_lab_history_is_gated_on_lab_access(client: APIClient) -> None:
    member = User.objects.create_user("member", password="x")
    outsider = User.objects.create_user("outsider", password="x")
    lab = Lab.objects.create(name="Neuro", slug="neuro")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    _briefing({"lab": lab}, TODAY, body="Lab report.")

    client.force_authenticate(outsider)
    assert client.get("/api/labs/neuro/briefings/").status_code == 403
    assert (
        client.get(f"/api/labs/neuro/briefings/{TODAY.isoformat()}/").status_code == 403
    )

    client.force_authenticate(member)
    index = client.get("/api/labs/neuro/briefings/")
    assert index.status_code == 200
    assert [row["generated_on"] for row in index.data] == [TODAY.isoformat()]
    assert all("body" not in row for row in index.data)

    detail = client.get(f"/api/labs/neuro/briefings/{TODAY.isoformat()}/")
    assert detail.status_code == 200
    assert detail.data["briefing"]["body"] == "Lab report."
