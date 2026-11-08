"""The Phase 8 measures read only what the announcement path writes."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.retrieval.models import (
    Announcement,
    AnnouncementReaction,
    ContentItem,
)

from apps.accounts.models import Lab
from apps.content import announce_metrics

TODAY = timezone.localdate()


def _ann(lab, n, state=Announcement.State.POSTED, reason=""):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="open-collector",
        external_id=f"m{n}",
        metadata={"title": f"Call {n}"},
    )
    return Announcement.objects.create(
        target_lab=lab,
        content=item,
        category=item.type,
        state=state,
        skip_reason=reason,
    )


@pytest.mark.django_db
def test_rates_reasons_and_clicks_per_target() -> None:
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    ana, ben = User.objects.create_user("ana"), User.objects.create_user("ben")
    a, b = _ann(lab, 1), _ann(lab, 2)
    _ann(lab, 3, Announcement.State.SKIPPED, "The last deadline has passed")
    _ann(lab, 4, Announcement.State.SKIPPED, "Mylo: not a research call")
    kinds = AnnouncementReaction.Kind
    for user in (ana, ben):
        AnnouncementReaction.objects.create(
            announcement=a, user=user, kind=kinds.INTERESTED
        )
    AnnouncementReaction.objects.create(
        announcement=a, user=ana, kind=kinds.REMIND, reason="dm:2w"
    )
    AnnouncementReaction.objects.create(
        announcement=b, user=ben, kind=kinds.NOT_FOR_US, reason="Wrong field"
    )
    for surface in ("announced", "announced", "card"):
        AnnouncementReaction.objects.create(
            announcement=a, user=ana, kind=kinds.LINK_CLICK, reason=surface
        )

    t = announce_metrics.compute(TODAY)["targets"]["lab:reef"]

    assert t["posted"] == 2 and t["held"] == 2
    assert t["held_by_class"] == {"deadline_passed": 1, "editor": 1}
    assert t["interested_rate"] == 0.5 and t["interested_people"] == 2
    assert t["remind_rate"] == 0.5
    assert t["not_for_us"] == 1 and t["not_for_us_reasons"] == ["Wrong field"]
    assert t["link_clicks"] == 3 and t["link_click_people"] == 1
    assert t["link_clicks_by_surface"] == {"announced": 2, "card": 1}
