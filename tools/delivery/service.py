"""The delivery write door: what other code may ask delivery to do.

Fan a shared item out to the project's other members, create or update a
deadline reminder, and switch a target's announcements on. Delivery depends on
retrieval and recommendation and nothing depends on it, so it subscribes to
their events and extension points rather than being called by them.
"""

from tools.delivery.fanout import fan_out_relevance, trigger_fanout
from tools.delivery.reminders import (
    create_or_update_subscription,
    create_subscription,
    set_state,
    update_subscription,
)
from tools.delivery.tasks import enqueue_activation

__all__ = [
    "create_or_update_subscription",
    "create_subscription",
    "enqueue_activation",
    "fan_out_relevance",
    "set_state",
    "trigger_fanout",
    "update_subscription",
]
