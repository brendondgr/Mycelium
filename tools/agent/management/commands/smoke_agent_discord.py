"""``manage.py smoke_agent_discord [--scripted] [--keep]``

Mylo in Discord, end to end, without Discord (plan D). Builds a throwaway lab
with a bound server, a linked member and a guest, posts an announcement
thread, then asks through the Discord adapter exactly as the bot does: a
member and a guest in the forum thread (one shared conversation, the post as
``#1``), the member in a DM, and a guest at the ``public`` level. Each answer
is followed in the activity view and drawn with the bot's renderer, then
checked: no thinking text, nothing that can ping, every chunk under Discord's
limit, the right refusals.

Runs against the configured model (the real one) unless ``--scripted``. Turns
run inline in this process; everything is rolled back unless ``--keep``.
Exits non-zero when a check fails.
"""

from __future__ import annotations

import itertools
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def _why(out) -> str:
    """A refusal's code and sentence, for a failed check's line."""
    return "" if out else f"[{out.code}: {out.message}]"


class _Rollback(Exception):
    pass


def _scripted_port():
    from apps.core.llm import LLMResponse

    def port(*, messages, tools, tool_choice, on_delta, should_stop):
        return LLMResponse(
            content="This call funds imaging work like yours (#1).",
            finish_reason="stop",
            usage={"total_tokens": 1},
        )

    return port


class Command(BaseCommand):
    help = "End-to-end check of Mylo in Discord against a fake transport."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scripted",
            action="store_true",
            help="Use a scripted model, not the real one.",
        )
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Keep the throwaway rows (default: roll back).",
        )

    def handle(self, *args, **opts):
        self.failures: list[str] = []
        try:
            with transaction.atomic():
                self._run(scripted=opts["scripted"])
                if not opts["keep"]:
                    raise _Rollback
        except _Rollback:
            pass
        if self.failures:
            raise CommandError(f"{len(self.failures)} check(s) failed")
        self.stdout.write(self.style.SUCCESS("smoke_agent_discord: all checks passed"))

    def expect(self, ok: bool, what: str) -> None:
        if ok:
            self.stdout.write(f"  ok    {what}")
        else:
            self.failures.append(what)
            self.stdout.write(self.style.ERROR(f"  FAIL  {what}"))

    def _world(self):
        from apps.accounts.models import Lab, LabMembership
        from apps.billing.models import AddOn, Subscription, SubscriptionAddOn, Tier
        from apps.integrations.models import DiscordIdentity
        from apps.integrations.testing import add_route, bind
        from django.contrib.auth.models import User
        from django.utils import timezone

        from tools.delivery.models import Announcement, AnnouncementPost

        lab = Lab.objects.create(name="Smoke Lab", slug="smoke-agent-discord")
        sub = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
        addon, _ = AddOn.objects.get_or_create(
            slug="bot_server",
            defaults={"name": "Mylo for your server", "feature": "bot_server"},
        )
        SubscriptionAddOn.objects.create(subscription=sub, add_on=addon)
        member = User.objects.create_user("smoke-discord-member", first_name="Ana")
        member.profile.is_verified = True
        member.profile.save(update_fields=["is_verified"])
        LabMembership.objects.create(user=member, lab=lab, role="member")
        DiscordIdentity.objects.create(
            user=member,
            discord_user_id="880000000000000001",
            state=DiscordIdentity.State.ACTIVE,
            link_method=DiscordIdentity.LinkMethod.OAUTH,
        )
        binding = bind(lab=lab, guild_id="880000000000000900", guild_name="Smoke HQ")
        add_route(binding, "grants", "880000000000000010")
        ann = Announcement.objects.create(
            target_lab=lab,
            category="grant",
            state=Announcement.State.POSTED,
            snapshot={"title": "Smoke Imaging Call", "funder": "NSF"},
            write_up={"why_it_matters": "It funds cell imaging."},
            facts={"deadline": "2027-02-01"},
        )
        AnnouncementPost.objects.create(
            announcement=ann,
            binding=binding,
            channel_id="880000000000000010",
            thread_id="880000000000000011",
            thread_name="Smoke Imaging Call",
            posted_at=timezone.now(),
        )
        return lab, member

    def _run(self, *, scripted: bool) -> None:
        from mylo.bot import chat_render as render

        from tools.agent import loop, stream
        from tools.agent.models import AgentOrgPolicy, AgentThread
        from tools.agent.surfaces import discord as surface

        stream.use_memory_bus()
        port = _scripted_port() if scripted else None
        lab, _member = self._world()
        ids = itertools.count(880000000000100000)

        def start(thread):
            loop.run_turn(thread.pk, port=port)

        def ask(
            who,
            *,
            name,
            guild="880000000000000900",
            channel,
            thread="",
            parent="",
            text,
        ):
            return surface.ask(
                discord_user_id=who,
                name=name,
                guild_id=guild,
                channel_id=thread or channel,
                thread_id=thread,
                parent_id=parent,
                message_id=str(next(ids)),
                text=text,
                start=start,
            )

        def draw(handle, label):
            shown = list(surface.follow(handle, poll=0.05, max_seconds=600))
            res = surface.result(handle)
            self.expect(
                res["state"] == "answered", f"{label}: answered ({res['state']})"
            )
            chunks = render.answer_chunks(
                res.get("text") or "",
                res.get("sources") or [],
                res.get("model"),
                first=handle.first,
            )
            self.expect(
                all(len(c) < render.LIMIT for c in chunks), f"{label}: chunks fit"
            )
            self.expect(
                not any(re.search(r"<@[!&]?\d+>|@everyone|@here", c) for c in chunks),
                f"{label}: nothing can ping",
            )
            self.expect(
                not any(m.get("type") == "thinking" for m in shown)
                and all(
                    "text" not in (m.get("payload") or {})
                    for m in shown
                    if m.get("type") == "activity"
                ),
                f"{label}: no thinking shown",
            )
            self.stdout.write("    " + chunks[0][:200].replace("\n", " / "))
            return res

        self.stdout.write("Forum thread, member then guest (one conversation):")
        forum = {
            "thread": "880000000000000011",
            "parent": "880000000000000010",
            "channel": "880000000000000011",
        }
        h1 = ask(
            "880000000000000001", name="Ana", text="What is this call about?", **forum
        )
        self.expect(bool(h1), f"member's question accepted {_why(h1)}")
        if h1:
            draw(h1, "member in thread")
        h2 = ask(
            "880000000000000002", name="Visitor", text="Who could lead it?", **forum
        )
        self.expect(
            bool(h2) and h2.guest, f"guest's question accepted as a guest {_why(h2)}"
        )
        if h2:
            draw(h2, "guest in thread")
            self.expect(h1 and h2.thread_id == h1.thread_id, "one shared conversation")
            thread = AgentThread.objects.get(pk=h2.thread_id)
            self.expect(
                (thread.settings or {}).get("anchor", {}).get("kind") == "announcement",
                "the announcement is the thread's #1",
            )

        self.stdout.write("DM, member:")
        h3 = ask(
            "880000000000000001",
            name="Ana",
            guild="",
            channel="880000000000000050",
            text="Hello Mylo.",
        )
        self.expect(bool(h3), f"DM accepted {_why(h3)}")
        if h3:
            draw(h3, "member in DM")

        self.stdout.write("Refusals:")
        r = ask("880000000000000003", name="Nobody", guild="", channel="1", text="hi")
        self.expect(not r and "Connect Discord" in r.message, "unlinked DM refused")
        AgentOrgPolicy.objects.update_or_create(
            lab=lab, defaults={"discord_guests": "off"}
        )
        r = ask(
            "880000000000000004", name="Guest", channel="880000000000000020", text="hi"
        )
        self.expect(not r and r.code == "guests_off", f"guests off refused {_why(r)}")
        r = ask("1", name="x", guild="880000000000000999", channel="1", text="hi")
        self.expect(not r and r.message == surface.UNBOUND, "unbound server refused")
