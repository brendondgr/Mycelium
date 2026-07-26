"""The outbox's storage contract: dedupe, claim-once, and terminal settlement.

These are the properties the rest of Phase A assumes. The claim test is the load-
bearing one: two drains must never both take the same row, because that is precisely
how a queue turns one reminder into two Discord messages.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone

from apps.integrations.models import DiscordOutboxMessage
from apps.integrations.services import resolve

_Status = DiscordOutboxMessage.Status


@pytest.fixture
def user(db):
    return User.objects.create_user("outbox-model-user")


@pytest.fixture
def postgres(db):
    if connection.vendor != "postgresql":
        pytest.skip("row-level claim locking requires PostgreSQL")


def _enqueue(user, key="k1", **kwargs):
    row, created = resolve.enqueue_outbox(
        dedupe_key=key,
        kind="reminder",
        target_type=resolve.OUTBOX_DM,
        recipient_user=user,
        content="hello",
        **kwargs,
    )
    return row, created


@pytest.mark.django_db
def test_enqueue_is_idempotent_on_dedupe_key(user) -> None:
    """Re-running a producer must not queue a second message."""
    first, created_first = _enqueue(user)
    second, created_second = _enqueue(user)

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert DiscordOutboxMessage.objects.count() == 1


@pytest.mark.django_db
def test_a_queued_message_is_due_immediately(user) -> None:
    row, _ = _enqueue(user)
    assert row.status == _Status.PENDING
    assert row.attempts == 0
    claimed = resolve.claim_outbox_batch()
    assert [c.pk for c in claimed] == [row.pk]


@pytest.mark.django_db
def test_claiming_consumes_an_attempt_before_the_send(user) -> None:
    """The attempt is spent at claim time, not on completion.

    A process that dies mid-send must leave a row that visibly used an attempt,
    rather than one that looks untouched and gets re-sent from scratch.
    """
    row, _ = _enqueue(user)
    resolve.claim_outbox_batch()

    row.refresh_from_db()
    assert row.status == _Status.SENDING
    assert row.attempts == 1


@pytest.mark.django_db
def test_a_message_scheduled_for_later_is_not_claimed(user) -> None:
    row, _ = _enqueue(user)
    resolve.claim_outbox_batch()
    resolve.mark_outbox_retry(
        row, next_attempt_at=timezone.now() + timedelta(minutes=5), reason="upstream"
    )

    assert resolve.claim_outbox_batch() == []

    later = timezone.now() + timedelta(minutes=6)
    assert [c.pk for c in resolve.claim_outbox_batch(now=later)] == [row.pk]


@pytest.mark.django_db
def test_retry_returns_the_row_to_pending_with_its_reason(user) -> None:
    row, _ = _enqueue(user)
    resolve.claim_outbox_batch()
    when = timezone.now() + timedelta(minutes=5)
    resolve.mark_outbox_retry(
        row, next_attempt_at=when, error_code=None, reason="upstream"
    )

    row.refresh_from_db()
    assert row.status == _Status.PENDING
    assert row.last_error_reason == "upstream"
    assert row.attempts == 1  # not re-incremented by settling


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("settle", "expected"),
    [
        (resolve.mark_outbox_sent, _Status.SENT),
        (resolve.mark_outbox_permanent, _Status.FAILED),
        (resolve.mark_outbox_dead, _Status.DEAD),
    ],
)
def test_terminal_states_are_never_claimed_again(user, settle, expected) -> None:
    row, _ = _enqueue(user)
    resolve.claim_outbox_batch()
    settle(row)

    row.refresh_from_db()
    assert row.status == expected
    assert row.settled_at is not None
    assert resolve.claim_outbox_batch(now=timezone.now() + timedelta(days=1)) == []


@pytest.mark.django_db
def test_sent_records_the_discord_message_id_and_clears_the_last_error(user) -> None:
    row, _ = _enqueue(user)
    resolve.claim_outbox_batch()
    resolve.mark_outbox_retry(row, next_attempt_at=timezone.now(), reason="upstream")
    resolve.mark_outbox_sent(row, discord_message_id="msg-1")

    row.refresh_from_db()
    assert row.discord_message_id == "msg-1"
    assert row.last_error_reason == ""  # the earlier blip is not left on the record
    assert row.sent_at is not None


@pytest.mark.django_db
def test_nonce_fits_discords_twenty_five_character_limit(user) -> None:
    """An integer PK is the whole reason the model does not use a UUID."""
    row, _ = _enqueue(user)
    assert len(row.nonce) <= 25
    assert row.nonce == str(row.pk)


@pytest.mark.django_db
def test_counters_report_what_operations_needs(user) -> None:
    sent, _ = _enqueue(user, key="sent")
    dead, _ = _enqueue(user, key="dead")
    _enqueue(user, key="waiting")

    resolve.claim_outbox_batch()
    resolve.mark_outbox_sent(sent)
    resolve.mark_outbox_dead(dead, reason="dm_blocked")

    counters = resolve.outbox_counters()
    assert counters["queued"] == 3
    assert counters["delivered"] == 1
    assert counters["dead"] == 1
    assert counters["pending"] == 1


@pytest.mark.django_db
def test_purge_keeps_the_evidence_of_failures(user, tmp_path) -> None:
    """Only successes are purged. A dead letter is the record of what went wrong."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-")

    sent, _ = _enqueue(user, key="sent", attachment_path=str(pdf))
    dead, _ = _enqueue(user, key="dead")
    resolve.claim_outbox_batch()
    resolve.mark_outbox_sent(sent, now=timezone.now() - timedelta(days=40))
    resolve.mark_outbox_dead(dead, now=timezone.now() - timedelta(days=40))

    paths = resolve.purge_outbox(before=timezone.now() - timedelta(days=30))

    assert paths == [str(pdf)]  # caller unlinks; resolve owns the DB, not the disk
    assert not DiscordOutboxMessage.objects.filter(pk=sent.pk).exists()
    assert DiscordOutboxMessage.objects.filter(pk=dead.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_two_drains_never_claim_the_same_row(postgres, user) -> None:
    """The guarantee that stops a queue duplicating messages under concurrency."""
    import threading

    for i in range(8):
        _enqueue(user, key=f"concurrent-{i}")

    claimed: list[list[int]] = []
    barrier = threading.Barrier(2)

    def drain_once() -> None:
        barrier.wait()
        rows = resolve.claim_outbox_batch(limit=8)
        claimed.append([r.pk for r in rows])
        connection.close()

    threads = [threading.Thread(target=drain_once) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    first, second = claimed
    assert not (set(first) & set(second)), "a row was claimed by both drains"
    assert len(first) + len(second) == 8
