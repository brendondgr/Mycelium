"""Telling someone, once, that Mylo could not reach them on Discord.

A dead letter is the one outcome the person on the other end can actually act on —
their DMs are closed, the lab's channel was deleted, the bot lost permission to post.
Silently retiring it after five attempts would repeat the failure the outbox was built
to fix, just later in the pipeline.

Three rules shape this module:

* **Once, not once per attempt.** The notice is keyed on the outbox row, and an outbox
  row is unique per logical message, so five attempts produce one notice and a re-queue
  of the same message produces none.
* **In the Mycelium app, and nowhere else.** Not a Discord message: if Discord is the
  thing that is broken, a Discord message is the one channel guaranteed not to arrive.
  Not the shared lab channel either — that is noise for people who cannot fix it.
* **To whoever can act.** A failed DM concerns its recipient. A failed channel post
  concerns the lab's managers, since only they can rebind a channel or fix permissions.

Reached from ``integrations.services.outbox`` by a lazy import, so the queue still
touches no ORM model of its own and the two apps do not form an import cycle.
"""

from __future__ import annotations

from apps.accounts.models import LabMembership

from tools.delivery.models import Notification

#: What to tell the person, per classified failure reason. Written to be actionable:
#: each one names what happened and what would fix it, in Mylo's register.
_COPY = {
    "dm_blocked": (
        "Mylo couldn't send you a Discord message",
        "Your direct messages are closed, or Mylo is blocked. Turn on "
        '"Allow direct messages from server members" in Discord, then re-run the '
        "reachability test on your profile.",
    ),
    "no_permission": (
        "Mylo couldn't post in your lab's Discord channel",
        "A permission setting on that channel stops Mylo posting there. Restore its "
        "View Channel, Send Messages and Embed Links permissions, or choose another "
        "channel with /setup.",
    ),
    "no_access": (
        "Mylo couldn't reach your lab's Discord channel",
        "Mylo can no longer see that channel — it may have been made private, or Mylo "
        "may have been removed from the server. Re-add Mylo, or pick another channel "
        "with /setup.",
    ),
    "channel_gone": (
        "Your lab's Discord channel no longer exists",
        "The channel Mylo posts to has been deleted. Choose a new one with /setup.",
    ),
    "guild_gone": (
        "Mylo is no longer in your lab's Discord server",
        "Nothing has been removed from Mycelium. Re-add Mylo to the server to start "
        "receiving updates again.",
    ),
    "not_configured": (
        "Mylo's Discord connection isn't set up",
        "This is a Mycelium-side configuration gap, not a problem with your account. "
        "An administrator needs to finish connecting Mylo to Discord.",
    ),
}
_FALLBACK = (
    "Mylo couldn't deliver a Discord message",
    "Mylo tried several times and couldn't get through. Check your Discord "
    "connection from your profile; nothing in Mycelium has been lost.",
)


def notify_delivery_failed(
    *,
    outbox_id,
    reason: str = "",
    target_type: str = "",
    recipient_user=None,
    lab=None,
    kind: str = "",
) -> int:
    """Write the one in-app notice for a dead-lettered message. Never raises.

    Returns how many notifications were created (0 if there is nobody to tell, or if
    this message has already been reported).
    """
    title, body = _COPY.get(str(reason), _FALLBACK)
    recipients = _recipients(target_type=target_type, user=recipient_user, lab=lab)
    created = 0
    for user in recipients:
        # One row per (message, person): the outbox id is already unique per logical
        # message, so retries cannot multiply this and neither can a re-queue.
        _, made = Notification.objects.get_or_create(
            dedupe_key=f"discord_fail:{outbox_id}:{user.id}",
            defaults={
                "user": user,
                "kind": Notification.Kind.DELIVERY_FAILED,
                "title": title,
                "body": body,
            },
        )
        created += int(made)
    return created


def _recipients(*, target_type: str, user, lab) -> list:
    """Whoever can actually do something about this failure."""
    if target_type == "dm":
        return [user] if user is not None else []
    if lab is None:
        return []
    # Only owners and admins can rebind a channel or fix permissions — the same set
    # `accounts.permissions.user_can_manage_lab` recognises, resolved in bulk.
    from apps.accounts.permissions import lab_manager_q

    memberships = (
        LabMembership.objects.filter(lab=lab)
        .filter(lab_manager_q())
        .select_related("user")
    )
    return [m.user for m in memberships]
