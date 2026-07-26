"""The authorization gate: who, how often, what, and whether the plan covers it.

The two assertions that matter most are the ones about what a *refusal* reveals: a
lab the caller cannot see must be indistinguishable from a lab that does not exist,
and no command argument may ever grant anything.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import DiscordGuildLink, DiscordIdentity
from apps.integrations.services import gate, state
from apps.integrations.services.gate import Denial

from .base import clear_discord_cache, discord_test_settings, grant_bot_server

SNOWFLAKE = "900000000000000010"
OUTSIDER = "900000000000000011"


@pytest.fixture(autouse=True)
def _discord_settings():
    """Swap every cache to LocMem, as the rest of the Discord suite does.

    The gate reads Redis for rate limiting, so without this the tests would either
    need a broker or would exercise the fail-closed path by accident and pass for
    entirely the wrong reason.
    """
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def _linked(username: str, snowflake: str = SNOWFLAKE):
    user = User.objects.create_user(username)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
    )
    return user


def _lab(name="Neuro Lab", slug="neuro", *, with_addon=True):
    lab = Lab.objects.create(name=name, slug=slug)
    if with_addon:
        grant_bot_server(lab)
    return lab


# --------------------------------------------------------------------------- #
# Stage 1 — identity
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_an_unlinked_snowflake_is_told_how_to_connect(db) -> None:
    result = gate.authorize(discord_user_id=SNOWFLAKE, action="digest")

    assert not result.ok
    assert result.denial is Denial.NOT_LINKED
    assert "Connect Discord" in result.message or "/activate" in result.message


@pytest.mark.django_db
def test_a_revoked_identity_does_not_count_as_linked(db) -> None:
    user = User.objects.create_user("revoked")
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=SNOWFLAKE,
        state=DiscordIdentity.State.REVOKED,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
    )

    assert gate.authorize(discord_user_id=SNOWFLAKE, action="digest").denial is (
        Denial.NOT_LINKED
    )


@pytest.mark.django_db
def test_a_linked_user_passes_a_personal_action(db) -> None:
    user = _linked("linked")
    result = gate.authorize(discord_user_id=SNOWFLAKE, action="digest")
    assert result.ok
    assert result.user == user


# --------------------------------------------------------------------------- #
# Stage 2 — rate limiting
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_search_is_limited_harder_than_other_commands(db, settings) -> None:
    settings.DISCORD_COMMAND_RATE_LIMITS = {"search": (2, 60), "command": (20, 60)}
    _linked("searcher")

    assert gate.authorize(discord_user_id=SNOWFLAKE, action="search").ok
    assert gate.authorize(discord_user_id=SNOWFLAKE, action="search").ok
    third = gate.authorize(discord_user_id=SNOWFLAKE, action="search")

    assert not third.ok
    assert third.denial is Denial.RATE_LIMITED
    # A different bucket is untouched by search's exhaustion.
    assert gate.authorize(discord_user_id=SNOWFLAKE, action="digest").ok


@pytest.mark.django_db
def test_one_persons_limit_does_not_affect_another(db, settings) -> None:
    settings.DISCORD_COMMAND_RATE_LIMITS = {"search": (1, 60), "command": (20, 60)}
    _linked("a", SNOWFLAKE)
    _linked("b", OUTSIDER)

    gate.authorize(discord_user_id=SNOWFLAKE, action="search")
    assert not gate.authorize(discord_user_id=SNOWFLAKE, action="search").ok
    assert gate.authorize(discord_user_id=OUTSIDER, action="search").ok


@pytest.mark.django_db
def test_rate_limiting_denies_when_the_cache_is_unreachable(
    db, monkeypatch
) -> None:
    """Fail closed: an outage must not silently unmeter the command surface."""
    _linked("linked")

    def boom():
        raise RuntimeError("redis is down")

    monkeypatch.setattr(state, "_cache", boom)

    result = gate.authorize(discord_user_id=SNOWFLAKE, action="search")
    assert not result.ok
    assert result.denial is Denial.RATE_LIMITED


@pytest.mark.django_db
def test_the_activation_lockout_also_blocks_commands(db) -> None:
    """One hostile snowflake, one lockout — it should not have a second surface."""
    _linked("locked")
    for _ in range(10):
        state.record_failure(SNOWFLAKE)

    assert not gate.authorize(discord_user_id=SNOWFLAKE, action="digest").ok


# --------------------------------------------------------------------------- #
# Stage 3 — object permission, and what a refusal reveals
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_lab_manager_may_configure_their_lab(db) -> None:
    user = _linked("manager")
    lab = _lab()
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.OWNER)

    result = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug=lab.slug
    )
    assert result.ok
    assert result.lab == lab


@pytest.mark.django_db
def test_a_plain_member_may_not_configure_the_lab(db) -> None:
    user = _linked("member")
    lab = _lab()
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)

    result = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug=lab.slug
    )
    assert not result.ok
    assert result.denial is Denial.FORBIDDEN


@pytest.mark.django_db
def test_a_forged_slug_reveals_nothing_about_which_labs_exist(db) -> None:
    """The security property: naming a real lab you cannot see must look exactly
    like naming one that does not exist.

    Otherwise anyone who can type a slug can enumerate every organisation on the
    platform by watching which error comes back.
    """
    _linked("outsider")
    _lab(name="Secret Lab", slug="secret")

    real_but_forbidden = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug="secret"
    )
    pure_fiction = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug="does-not-exist"
    )

    assert real_but_forbidden.denial is pure_fiction.denial
    assert real_but_forbidden.message == pure_fiction.message


@pytest.mark.django_db
def test_naming_a_lab_never_grants_anything(db) -> None:
    """Authority comes from the interaction's user id, not from an argument."""
    _linked("nobody")
    lab = _lab()

    assert not gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug=lab.slug
    ).ok


@pytest.mark.django_db
def test_the_guild_supplies_the_lab_when_no_slug_is_given(db) -> None:
    user = _linked("guild-manager")
    lab = _lab()
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.ADMIN)
    DiscordGuildLink.objects.create(
        lab=lab, guild_id="g-1", state=DiscordGuildLink.State.ACTIVE
    )

    result = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", guild_id="g-1"
    )
    assert result.ok
    assert result.lab == lab


# --------------------------------------------------------------------------- #
# Stage 4 — entitlement, at the point of use
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_lab_without_the_bot_addon_is_refused_with_an_upgrade_path(db) -> None:
    """Checked here, not trusted from install time — plans lapse."""
    user = _linked("unpaid-manager")
    lab = _lab(with_addon=False)
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.OWNER)

    result = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug=lab.slug
    )

    assert not result.ok
    assert result.denial is Denial.NOT_ENTITLED
    assert "add-on" in result.message
    assert lab.name in result.message  # says which lab, so it is actionable


@pytest.mark.django_db
def test_entitlement_is_checked_after_permission_not_before(db) -> None:
    """A stranger must not learn a lab's billing state by naming it."""
    _linked("stranger")
    lab = _lab(with_addon=False)

    result = gate.authorize(
        discord_user_id=SNOWFLAKE, action="setup", lab_slug=lab.slug
    )
    assert result.denial is Denial.FORBIDDEN  # not NOT_ENTITLED


@pytest.mark.django_db
def test_personal_commands_need_no_lab_plan(db) -> None:
    """Search and digest are personal reads; a lab add-on is irrelevant to them."""
    _linked("free-user")
    for action in ("search", "digest", "saves"):
        assert gate.authorize(discord_user_id=SNOWFLAKE, action=action).ok


# --------------------------------------------------------------------------- #
# Stage 5 — audit
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_every_outcome_is_audited_exactly_once(db) -> None:
    from apps.accounts.models import AuditEvent

    _linked("audited")
    gate.authorize(discord_user_id=SNOWFLAKE, action="digest")  # allowed
    gate.authorize(discord_user_id=OUTSIDER, action="digest")  # not linked

    rows = AuditEvent.objects.filter(action="discord.command.digest")
    assert rows.count() == 2
    outcomes = {r.metadata.get("outcome") for r in rows}
    assert outcomes == {"allowed", "not_linked"}


@pytest.mark.django_db
def test_the_audit_trail_never_stores_a_raw_snowflake(db) -> None:
    from apps.accounts.models import AuditEvent

    _linked("audited")
    gate.authorize(discord_user_id=SNOWFLAKE, action="digest")

    row = AuditEvent.objects.get(action="discord.command.digest")
    assert SNOWFLAKE not in str(row.metadata)
    assert row.metadata["discord_user_hash"]
