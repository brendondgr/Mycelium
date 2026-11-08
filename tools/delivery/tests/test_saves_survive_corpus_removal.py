"""A save outlives its item when the corpus removes it.

Both removals are retrieval's (the collector's prune and the
``reset_opportunities`` wipe), and retrieval knows nothing about saves; a save
survives because its link is ``SET_NULL`` and it keeps a snapshot.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from tools.delivery.models import SavedOpportunity
from tools.retrieval.collect.grants.record import Opportunity
from tools.retrieval.collect.ingest import prune_expired, upsert_items
from tools.retrieval.collect.mapping import map_grant
from tools.retrieval.models import ContentItem

TODAY = date(2026, 8, 16)
TODAY_ISO = "2026-08-16"


def _grant_item(sid="g1", *, source="nsf", close_date="2026-11-12", **over):
    kwargs = dict(
        source=source,
        source_record_id=sid,
        title="Test Research Award",
        funder="Test Funder",
        description="A grant funding foundational research on distributed systems.",
        close_date=close_date,
        currency="USD",
    )
    kwargs.update(over)
    return map_grant(Opportunity(**kwargs), today=TODAY)

pytestmark = pytest.mark.django_db


def _item(kind: str, source: str = "pivot") -> ContentItem:
    return ContentItem.objects.create(
        type=kind,
        source=source,
        external_id=f"{source}-{uuid.uuid4()}",
        metadata={"title": "x", "name": "x"},
    )


def test_a_save_survives_its_item_via_the_snapshot(django_user_model):
    """``SavedOpportunity.content`` is SET_NULL with a snapshot taken at save time.

    The save outlives the wipe. It does not re-attach to whatever replaces the
    item — that pairing is genuinely lost, which is why the command reports the
    count before deleting.
    """
    user = django_user_model.objects.create_user(username="u", password="x")
    item = _item(ContentItem.Type.GRANT)
    save = SavedOpportunity.objects.create(
        user=user,
        content=item,
        area=SavedOpportunity.Area.GRANT,
        title="A grant",
    )

    call_command("reset_opportunities")  # the dry run counts the save
    call_command("reset_opportunities", "--yes")

    save.refresh_from_db()
    assert save.content_id is None
    assert save.title == "A grant"


def test_prune_preserves_saved_deadline_via_set_null():
    user = User.objects.create_user(username="researcher", password="pw")
    upsert_items(
        [_grant_item("expiring", close_date="2025-01-01")], today=TODAY_ISO
    )
    item = ContentItem.objects.get(external_id="src:nsf:expiring")
    saved = SavedOpportunity.objects.create(
        user=user,
        content=item,
        area=SavedOpportunity.Area.GRANT,
        title="Test Research Award",
        deadline_date="2025-01-01",
        snapshot={"funder": "Test Funder"},
    )

    assert prune_expired(today=TODAY_ISO) == 1

    saved.refresh_from_db()
    assert saved.content_id is None  # SET_NULL, not deleted
    assert saved.snapshot["funder"] == "Test Funder"
