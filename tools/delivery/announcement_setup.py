"""The announcements step of `/setup` (plan D12, D13).

Configures **one binding** — the lab or department being set up in this server —
so running it for a lab never touches the department's channels, and the reverse.

* **Create them for me** makes a category with three forums for a lab (``#grants``,
  ``#fellowships``, ``#conferences``) or one ``#dept-opportunities`` forum for a
  department, each sorted by recent activity so an updated
  thread rises, and carrying Mylo's tags. Nothing is created unless a manager asks.
* **Use channels I already have** binds an existing forum per kind, after proving
  Mylo can start a thread in it.
* **Who can start posts** — everyone (the default), managers only, or chosen roles.
  Anyone can always reply in a thread: only *starting* a post is restricted.
* **Switching on** records ``activated_at`` and runs the activation seed for that
  target straight away (six *Already open* threads and the closing-soon list).

Every entry point takes an already-authorized binding: the caller ran the gate.
"""

from __future__ import annotations

from apps.integrations.services import discord_api, resolve
from django.utils import timezone

from tools.delivery.discord_announcements import (
    DEPT_FORUM_TAGS,
    FORUM_TAGS,
    KINDS,
    PURPOSE_KIND,
)
from tools.delivery.models import AnnouncementSettings

PURPOSES = ("grants", "fellowships", "conferences")
FORUM = 15
# Discord permission bits.
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11  # in a forum: start a post
EMBED_LINKS = 1 << 14
MANAGE_THREADS = 1 << 34
SEND_IN_THREADS = 1 << 38
_TOPICS = {
    "grants": "One thread per grant that newly fits {name}. A changed call is updated "
    "in its own thread and moves to the top. Anyone can reply.",
    "fellowships": "Fellowships that fit people in {name}. Eligibility goes to each "
    "person privately, never here. Anyone can reply.",
    "conferences": "Venues that fit {name}, announced once their submission dates are "
    "published. Anyone can reply.",
}
DEPT_FORUM = "dept-opportunities"
_DEPT_TOPIC = (
    "Calls only {name} as a department can take on: limited submissions, "
    "department applicants, training programmes and centres. Each names the labs "
    "that could lead. Anyone can reply."
)


def settings_for_binding(binding) -> AnnouncementSettings:
    if binding.lab_id:
        row, _ = AnnouncementSettings.objects.get_or_create(target_lab=binding.lab)
    else:
        row, _ = AnnouncementSettings.objects.get_or_create(
            target_department=binding.department
        )
    return row


def state(binding) -> dict:
    """What the announcements menu shows for one binding."""
    routes = resolve.routes_for_binding(binding)
    row = settings_for_binding(binding)
    policy = next(
        (routes[p].poster_policy for p in PURPOSES if p in routes), "everyone"
    )
    return {
        "enabled": row.enabled,
        "activated_at": row.activated_at.isoformat() if row.activated_at else "",
        "routes": {p: routes[p].channel_id for p in PURPOSES if p in routes},
        "poster_policy": policy,
    }


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #
def create_forums(binding, *, actor=None) -> tuple[bool, str]:
    """Make the category and its forums for this binding — three for a lab, one
    ``#dept-opportunities`` for a department; ``(ok, message)``."""
    name = resolve.binding_name(binding)
    guild_id = binding.guild.guild_id
    shared = len(resolve.bindings_for_guild(guild_id)) > 1
    category_name = "Mylo Opportunities" + (f" · {name}" if shared else "")
    try:
        cat = discord_api.create_guild_channel(
            guild_id, {"name": category_name[:100], "type": 4}
        )
        if cat.status not in (200, 201):
            return False, _refusal(cat)
        made = []
        # A department gets one forum for every kind; a lab one per kind.
        forums = (
            [(DEPT_FORUM, PURPOSES, _DEPT_TOPIC, DEPT_FORUM_TAGS)]
            if binding.department_id
            else [(p, (p,), _TOPICS[p], FORUM_TAGS[p]) for p in PURPOSES]
        )
        for forum_name, purposes, topic, forum_tags in forums:
            resp = discord_api.create_guild_channel(
                guild_id,
                {
                    "name": forum_name,
                    "type": FORUM,
                    "parent_id": cat.json["id"],
                    "topic": topic.format(name=name)[:1024],
                    "default_forum_layout": 1,
                    "default_sort_order": 0,  # recent activity: updates rise
                    "available_tags": [
                        {"name": t, "emoji_name": e} for t, e in forum_tags
                    ],
                },
            )
            if resp.status not in (200, 201):
                return False, _refusal(resp)
            tags = {t["name"]: t["id"] for t in resp.json.get("available_tags") or []}
            for purpose in purposes:
                resolve.set_route(
                    binding,
                    purpose,
                    resp.json["id"],
                    verified_at=timezone.now(),
                    channel_type=FORUM,
                    forum_tag_ids=tags,
                    created_by_mylo=True,
                    channel_name=forum_name,
                    actor=actor,
                )
            made.append(f"<#{resp.json['id']}>")
    except discord_api.DiscordHTTPError:
        return False, "I couldn't reach Discord just now. Try again in a moment."
    return True, f"Made **{category_name}** with {', '.join(made)}."


def _refusal(resp) -> str:
    if resp.status == 403:
        return (
            "I need the **Manage Channels** permission to create forums. Grant it, or "
            "pick forums you already have instead."
        )
    return f"Discord refused that (HTTP {resp.status}). Nothing else was changed."


def use_forum(
    binding, purpose: str, channel_id: str, *, actor=None
) -> tuple[bool, str]:
    """Bind an existing forum for ``purpose`` after proving Mylo can post in it."""
    if purpose not in PURPOSES:
        return False, "Unknown channel kind."
    try:
        info = discord_api.get_channel(channel_id)
        if info.status != 200:
            return False, f"I can't see <#{channel_id}>. Check that I can view it."
        if info.json.get("type") != FORUM:
            return False, f"<#{channel_id}> isn't a forum channel. Pick a forum."
        probe = discord_api.create_forum_thread(
            channel_id,
            name="Mylo is set up here",
            embed={
                "title": "Mylo is set up here ✅",
                "description": "This forum will receive "
                f"{resolve.binding_name(binding)}'s "
                f"{KINDS[PURPOSE_KIND[purpose]][0].lower()} announcements.",
                "color": 0x5E7A3E,
            },
        )
        if probe.status not in (200, 201):
            return False, (
                f"I can't start a post in <#{channel_id}>: a permission denies me "
                "Send Messages there. Fix it, or pick another forum."
            )
        # The proof has done its job; it would only clutter the forum.
        discord_api.delete_channel(str(probe.json.get("id")))
    except discord_api.DiscordHTTPError:
        return False, "I couldn't reach Discord just now. Try again in a moment."
    route = resolve.set_route(
        binding,
        purpose,
        channel_id,
        verified_at=timezone.now(),
        channel_type=FORUM,
        created_by_mylo=False,
        channel_name=str(info.json.get("name") or ""),
        actor=actor,
    )
    from tools.delivery.discord_announcements import ensure_forum_tags

    ensure_forum_tags(route)
    return True, f"{purpose.title()} → <#{channel_id}>."


def clear_forum(binding, purpose: str, *, actor=None) -> str:
    resolve.clear_route(binding, purpose, actor=actor)
    return f"{purpose.title()} announcements turned off here."


# --------------------------------------------------------------------------- #
# Who can start posts
# --------------------------------------------------------------------------- #
def set_poster_policy(
    binding, policy: str, *, role_ids=(), manager_discord_ids=(), bot_user_id: str = ""
) -> tuple[bool, str]:
    """Apply ``policy`` to each of this binding's forums. Replies stay open."""
    if policy not in ("everyone", "managers", "roles"):
        return False, "Unknown choice."
    everyone_role = binding.guild.guild_id  # @everyone's role id is the guild id
    routes = [
        r for p, r in resolve.routes_for_binding(binding).items() if p in PURPOSES
    ]
    if not routes:
        return False, "Choose this binding's forums first."
    try:
        for route in routes:
            if policy == "everyone":
                ok = discord_api.set_permission_overwrite(
                    route.channel_id,
                    everyone_role,
                    kind=0,
                    allow=SEND_IN_THREADS,
                    deny=0,
                )
            else:
                ok = discord_api.set_permission_overwrite(
                    route.channel_id,
                    everyone_role,
                    kind=0,
                    allow=SEND_IN_THREADS,
                    deny=SEND_MESSAGES,
                )
                if bot_user_id:
                    discord_api.set_permission_overwrite(
                        route.channel_id,
                        bot_user_id,
                        kind=1,
                        allow=VIEW_CHANNEL
                        | SEND_MESSAGES
                        | EMBED_LINKS
                        | MANAGE_THREADS
                        | SEND_IN_THREADS,
                        deny=0,
                    )
                allowed = (
                    list(role_ids) if policy == "roles" else list(manager_discord_ids)
                )
                for target_id in allowed:
                    discord_api.set_permission_overwrite(
                        route.channel_id,
                        str(target_id),
                        kind=0 if policy == "roles" else 1,
                        allow=SEND_MESSAGES,
                        deny=0,
                    )
            if ok.status not in (200, 204):
                return False, (
                    "I need the **Manage Roles** permission on those forums to change "
                    "who can start posts."
                )
            resolve.set_route_poster_policy(
                binding, route.purpose, policy=policy, role_ids=role_ids
            )
    except discord_api.DiscordHTTPError:
        return False, "I couldn't reach Discord just now. Try again in a moment."
    said = {
        "everyone": "Everyone can start posts.",
        "managers": "Only managers can start posts.",
        "roles": "Only the chosen roles can start posts.",
    }[policy]
    return True, f"{said} Anyone can still reply in a thread."


def manager_discord_ids(binding) -> list[str]:
    """Linked Discord ids of this binding's own managers."""
    from apps.accounts.models import DeptMembership, LabMembership
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if binding.lab_id:
        from apps.accounts.permissions import lab_manager_q

        managers = LabMembership.objects.filter(lab=binding.lab).filter(
            lab_manager_q()
        )
        users = User.objects.filter(pk__in=managers.values("user_id"))
    else:
        roles = (DeptMembership.Role.OWNER, DeptMembership.Role.ADMIN)
        users = User.objects.filter(
            dept_memberships__department=binding.department,
            dept_memberships__role__in=roles,
        )
    ids = resolve.active_discord_ids_for_users(list(users))
    return list(ids.values())


# --------------------------------------------------------------------------- #
# Switching on and off
# --------------------------------------------------------------------------- #
def switch(binding, *, on: bool, actor=None) -> tuple[AnnouncementSettings, bool]:
    """``(settings, first_activation)``. Turning on for the first time stamps
    ``activated_at``; the caller then runs :func:`activate_now`."""
    row = settings_for_binding(binding)
    first = on and row.activated_at is None
    row.enabled = on
    if first:
        row.activated_at = timezone.now()
    row.updated_by = actor
    row.save(update_fields=["enabled", "activated_at", "updated_by", "updated_at"])
    from apps.integrations.services import audit

    audit.discord_audit(
        action="announcements.enabled" if on else "announcements.disabled",
        actor=actor,
        guild_id=binding.guild.guild_id,
        metadata={"binding_id": binding.id, "target": binding.target_kind},
    )
    return row, first


def activate_now(binding, *, complete="default") -> dict:
    """The activation seed and the closing-soon list for this binding's target,
    straight away (plan D5). Safe to call twice: the seed runs once."""
    from tools.delivery import announce, announce_updates, discord_announcements
    from tools.delivery import announce_editor as editor

    row = settings_for_binding(binding)
    target = announce.Target(binding.target_kind, binding.target, row)
    if not announce.target_entitled(target):
        return {"posted": 0, "reason": "not_entitled"}
    today = timezone.localdate()
    outcome = announce.run_target(
        target,
        today,
        dry_run=False,
        complete=editor._model_complete if complete == "default" else complete,
        poster=lambda ann: discord_announcements.post(ann, drain=False),
    )
    discord_announcements.flush()
    plan = announce_updates.plan(target, today)
    plan.changed, plan.to_close = [], []  # activation posts only the list
    discord_announcements.apply_updates(plan, today)
    return {"posted": len(outcome.posted), "held": len(outcome.held)}


def populate(binding, count: int, *, actor=None) -> tuple[str, dict]:
    """``/mylo populate`` for one binding (see :mod:`.announce_populate`); the
    caller has already run the gate."""
    from tools.delivery import announce_populate

    return announce_populate.populate(binding, count, actor=actor)


def activate_target(kind: str, target_id: str) -> dict:
    """``activate_now`` for a lab or department named by id, from any binding of it
    (the seed posts to all of them)."""
    from apps.accounts.models import Department, Lab

    from tools.delivery import announce

    if not announce.enabled():
        return {"posted": 0, "reason": "switched_off"}
    obj = (Lab if kind == "lab" else Department).objects.filter(pk=target_id).first()
    if obj is None:
        return {"posted": 0, "reason": "no_target"}
    bindings = (
        resolve.bindings_for_lab(obj)
        if kind == "lab"
        else resolve.bindings_for_department(obj)
    )
    if not bindings:
        return {"posted": 0, "reason": "no_binding"}
    return activate_now(bindings[0])
