"""The one liveness rule (:mod:`tools.retrieval.liveness`).

Pure functions, no database: these are the exact predicates the nightly prune
and every feed read share, so they are worth pinning independently of either
caller. The asymmetry between a dateless grant and a dateless conference is the
whole point of the module and gets the most coverage here.
"""

from __future__ import annotations

from tools.retrieval.liveness import is_expired, is_live, is_stale
from tools.retrieval.models import ContentItem

TODAY = "2026-08-17"
CONFERENCE = ContentItem.Type.CONFERENCE
GRANT = ContentItem.Type.GRANT
FELLOWSHIP = ContentItem.Type.FELLOWSHIP


def _seen(day: str) -> dict:
    return {"last_seen": f"{day}T03:00:00+00:00"}


# --- shown or hidden -------------------------------------------------------


def test_a_conference_lives_until_its_last_written_date():
    """``prune_after`` is the *last* date on the record, not the next one, so a
    multi-round venue survives to its final round instead of vanishing at the
    first — the split ``mapping._conference_deadlines`` exists to make."""
    assert is_live(CONFERENCE, {"prune_after": "2026-08-17"}, TODAY) is True
    assert is_live(CONFERENCE, {"prune_after": "2026-12-01"}, TODAY) is True
    assert is_live(CONFERENCE, {"prune_after": "2026-08-16"}, TODAY) is False


def test_a_dateless_conference_is_hidden():
    """No deadline and no event date is nothing a reader can act on. This is
    the 156-of-912 case, invisible to expiry because an empty ``prune_after``
    can never be proven past."""
    assert is_live(CONFERENCE, {}, TODAY) is False
    assert is_live(CONFERENCE, {"prune_after": ""}, TODAY) is False


def test_a_dateless_grant_or_fellowship_is_kept():
    """The same empty string means the opposite here: a rolling call that never
    expires by design."""
    assert is_live(GRANT, {"prune_after": ""}, TODAY) is True
    assert is_live(FELLOWSHIP, {}, TODAY) is True


def test_a_past_grant_is_still_hidden():
    assert is_live(GRANT, {"prune_after": "2026-08-16"}, TODAY) is False


def test_the_comparison_survives_a_single_digit_month():
    """Zero-padded ISO on both sides is what makes the plain string compare
    correct — "2026-10-01" must read as later than "2026-08-17", which it only
    does character-by-character because the month is padded."""
    assert is_live(CONFERENCE, {"prune_after": "2026-10-01"}, TODAY) is True


# --- hidden vs deletable ---------------------------------------------------


def test_hidden_is_not_the_same_as_deletable():
    """A dateless conference is hidden immediately but must not be deleted on
    that basis alone: the source may still be listing it every night, and
    deleting it would only re-create it on the next run with a fresh
    ``first_seen``."""
    dateless = _seen("2026-08-17")
    assert is_live(CONFERENCE, dateless, TODAY) is False
    assert is_expired(CONFERENCE, dateless, TODAY) is False
    assert is_stale(CONFERENCE, dateless, TODAY) is False


def test_a_dateless_conference_becomes_deletable_once_unseen_long_enough():
    assert is_stale(CONFERENCE, _seen("2026-01-01"), TODAY) is True


def test_a_dateless_grant_is_never_stale():
    assert is_stale(GRANT, _seen("2020-01-01"), TODAY) is False


def test_a_dated_conference_is_expired_not_stale():
    """The two rules must not both claim the same row, or the prune's own
    counts double-count it."""
    dated = {"prune_after": "2020-01-01", **_seen("2020-01-01")}
    assert is_expired(CONFERENCE, dated, TODAY) is True
    assert is_stale(CONFERENCE, dated, TODAY) is False


def test_a_row_that_was_never_stamped_at_all_is_stale():
    """Nothing can save a row no ingest pass has ever claimed to have seen."""
    assert is_stale(CONFERENCE, {}, TODAY) is True


def test_first_seen_stands_in_when_last_seen_is_missing():
    assert is_stale(CONFERENCE, {"first_seen": "2026-08-16T00:00:00+00:00"}, TODAY) is (
        False
    )
    assert is_stale(CONFERENCE, {"first_seen": "2020-01-01T00:00:00+00:00"}, TODAY) is (
        True
    )
