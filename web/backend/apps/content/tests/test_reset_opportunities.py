"""The opportunity wipe deletes exactly two areas, and refuses a third.

These tests exist because the command is destructive and irreversible without a
restore. The interesting assertions are the ones about what it does *not* do.
"""

from __future__ import annotations

import uuid

import pytest
from django.core.management import CommandError, call_command

from apps.content.models import ContentItem, SavedOpportunity

pytestmark = pytest.mark.django_db


def _item(kind: str, source: str = "pivot") -> ContentItem:
    return ContentItem.objects.create(
        type=kind,
        source=source,
        external_id=f"{source}-{uuid.uuid4()}",
        metadata={"title": "x", "name": "x"},
    )


def test_dry_run_deletes_nothing():
    _item(ContentItem.Type.GRANT)
    _item(ContentItem.Type.CONFERENCE)
    call_command("reset_opportunities")
    assert ContentItem.objects.count() == 2


def test_yes_deletes_grants_and_conferences():
    _item(ContentItem.Type.GRANT)
    _item(ContentItem.Type.CONFERENCE)
    call_command("reset_opportunities", "--yes")
    assert ContentItem.objects.count() == 0


def test_fellowships_and_papers_survive():
    """The whole point of the command's narrowness.

    Fellowships come from a public source that is not being replaced; papers are
    a different subsystem entirely. A wipe that took either would be silent and
    expensive.
    """
    fellowship = _item(ContentItem.Type.FELLOWSHIP, source="illinois-fellowship-finder")
    paper = _item(ContentItem.Type.PAPER, source="OpenAlex")
    _item(ContentItem.Type.GRANT)

    call_command("reset_opportunities", "--yes")

    assert set(ContentItem.objects.values_list("id", flat=True)) == {
        fellowship.id,
        paper.id,
    }


def test_explicitly_asking_for_fellowships_is_refused():
    _item(ContentItem.Type.FELLOWSHIP, source="illinois-fellowship-finder")
    with pytest.raises(CommandError, match="refusing to delete fellowships"):
        call_command("reset_opportunities", "--types", "fellowship", "--yes")
    assert ContentItem.objects.count() == 1


def test_unknown_type_is_rejected_rather_than_ignored():
    with pytest.raises(CommandError, match="unknown type"):
        call_command("reset_opportunities", "--types", "grant,widget", "--yes")


def test_source_filter_restricts_the_wipe():
    keep = _item(ContentItem.Type.GRANT, source="grants:nsf")
    _item(ContentItem.Type.GRANT, source="pivot")

    call_command("reset_opportunities", "--source", "pivot", "--yes")

    assert list(ContentItem.objects.values_list("id", flat=True)) == [keep.id]


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

    call_command("reset_opportunities", "--yes")

    save.refresh_from_db()
    assert save.content_id is None
    assert save.title == "A grant"
