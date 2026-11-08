"""The report body's grammar, and the two renderers that must agree on it.

Only the Python half is exercised here; its TypeScript mirror lives in
``markdown-prose.tsx`` and the two are kept in step by hand, which is why the
rules are stated once in ``report_grammar.py`` and both point at it.

The construct worth the most attention is the labelled beat. Until now any bullet
flushed the open ordered list, which split an alert's four beats away from the
title they belong to — a title stranded above its own reasoning, and at a page
break, above nothing at all.
"""

from __future__ import annotations

from tools.delivery import report_grammar as grammar


def test_citations_are_found_in_order_and_deduped() -> None:
    text = "It tests the same question [P2]. Its data is yours [P1], again [P2]."
    assert grammar.citations(text) == [2, 1]


def test_state_markers_are_grammar_for_the_verifier_not_prose() -> None:
    """A reader does not need to be told which JSON key a sentence came from."""
    text = "That is the question your paper asks [S:slow.claimed_contribution]."

    assert grammar.state_paths(text) == ["slow.claimed_contribution"]
    assert grammar.strip_markers(text) == "That is the question your paper asks."


def test_stripping_a_marker_does_not_leave_a_space_before_the_full_stop() -> None:
    assert grammar.strip_markers("Two [S:a.b] words [S:c.d] here .") == (
        "Two words here."
    )


def test_a_labelled_beat_is_distinguishable_from_a_plain_bullet() -> None:
    """The distinction is what keeps beats attached to their item."""
    assert grammar.LABELLED_BEAT.match("- **Where you still differ:** it does not…")
    assert not grammar.LABELLED_BEAT.match("- An ordinary bullet")
    # A bolded run that is not a label does not qualify — the colon is the token.
    assert not grammar.LABELLED_BEAT.match("- **NEW** something")


def test_the_references_block_is_rendered_by_code() -> None:
    """Plan H6: a model renumbering these would re-point every citation."""
    block = grammar.references_block(
        [
            {"n": 1, "title": "A paper", "source": "arXiv", "kind": "paper"},
            {"n": 2, "title": "A grant"},
        ]
    )

    assert block.splitlines()[0] == "## References"
    assert "- **[P1]** A paper · arXiv · paper" in block
    assert "- **[P2]** A grant" in block
    assert grammar.references_block([]) == ""


def test_the_pdf_renders_a_citation_as_a_marker_not_as_literal_brackets() -> None:
    from tools.delivery.daily_report_pdf import _MUTED_HEX, _inline

    rendered = _inline("It tests the same question [P2].")

    assert _MUTED_HEX in rendered
    assert "[P2]" in rendered


def test_the_pdf_strips_state_markers_before_display() -> None:
    from tools.delivery.daily_report_pdf import _inline

    assert "[S:" not in _inline("A claim [S:slow.problem] of yours.")


def test_a_beat_stays_with_its_numbered_item_in_the_pdf() -> None:
    """A title stranded above its own reasoning is the failure being fixed."""
    from tools.delivery.daily_report_pdf import _markdown_flowables, _styles

    flow = _markdown_flowables(
        "1. **[A paper](https://x.org/1)** — **NEW** · Read\n"
        "- **What overlaps:** it asks your question.\n"
        "- **Do this week:** settle your framing.\n"
        "\n"
        "- An ordinary bullet, which is its own thing.\n",
        _styles(),
    )

    # One entry row (a Table) plus one standalone bullet paragraph — not three
    # bullets and an orphaned title.
    from reportlab.platypus import Table

    tables = [item for item in flow if isinstance(item, Table)]
    assert len(tables) == 1
    rendered = " ".join(
        getattr(item, "text", "") for item in flow if hasattr(item, "text")
    )
    assert "ordinary bullet" in rendered
