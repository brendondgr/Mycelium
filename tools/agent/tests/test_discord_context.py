"""Who sees what in a conversation, and what an answer may claim.

* a person keeps their own lookups in a channel conversation;
* another asker's lookups are replayed only when all they read is visible to
  the person asking now;
* a reply to one of Mylo's answers continues that conversation;
* ``/mylo new`` starts a fresh one;
* an answer whose details are not in what Mylo read is sent back once, then
  cut down; a runaway loop is retried, never posted.
"""

from __future__ import annotations

import pytest

from tools.agent import loop, rebuild, refs, service, store, verify
from tools.agent.caller import for_thread
from tools.agent.models import AgentDiscordTurn, AgentThread, AgentThreadLink
from tools.agent.surfaces import discord as surface

from . import test_discord_surface as _surface_tests
from .conftest import make_user, thread_for
from .test_discord_surface import GUILD, ask

#: The Discord test settings and the bound server, shared with those tests.
_discord = _surface_tests._discord
server = _surface_tests.server

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #
def _speaker(who: str) -> dict:
    return {"kind": "member", "user_id": None, "discord_user_id": who, "name": who}


def _turn(thread, who, question, *, name, refs_=(), content, answer):
    store.append(thread, "user", {"text": question, "speaker": _speaker(who)})
    call = {"id": f"c-{question}", "name": name, "arguments": "{}"}
    store.append(thread, "assistant", {"text": "", "tool_calls": [call]})
    store.append(
        thread,
        "tool_result",
        {
            "call_id": call["id"],
            "name": name,
            "status": "ok",
            "refs": list(refs_),
            "content": content,
        },
    )
    store.append(thread, "assistant", {"text": answer, "final": True})


@pytest.fixture
def shared_thread():
    thread = thread_for(make_user("ada"))
    thread.shared = True
    thread.user = None  # a shared thread has no owner
    thread.settings = {
        "refs": [
            {"n": 1, "ref": "item:public", "kind": "paper", "title": "Open"},
            {"n": 2, "ref": "profile:ada", "kind": "profile", "title": "Ada"},
        ]
    }
    thread.save()
    return thread


def _tool_texts(thread, caller=None):
    msgs = rebuild.messages(thread, store.events(thread), kind="chat", caller=caller)
    return [m["content"] for m in msgs if m["role"] == "tool"]


def test_a_person_keeps_their_own_earlier_lookups(shared_thread):
    _turn(shared_thread, "100", "find it", name="corpus_search", refs_=[2],
          content="private profile text", answer="Found it.")
    store.append(shared_thread, "user", {"text": "more?", "speaker": _speaker("100")})
    assert _tool_texts(shared_thread) == ["private profile text"]


def test_another_askers_private_lookup_stays_hidden(shared_thread, monkeypatch):
    monkeypatch.setattr(refs, "visible_here", lambda caller, ref: ref == "item:public")
    _turn(shared_thread, "100", "me", name="me_profile", refs_=[2],
          content="private profile text", answer="You are Ada.")
    _turn(shared_thread, "100", "paper", name="corpus_item", refs_=[1],
          content="open paper text", answer="It is open.")
    store.append(shared_thread, "user", {"text": "and?", "speaker": _speaker("200")})
    caller = for_thread(shared_thread)
    texts = _tool_texts(shared_thread, caller)
    assert texts == ["open paper text"]  # the visible lookup only
    # Without a caller nothing of another person's crosses over.
    assert _tool_texts(shared_thread) == []


def test_a_lookup_written_for_its_asker_never_crosses(shared_thread, monkeypatch):
    # The lab is visible to the next asker, but org_lab's text is written for
    # whoever called it ("Your role: …"), so it stays with them.
    monkeypatch.setattr(refs, "visible_here", lambda caller, ref: True)
    _turn(shared_thread, "100", "our lab?", name="org_lab", refs_=[1],
          content="Your role: owner", answer="It images cells.")
    store.append(shared_thread, "user", {"text": "and?", "speaker": _speaker("200")})
    assert _tool_texts(shared_thread, for_thread(shared_thread)) == []


def test_visible_results_are_what_the_verifier_reads(shared_thread):
    _turn(shared_thread, "100", "q", name="corpus_item", refs_=[1],
          content="Authors: Bouchiha", answer="ok")
    store.append(shared_thread, "user", {"text": "again", "speaker": _speaker("100")})
    results = rebuild.visible_results(shared_thread, store.events(shared_thread))
    assert [r["content"] for r in results] == ["Authors: Bouchiha"]


# --------------------------------------------------------------------------- #
# The verifier
# --------------------------------------------------------------------------- #
SOURCE = verify.source_text(
    [
        {
            "content": "#1 [paper] TACTIC-KG\nAuthors: Mouhamed Amine Bouchiha, "
            "Grégory Blanc\nVenue: Lecture Notes in Computer Science (2026)\n"
            "DOI: 10.1007/978-3-032-38692-2_24\nF1 reached 87.5%."
        }
    ]
)


def test_details_read_from_the_item_pass():
    text = (
        "**TACTIC-KG** (#1)\n- **Authors:** Mouhamed Amine Bouchiha, Gregory Blanc\n"
        "- **Venue:** Lecture Notes in Computer Science (2026)\n"
        "- **DOI:** https://doi.org/10.1007/978-3-032-38692-2_24\nIt reports 87.5%."
    )
    assert verify.unsupported(text, SOURCE) == []


def test_made_up_details_are_caught():
    text = (
        "- **Authors:** Yuxuan Zhang, Yifan Chen\n"
        "- **DOI:** 10.1145/1234567.7654321\nIt scores 92% F1."
    )
    claims = verify.unsupported(text, SOURCE)
    assert "- **Authors:** Yuxuan Zhang, Yifan Chen" in claims
    assert "92%" in claims
    stripped = verify.strip_claims(text, claims)
    assert "Zhang" not in stripped and "92%" not in stripped


def test_an_invented_venue_sharing_words_with_the_evidence_is_caught():
    # EXP-2026-11-013: "Marine Forecasting Letters" passed on two of its three
    # words; now every distinctive word must be in what was read.
    source = verify.source_text(
        [{"content": "Marine heatwave forecasting with ML. Venue: Ocean Science"}]
    )
    assert verify.unsupported("- Venue: Marine Forecasting Letters", source) == [
        "- Venue: Marine Forecasting Letters"
    ]
    assert verify.unsupported("- Venue: Ocean Science", source) == []


def test_a_wrong_year_beside_the_authors_is_caught():
    assert verify.unsupported(
        "- **Authors:** Mouhamed Amine Bouchiha, Gregory Blanc (2024)", SOURCE
    ) == ["- **Authors:** Mouhamed Amine Bouchiha, Gregory Blanc (2024)"]
    assert verify.unsupported(
        "- **Authors:** Mouhamed Amine Bouchiha, Gregory Blanc (2026)", SOURCE
    ) == []


def test_an_amount_in_short_form_is_backed_by_the_long_form():
    # EXP-2026-11-013: two of three repairs removed "€1.5–15M" because the call
    # said "€1,500,000–€15,000,000".
    source = verify.source_text(
        [{"content": "EU Space Partnership. Budget: €1,500,000–€15,000,000."}]
    )
    short = "#10 (EU Space Partnership — €1.5–15M, TRL 7–8)"
    assert verify.unsupported(short, source) == []
    assert verify.unsupported("- Amount: €1.5M to €15 million", source) == []
    assert verify.unsupported("It is worth €2.5M.", source) == ["2.5"]
    wrong = "- Amount: €20 million"
    assert verify.unsupported(wrong, source) == [wrong]
    # rounding at the written precision is not an error; past it is
    rounded = verify.source_text([{"content": "Amount: €1,000,000–€8,925,000"}])
    assert verify.unsupported("Budgets run €1.0M–€8.9M.", rounded) == []
    assert verify.unsupported("Budgets run €1.0M–€8.7M.", rounded) == ["8.7"]
    # a link's digits are not an amount
    linked = verify.source_text([{"content": "Link: https://doi.org/10.1145/3770855.3818893"}])
    assert verify.unsupported("It is worth $3.8 million.", linked) == ["3.8"]


def test_a_citation_known_only_by_title_is_unread(shared_thread):
    assert verify.unread(shared_thread, "See #1 and #2.", seen={2}) == [1]


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
def _send(thread, text):
    return service.send(for_thread(thread), thread, text, start=lambda t: None)


def _events(thread, kind):
    return [e.payload for e in store.events(thread) if e.type == kind]


def _final(thread):
    finals = [p for p in _events(thread, "assistant") if p.get("final")]
    return finals[-1]["text"] if finals else None


def test_unbacked_details_get_a_repair_with_functions_on(scripted):
    thread = thread_for(make_user("ada"))
    _send(thread, "who wrote it?")
    model = scripted(
        "- **Authors:** Yuxuan Zhang, Yifan Chen", "I couldn't find the authors."
    )
    loop.run_turn(thread.pk, port=model)
    verdicts = _events(thread, "verdict")
    assert verdicts[0]["action"] == "repair"
    assert verdicts[0]["unsupported"] == ["- **Authors:** Yuxuan Zhang, Yifan Chen"]
    assert model.requests[1]["tool_choice"] != "none"  # free to go and read
    assert _final(thread) == "I couldn't find the authors."


def test_details_still_unbacked_after_the_repair_are_removed(scripted):
    thread = thread_for(make_user("ada"))
    _send(thread, "who wrote it?")
    model = scripted(
        "Here it is.\n- **Authors:** Yuxuan Zhang",
        "Here it is.\n- **Authors:** Yuxuan Zhang",
    )
    loop.run_turn(thread.pk, port=model)
    assert _final(thread) == "Here it is."
    assert _events(thread, "verdict")[-1]["action"] == "stripped"
    assert any(n.get("text") == loop.CLAIMS_REMOVED for n in _events(thread, "note"))


LOOPED = "Here's what I found:\n- Authors: " + "Yifan Chen, " * 40


def test_a_runaway_answer_is_retried_and_never_posted(scripted):
    thread = thread_for(make_user("ada"))
    _send(thread, "tell me")
    model = scripted(LOOPED, "A short, clean answer.")
    loop.run_turn(thread.pk, port=model)
    assert _final(thread) == "A short, clean answer."
    assert all("Yifan" not in p.get("text", "") for p in _events(thread, "assistant"))
    assert _events(thread, "verdict")[0]["action"] == "runaway_retry"


def test_a_second_runaway_posts_an_honest_line(scripted):
    thread = thread_for(make_user("ada"))
    _send(thread, "tell me")
    loop.run_turn(thread.pk, port=scripted(LOOPED, LOOPED))
    assert _final(thread) == loop.RUNAWAY_GIVE_UP


# --------------------------------------------------------------------------- #
# Discord: replies and /mylo new
# --------------------------------------------------------------------------- #
def _reply(snowflake, to, *, channel="general"):
    from .test_discord_surface import _n

    return surface.ask(
        discord_user_id=snowflake,
        name="Visitor",
        guild_id=GUILD,
        channel_id=channel,
        thread_id="",
        parent_id="",
        message_id=str(next(_n)),
        text="and this?",
        start=lambda t: None,
        reply_to_id=to,
    )


def test_a_reply_to_someones_answer_continues_their_conversation(server):
    a = ask(server.member_id, channel="general")
    surface.set_status_message(a, "77001")
    own = ask(server.admin_id, channel="general")
    assert own.thread_id != a.thread_id  # a channel: one each
    joined = _reply(server.admin_id, "77001")
    assert joined.thread_id == a.thread_id


def test_a_reply_to_a_later_chunk_finds_the_conversation(server):
    a = ask(server.member_id, channel="general")
    surface.finish(a, "answered", ["77100", "77101"])
    assert AgentDiscordTurn.objects.get(pk=a.turn_id).message_ids == ["77100", "77101"]
    assert _reply(server.admin_id, "77101").thread_id == a.thread_id


def test_a_reply_to_anything_else_uses_the_askers_own_conversation(server):
    own = ask(server.admin_id, channel="general")
    assert _reply(server.admin_id, "12345").thread_id == own.thread_id


def test_mylo_new_starts_afresh_and_old_answers_still_continue(server):
    a = ask(server.member_id, channel="general")
    surface.set_status_message(a, "77200")
    line = surface.new_command(
        discord_user_id=server.member_id, guild_id=GUILD, place_id="general"
    )
    assert line.startswith("Fresh start")
    assert AgentThreadLink.objects.get(thread_id=a.thread_id).closed_at is not None
    fresh = ask(server.member_id, channel="general")
    assert fresh.thread_id != a.thread_id
    assert _reply(server.member_id, "77200").thread_id == a.thread_id
    again = surface.new_command(
        discord_user_id=server.member_id, guild_id="", place_id="nowhere"
    )
    assert "no conversation" in again
    assert AgentThread.objects.filter(pk=a.thread_id).exists()  # nothing deleted
