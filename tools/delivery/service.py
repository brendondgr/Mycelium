"""The delivery write door: what other code may ask delivery to do.

Write a person's or a lab's daily report now, fan a shared item out to the
project's other members, create or update a deadline reminder, and switch a
target's announcements on, and save, share or clear items for fixtures such
as the public demo's lab (``save_item``, ``share_to_project``,
``clear_activity``). Delivery depends on
retrieval and recommendation and nothing depends on it, so it subscribes to
their events and extension points rather than being called by them.
"""

from tools.delivery.briefing import (
    generate_briefing_for_lab,
    generate_briefing_for_user,
)
from tools.delivery.fanout import fan_out_relevance, trigger_fanout
from tools.delivery.reminders import (
    create_or_update_subscription,
    create_subscription,
    set_state,
    update_subscription,
)
from tools.delivery.tasks import enqueue_activation


def save_item(user, content, *, note: str = "", target_lab=None):
    """Save ``content`` for ``user`` (or to ``target_lab``), as the bookmark
    button does: a snapshot of the item, no notification."""
    from tools.delivery.views import _save_from_item

    return _save_from_item(user, content, note=note, target_lab=target_lab)


def share_to_project(project, content, sharer, *, note: str = ""):
    """Share ``content`` into ``project`` as ``sharer`` and fan it out to the
    other members whose profile it fits (their "Suggested for you")."""
    from tools.delivery.collaboration import share_to_project as share

    shared = share(project, content, sharer, note=note)
    fan_out_relevance(shared, embed_missing=False)
    return shared


def clear_activity(users=(), labs=(), projects=()) -> int:
    """Delete these people's and labs' saves and reminders, the suggestions
    made to these people, and the shares into these projects. Used to rebuild a
    fixture world's activity from its current feed; returns rows deleted."""
    from django.db.models import Q

    from tools.delivery.models import (
        MemberSuggestion,
        ProjectShare,
        ReminderSubscription,
        SavedOpportunity,
    )

    users, labs, projects = list(users), list(labs), list(projects)
    deleted = 0
    for model, where in (
        (MemberSuggestion, Q(user__in=users)),
        (ProjectShare, Q(project__in=projects)),
        (ReminderSubscription, Q(target_user__in=users) | Q(target_lab__in=labs)),
        (SavedOpportunity, Q(user__in=users) | Q(target_lab__in=labs)),
    ):
        deleted += model.objects.filter(where).delete()[0]
    return deleted


__all__ = [
    "clear_activity",
    "create_or_update_subscription",
    "create_subscription",
    "enqueue_activation",
    "fan_out_relevance",
    "generate_briefing_for_lab",
    "generate_briefing_for_user",
    "save_item",
    "set_state",
    "share_to_project",
    "trigger_fanout",
    "update_subscription",
]
