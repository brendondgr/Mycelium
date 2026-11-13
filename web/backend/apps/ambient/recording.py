"""What Mylo records, per server and per project — both halves of the switch.

Two people hold a switch over the same message (settings plan, "What Mylo
records"):

* **The head's**, on the server: :attr:`Source.consent_state`, turned on and off
  by whoever runs the org's servers (``org.servers.manage``). While it is off
  nobody in that server is recorded.
* **The member's**, on themselves: the per-platform :class:`ListeningConsent`,
  and beneath it a :class:`RecordingExclusion` per server and per project.

Both must be on for anything to be recorded, and the head's off **wins**: a
member's switch for a server whose head turned listening off reads off and
locked, and turning it back on is refused (:class:`Locked`) — the member can
only add exclusions there, never lift one. Eligibility enforces the same rule on
arrival (:func:`.eligibility.observable`); this module is the read and the
write the settings pages use.
"""

from __future__ import annotations

from django.db.models import Q

from .models import RecordingExclusion, Source

#: The kinds of source that are a shared server rather than one person's chat.
SERVER_KINDS = (
    Source.Kind.DISCORD_GUILD,
    Source.Kind.SLACK_WORKSPACE,
    Source.Kind.TEAMS_TEAM,
)

LOCKED_REASON = (
    "Listening is off for this server. Only its lab or department can turn it "
    "back on."
)


class Locked(Exception):
    """A member tried to switch recording on where the head switched it off."""


# --------------------------------------------------------------------------- #
# Which servers belong to which org
# --------------------------------------------------------------------------- #


def _org_guild_ids(*, labs=(), departments=()) -> dict[str, list[str]]:
    """Discord guild id → the names of the given orgs bound in it (live only)."""
    from apps.integrations.models import DiscordGuildLink, DiscordTargetBinding

    rows = (
        DiscordTargetBinding.objects.filter(
            state=DiscordTargetBinding.State.ACTIVE,
            guild__state=DiscordGuildLink.State.ACTIVE,
        )
        .filter(Q(lab__in=list(labs)) | Q(department__in=list(departments)))
        .select_related("guild", "lab", "department")
    )
    out: dict[str, list[str]] = {}
    for binding in rows:
        target = binding.lab or binding.department
        out.setdefault(binding.guild.guild_id, []).append(target.name)
    return out


def _guild_names(guild_ids) -> dict[str, str]:
    from apps.integrations.models import DiscordGuildLink

    return dict(
        DiscordGuildLink.objects.filter(guild_id__in=list(guild_ids)).values_list(
            "guild_id", "guild_name_cache"
        )
    )


def _member_orgs(user) -> tuple[list, list]:
    """The labs and departments ``user`` belongs to, a department's labs'
    members included (a department member is anyone it can reach)."""
    from apps.accounts.models import Department, Lab

    labs = list(Lab.objects.filter(memberships__user=user).distinct())
    departments = list(
        Department.objects.filter(
            Q(owner=user)
            | Q(memberships__user=user)
            | Q(labs__memberships__user=user)
        ).distinct()
    )
    return labs, departments


def member_servers(user) -> list[Source]:
    """Every shared server whose listening could reach ``user``: the sources of
    the Discord servers their labs and departments are bound in, and their
    labs' Slack workspaces and Teams teams. A server Mylo never listened in has
    no source and records nobody, so it is not listed."""
    labs, departments = _member_orgs(user)
    guild_ids = _org_guild_ids(labs=labs, departments=departments)
    return list(
        Source.objects.filter(
            Q(kind=Source.Kind.DISCORD_GUILD, external_id__in=list(guild_ids))
            | Q(
                kind__in=[Source.Kind.SLACK_WORKSPACE, Source.Kind.TEAMS_TEAM],
                lab__in=labs,
            )
        )
        .select_related("lab")
        .order_by("label", "pk")
    )


def _source_orgs(source: Source) -> list[str]:
    if source.kind == Source.Kind.DISCORD_GUILD:
        from apps.integrations.services import resolve

        return [
            (b.lab or b.department).name
            for b in resolve.bindings_for_guild(source.external_id)
            if (b.lab or b.department) is not None
        ]
    return [source.lab.name] if source.lab_id else []


# --------------------------------------------------------------------------- #
# The member's half
# --------------------------------------------------------------------------- #


def member_state(user) -> dict:
    """The member's per-server and per-project switches, with the locks."""
    from apps.research.models import Project

    excluded_sources = set(
        RecordingExclusion.objects.filter(user=user, source__isnull=False).values_list(
            "source_id", flat=True
        )
    )
    excluded_projects = set(
        RecordingExclusion.objects.filter(
            user=user, project__isnull=False
        ).values_list("project_id", flat=True)
    )
    sources = member_servers(user)
    names = _guild_names(
        s.external_id for s in sources if s.kind == Source.Kind.DISCORD_GUILD
    )
    servers = []
    for source in sources:
        locked = not source.listening
        label = (
            names.get(source.external_id)
            if source.kind == Source.Kind.DISCORD_GUILD
            else ""
        )
        servers.append(
            {
                "id": source.pk,
                "label": label or source.label or source.get_kind_display(),
                "platform": source.platform,
                "orgs": _source_orgs(source),
                "server_listening": source.listening,
                "excluded": source.pk in excluded_sources,
                # Both halves: what the member's switch shows.
                "recording": source.listening and source.pk not in excluded_sources,
                "locked": locked,
                "locked_reason": LOCKED_REASON if locked else "",
            }
        )
    projects = [
        {
            "id": str(project.pk),
            "name": project.name,
            "excluded": project.pk in excluded_projects,
        }
        for project in Project.objects.visible_to(user)
        .filter(is_archived=False)
        .order_by("name", "pk")
    ]
    return {"servers": servers, "projects": projects}


def set_server(user, source_id, *, record: bool) -> None:
    """Keep one server out (``record=False``) or lift that (``record=True``).

    Lifting is refused while the server's own switch is off: the head's off
    wins, so a member cannot switch recording back on there.
    """
    source = next(
        (s for s in member_servers(user) if str(s.pk) == str(source_id)), None
    )
    if source is None:
        raise LookupError("not one of your servers")
    if record:
        if not source.listening:
            raise Locked(LOCKED_REASON)
        RecordingExclusion.objects.filter(user=user, source=source).delete()
    else:
        RecordingExclusion.objects.get_or_create(user=user, source=source)
        _drop_buffered(source)


def set_project(user, project_id, *, record: bool) -> None:
    """Keep one project out (``record=False``) or lift that."""
    from apps.research.models import Project

    project = Project.objects.visible_to(user).filter(pk=project_id).first()
    if project is None:
        raise LookupError("no such project")
    if record:
        RecordingExclusion.objects.filter(user=user, project=project).delete()
    else:
        RecordingExclusion.objects.get_or_create(user=user, project=project)


def _drop_buffered(source: Source) -> None:
    """Discard what this server still holds from people no longer eligible —
    an opt-out stops what is waiting for tonight's read, not only what comes
    next."""
    from .models import RawMessageRef
    from .reconcile import drop_ineligible

    refs = RawMessageRef.objects.filter(source=source, read_at__isnull=True)
    drop_ineligible(source, refs.select_related("speaker"))


# --------------------------------------------------------------------------- #
# The head's half
# --------------------------------------------------------------------------- #


def org_servers(org) -> list[dict]:
    """The org's Discord servers and whether Mylo listens in each — the head's
    switch. Slack and Teams keep their own cards (``SlackLabCard``,
    ``TeamsLabCard``), which already hold that switch for a lab."""
    from apps.accounts.models import Lab

    from .eligibility import ambient_enabled
    from .service import guild_source

    if isinstance(org, Lab):
        guilds = _org_guild_ids(labs=[org])
    else:
        guilds = _org_guild_ids(departments=[org])
    names = _guild_names(guilds)
    out = []
    for guild_id in sorted(guilds, key=lambda g: (names.get(g) or "", g)):
        source = guild_source(guild_id)
        out.append(
            {
                "guild_id": guild_id,
                "name": names.get(guild_id) or "Discord server",
                "listening": bool(source and source.listening),
                "available": ambient_enabled(),
                "shared_with": [n for n in guilds[guild_id] if n != org.name],
            }
        )
    return out


def set_org_server(org, guild_id: str, *, on: bool, changed_by) -> dict:
    """Turn listening on or off for one of the org's Discord servers."""
    from apps.accounts.models import Lab

    from .service import set_guild_listening

    guilds = (
        _org_guild_ids(labs=[org])
        if isinstance(org, Lab)
        else _org_guild_ids(departments=[org])
    )
    if str(guild_id) not in guilds:
        raise LookupError("not one of this org's servers")
    return set_guild_listening(
        str(guild_id),
        on=on,
        changed_by=changed_by,
        lab=org if isinstance(org, Lab) else None,
    )
