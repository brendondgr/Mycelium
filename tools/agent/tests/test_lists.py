"""Lists that say whether they are complete (Q-079): the feed functions take
a deadline filter that is applied before any cut, page with an offset, and end
every result with one line saying "all of it" or how to get the rest."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from .test_kg_functions import item, lab_run, run, save, score

pytestmark = pytest.mark.django_db


def due(content, days, kind="application", confidence="confirmed", label=""):
    from tools.retrieval.read import ContentDeadline

    return ContentDeadline.objects.create(
        content=content,
        kind=kind,
        round_key=label,
        round_label=label,
        confidence=confidence,
        due_date=timezone.localdate() + timedelta(days=days),
    )


def day(days: int) -> str:
    return (timezone.localdate() + timedelta(days=days)).isoformat()


def last(out) -> str:
    return out["content"].splitlines()[-1]


def _slate_of_conferences(world, n=36, inside=(5, 14, 22, 33)):
    """``n`` conferences in the lab's slate; the ones ranked ``inside`` have a
    manuscript deadline 40–49 days out, every other one 100+ days out."""
    for rank in range(1, n + 1):
        conf = item(f"Conference {rank:02d}", "conference")
        score(conf, rank, target_lab=world.lab)
        due(conf, 40 + rank % 10 if rank in inside else 100 + rank, "manuscript")
        due(conf, 45, "event")  # the dates it is held: never "a deadline"


def test_a_deadline_window_returns_every_match_and_says_it_is_complete(world):
    _slate_of_conferences(world)
    out = run(
        world.member,
        "feeds_slate",
        {
            "types": ["conference"],
            "due_from": day(40),
            "due_to": day(49),
            "deadline": "manuscript",
        },
        kind="lab",
        obj=world.lab,
    )
    assert out["status"] == "ok"
    rows = [x for x in out["content"].splitlines() if x.startswith("- ")]
    assert [r.split("Conference ")[1][:2] for r in rows] == ["05", "14", "22", "33"]
    assert all("manuscript deadline" in r for r in rows)
    assert "checked all 36" in out["content"]
    assert last(out) == "This is the complete list: all 4 of 4 matching items."
    # With no kind named, an event's own dates are not a deadline.
    out = run(
        world.member,
        "feeds_slate",
        {"types": ["conference"], "due_from": day(40), "due_to": day(49)},
        kind="lab",
        obj=world.lab,
    )
    assert len([x for x in out["content"].splitlines() if x.startswith("- ")]) == 4
    # ... and are listed when asked for.
    out = run(
        world.member,
        "feeds_slate",
        {"due_from": day(40), "due_to": day(49), "deadline": "event"},
        kind="lab",
        obj=world.lab,
    )
    assert last(out) == "This is the complete list: all 36 of 36 matching items."


def test_a_deadline_window_keeps_who_should_look(world):
    conf = item("Named conference", "conference")
    score(
        conf, 1, target_lab=world.lab, signals={"member_fit": [{"username": "admin"}]}
    )
    due(conf, 20, "manuscript")
    out = run(
        world.member, "feeds_slate", {"due_to": day(30)}, kind="lab", obj=world.lab
    )
    row = next(x for x in out["content"].splitlines() if x.startswith("- "))
    assert "manuscript deadline" in row and "who should look: #" in row
    assert row.rstrip().endswith("Admin")


def test_no_match_is_a_complete_answer_too(world):
    _slate_of_conferences(world, n=6, inside=())
    out = run(
        world.member,
        "feeds_slate",
        {"types": ["conference"], "due_to": day(30)},
        kind="lab",
        obj=world.lab,
    )
    assert out["status"] == "ok" and "None of the 6 conferences" in out["content"]
    assert last(out).endswith("This is the complete list: 0 matching items.")


def test_a_result_too_long_for_the_budget_pages_with_an_offset(world, settings):
    settings.AGENT_RESULT_CAP_TOKENS = 500  # 2,000 characters, 600 held back
    _slate_of_conferences(world, n=36, inside=tuple(range(1, 37)))
    args = {"types": ["conference"], "due_from": day(0), "due_to": day(60)}
    first = run(world.member, "feeds_slate", args, kind="lab", obj=world.lab)
    shown = [x for x in first["content"].splitlines() if x.startswith("- ")]
    assert 0 < len(shown) < 36 and len(first["content"]) <= 2000
    assert last(first) == (
        f"This is not the complete list: only the first {len(shown)} of 36 "
        f"matching items; pass offset={len(shown)} for the rest."
    )
    seen, offset, calls = list(shown), len(shown), 0
    while offset < 36 and calls < 12:
        more = run(
            world.member,
            "feeds_slate",
            {**args, "offset": offset},
            kind="lab",
            obj=world.lab,
        )
        rows = [x for x in more["content"].splitlines() if x.startswith("- ")]
        assert rows
        seen += rows
        offset += len(rows)
        calls += 1
    assert len(seen) == 36 and len({r.split(" [")[0] for r in seen}) == 36
    assert last(more).startswith("This is the end of the list")


def test_rank_order_pages_with_an_offset(world):
    for rank in range(1, 13):
        score(item(f"Paper {rank:02d}"), rank, target_user=world.member)
    first = run(world.member, "feeds_slate", {"types": ["paper"]})
    assert "Paper 08" in first["content"] and "Paper 09" not in first["content"]
    assert "papers only the first 8 of 12" in last(first)
    assert "offset=8" in last(first)
    rest = run(world.member, "feeds_slate", {"types": ["paper"], "offset": 8})
    assert "Paper 09" in rest["content"] and "Paper 12" in rest["content"]
    assert "Paper 08" not in rest["content"]
    assert last(rest).startswith("This is the end of the slate")


def test_projects_feed_takes_the_same_filter(world):
    near, far = item("Near grant", "grant"), item("Far grant", "grant")
    score(near, 2, target_project=world.lab_project)
    score(far, 1, target_project=world.lab_project)
    due(near, 12)
    due(far, 300, confidence="anticipated")
    out = run(
        world.member,
        "projects_feed",
        {"types": ["grant"], "due_to": day(30)},
        kind="project",
        obj=world.lab_project,
    )
    assert out["status"] == "ok"
    assert "Near grant" in out["content"] and "Far grant" not in out["content"]
    assert last(out) == "This is the complete list: all 1 of 1 matching items."
    plain = run(
        world.member, "projects_feed", {}, kind="project", obj=world.lab_project
    )
    assert plain["content"].index("Far grant") < plain["content"].index("Near grant")
    assert last(plain) == "This is the complete slate: all 2 of 2 items."
    late = run(
        world.member,
        "projects_feed",
        {"due_from": day(200)},
        kind="project",
        obj=world.lab_project,
    )
    assert "Far grant" in late["content"] and ", anticipated" in late["content"]


def test_deadlines_take_a_window_a_kind_and_an_offset(world):
    for n in range(1, 8):
        conf = item(f"Meeting {n}", "conference")
        score(conf, n, target_lab=world.lab)
        due(conf, 70 + n, "manuscript")
        due(conf, 75, "event")
    grant = item("Lab grant", "grant")
    score(grant, 1, target_lab=world.lab)
    due(grant, 72)
    args = {"due_from": day(70), "due_to": day(80), "deadline": "manuscript"}
    out = run(world.member, "feeds_deadlines", args, kind="lab", obj=world.lab)
    rows = [x for x in out["content"].splitlines() if x.startswith("- ")]
    assert len(rows) == 7 and "Lab grant" not in out["content"]
    assert "This is the complete list: all 7 of 7 deadlines" in out["content"]
    part = run(
        world.member,
        "feeds_deadlines",
        {**args, "limit": 3},
        kind="lab",
        obj=world.lab,
    )
    assert "only the first 3 of 7" in part["content"]
    assert "pass offset=3" in part["content"]
    rest = run(
        world.member,
        "feeds_deadlines",
        {**args, "offset": 3},
        kind="lab",
        obj=world.lab,
    )
    assert len([x for x in rest["content"].splitlines() if x.startswith("- ")]) == 4
    only = run(
        world.member,
        "feeds_deadlines",
        {"due_from": day(70), "due_to": day(80), "types": ["grant"]},
        kind="lab",
        obj=world.lab,
    )
    assert "Lab grant" in only["content"] and "Meeting" not in only["content"]


def test_saved_items_take_a_window(world):
    soon, later = item("Soon grant", "grant"), item("Later grant", "grant")
    save(world.member, soon, deadline_date=timezone.localdate() + timedelta(days=5))
    save(world.member, later, deadline_date=timezone.localdate() + timedelta(days=90))
    out = run(world.member, "feeds_saved", {"due_to": day(30)})
    assert "Soon grant" in out["content"] and "Later grant" not in out["content"]
    assert "This is the complete list: all 1 of 1 saves." in out["content"]
    both = run(world.member, "feeds_saved", {})
    assert "This is the complete list: all 2 of 2 saves." in both["content"]


def test_a_malformed_date_is_a_malformed_call(world):
    out = run(world.member, "feeds_slate", {"due_to": "end of March"})
    assert out["status"] == "error" and out["error"]["code"] == "bad_arguments"
    assert "YYYY-MM-DD" in out["error"]["detail"]
    out = run(world.member, "feeds_slate", {"due_from": day(9), "due_to": day(3)})
    assert out["error"]["code"] == "bad_arguments"
    out = run(world.member, "feeds_slate", {"due_to": day(9), "deadline": "soon"})
    assert out["error"]["code"] == "bad_arguments"


def test_a_feed_the_caller_may_not_see_is_refused_as_before(world):
    hidden = item("Hidden conference", "conference")
    score(hidden, 1, target_project=world.other_project)
    due(hidden, 10, "manuscript")
    args = {"project": f"project:{world.other_project.pk}", "due_to": day(30)}
    for name in ("feeds_slate", "projects_feed"):
        out = run(world.member, name, args)
        assert out["status"] == "denied" and out["error"]["code"] == "not_visible"
        assert "Hidden" not in str(out)
    # Where the lab reads the reply, a person's own slate is still refused.
    mine = item("My conference", "conference")
    score(mine, 1, target_user=world.member)
    due(mine, 10, "manuscript")
    out = lab_run(
        world.member,
        "feeds_slate",
        {"due_to": day(30)},
        world.lab,
        kind="personal",
        obj=None,
    )
    assert "My conference" not in str(out)


def _slate_of_grants(world, n=30):
    """``n`` grants in the lab's slate. Those ranked 7, 19 and 28 pay up to
    EUR 5,000,000; rank 11 pays USD 5,000,000; rank 3 states no amount; every
    other one pays up to EUR 100,000 + its rank."""
    for rank in range(1, n + 1):
        if rank == 3:
            meta = {"currency": "USD"}  # the source's default, with no amount
        elif rank == 11:
            meta = {"amount": "$5,000,000", "award_ceiling": 5e6, "currency": "USD"}
        elif rank in (7, 19, 28):
            meta = {
                "amount": "€2,000,000–€5,000,000",
                "award_floor": 2e6,
                "award_ceiling": 5e6,
                "currency": "EUR",
            }
        else:
            top = 100_000 + rank
            meta = {"amount": f"€{top:,}", "award_ceiling": top, "currency": "EUR"}
        score(item(f"Grant {rank:02d}", "grant", **meta), rank, target_lab=world.lab)


def test_an_amount_filter_returns_every_match_and_says_it_is_complete(world):
    # Q-091: with no such filter Mylo read all 32 grants one call at a time,
    # and three of six such turns never answered.
    _slate_of_grants(world)
    out = run(
        world.member,
        "feeds_slate",
        {"types": ["grant"], "amount_min": 4_000_000, "currency": "EUR"},
        kind="lab",
        obj=world.lab,
    )
    assert out["status"] == "ok"
    listed = [x for x in out["content"].splitlines() if x.startswith("- ")]
    assert [x.split("Grant ")[1][:2] for x in listed] == ["07", "19", "28"]
    assert all("€2,000,000–€5,000,000" in x for x in listed)
    assert "checked all 30" in out["content"]
    assert "a highest amount of at least 4,000,000 EUR" in out["content"]
    assert last(out).startswith(
        "This is the complete list: all 3 of 3 matching items. 1 of the 30 state "
        "no amount, so they cannot match. 1 state theirs in another currency "
        "(1 in USD) and were not compared"
    )
    assert len(out["refs"]) == 4  # the lab and the three grants


def test_a_currency_alone_and_a_ceiling_are_filters_too(world):
    _slate_of_grants(world)
    usd = run(
        world.member, "feeds_slate", {"currency": "$"}, kind="lab", obj=world.lab
    )
    assert [x for x in usd["content"].splitlines() if x.startswith("- ")] == [
        "- #2 Grant 11 [grant] — $5,000,000"
    ]
    assert "an amount stated in USD" in usd["content"]
    # Asked in dollars, the euro grants are not compared: the result says so,
    # so the next call is this list in euros and not every grant read in turn.
    assert last(usd).endswith(
        "28 state theirs in another currency (28 in EUR) and were not compared: "
        "amounts are not converted. Call again with that currency and the amount "
        "in it to list them."
    )
    small = run(
        world.member,
        "feeds_slate",
        {"amount_max": "100,005", "currency": "eur"},
        kind="lab",
        obj=world.lab,
    )
    # ranks 1, 2, 4 and 5: rank 3 states no amount
    assert last(small).startswith("This is the complete list: all 4 of 4 matching")
    none = run(
        world.member,
        "feeds_slate",
        {"amount_min": "1 billion"},
        kind="lab",
        obj=world.lab,
    )
    assert "None of the 30 grants" in none["content"]
    assert "0 matching items" in last(none)


def test_an_amount_and_a_deadline_window_are_both_applied(world):
    rich_soon = item("Rich soon", "grant", amount="€9,000,000", award_ceiling=9e6,
                     currency="EUR")  # fmt: skip
    rich_late = item("Rich late", "grant", amount="€9,000,000", award_ceiling=9e6,
                     currency="EUR")  # fmt: skip
    poor_soon = item("Poor soon", "grant", amount="€9,000", award_ceiling=9e3,
                     currency="EUR")  # fmt: skip
    for rank, (grant, days) in enumerate(
        ((rich_soon, 10), (rich_late, 200), (poor_soon, 10)), start=1
    ):
        score(grant, rank, target_project=world.lab_project)
        due(grant, days)
    out = run(
        world.member,
        "projects_feed",
        {"due_to": day(30), "amount_min": 1e6},
        kind="project",
        obj=world.lab_project,
    )
    listed = [x for x in out["content"].splitlines() if x.startswith("- ")]
    assert len(listed) == 1 and "Rich soon" in listed[0]
    assert "€9,000,000; application deadline" in listed[0]
    assert last(out) == "This is the complete list: all 1 of 1 matching items."


def test_a_slate_row_says_what_the_item_pays(world):
    _slate_of_grants(world, n=4)
    fellowship = item(
        "A fellowship", "fellowship", amount_raw="up to $28,000", amount_max=28000,
        amount_currency="USD", amount_kind="up_to",
    )  # fmt: skip
    score(fellowship, 1, target_lab=world.lab)
    out = run(world.member, "feeds_slate", {}, kind="lab", obj=world.lab)
    assert "Grant 01 [grant, €100,001]" in out["content"]
    assert "Grant 03 [grant]" in out["content"]  # no amount stated: none shown
    assert "A fellowship [fellowship, up to $28,000]" in out["content"]


def test_a_malformed_amount_is_a_malformed_call(world):
    out = run(world.member, "feeds_slate", {"amount_min": "a lot"})
    assert out["error"]["code"] == "bad_arguments"
    assert "amount_min must be a number" in out["error"]["detail"]
    out = run(world.member, "feeds_slate", {"currency": "European money"})
    assert out["error"]["code"] == "bad_arguments"
    out = run(world.member, "feeds_slate", {"amount_min": 9, "amount_max": 3})
    assert out["error"]["code"] == "bad_arguments"
