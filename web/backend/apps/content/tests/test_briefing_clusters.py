"""The report body is organised by research theme, and quiet themes stay quiet."""

from apps.content.briefing import ScopePart
from apps.content.briefing_sections import (
    _cluster_groups,
    generate_report_body,
    theme_blocks,
)
from apps.content.theme_report import ThemeSection


def _item(title, cluster, verdict="read", *, entrant=True):
    return {
        "title": title,
        "cluster_label": cluster,
        "verdict": verdict,
        "lead": f"why {title}",
        "caveat": f"caveat for {title}",
        "url": f"https://x/{title}",
        "is_entrant": entrant,
        "position": 1,
        "bridge_labels": [],
        "source_name": "arxiv",
        "deadline_date": "",
    }


def test_cluster_groups_noop_for_single_cluster() -> None:
    items = [_item("a", "Med"), _item("b", "Med")]
    groups = _cluster_groups(items)
    assert len(groups) == 1
    assert groups[0][0] == ""  # unlabelled single group


def test_cluster_groups_splits_two_clusters_order_preserving() -> None:
    items = [_item("a", "Medical AI"), _item("b", "Ocean"), _item("c", "Medical AI")]
    groups = _cluster_groups(items)
    assert [label for label, _ in groups] == ["Medical AI", "Ocean"]
    assert [i["title"] for i in groups[0][1]] == ["a", "c"]


# --------------------------------------------------------------------------- #
# Theme sections: the document's body
# --------------------------------------------------------------------------- #
def _section(label, entrants=None, standing=None, read="") -> ThemeSection:
    return ThemeSection(
        cluster_id=f"c-{label.lower().replace(' ', '-')}",
        label=label,
        entrants=entrants or {},
        standing=standing or {},
        read=read,
    )


def _part(label: str, kind: str, sections=None, quiet=None) -> ScopePart:
    themes = sections or []
    return ScopePart(
        key=label.lower(),
        label=label,
        kind=kind,
        scope="",
        counts={},
        items={},
        themes=themes,
        quiet=quiet or [],
    )


def test_a_theme_with_news_gets_a_section_led_by_mylos_read() -> None:
    part = _part(
        "Personal",
        "personal",
        [
            _section(
                "Medical AI",
                entrants={"papers": [_item("Segmentation nets", "Medical AI")]},
                read="Two of today's papers converge on the same failure mode.",
            )
        ],
    )

    blocks = theme_blocks(part, ["papers"])

    assert len(blocks) == 1
    assert blocks[0].startswith("## Medical AI")
    # The prose sits next to what it describes, above the list rather than in a
    # separate section that repeats it.
    assert "converge on the same failure mode" in blocks[0]
    assert "### Papers" in blocks[0]
    assert "1. **[Segmentation nets]" in blocks[0]


def test_an_entrant_carries_its_verdict_and_never_a_percentage() -> None:
    part = _part(
        "Personal",
        "personal",
        [_section("Medical AI", entrants={"papers": [_item("Fresh", "Medical AI")]})],
    )

    body = theme_blocks(part, ["papers"])[0]

    assert "**NEW**" in body
    assert "Read" in body
    assert "%" not in body


def test_standing_items_are_reference_rows_with_no_commentary() -> None:
    """The block serves the reader who skipped three days — nothing more."""
    settled = _item("Old but good", "Medical AI", entrant=False)
    part = _part(
        "Personal",
        "personal",
        [
            _section(
                "Medical AI",
                entrants={"papers": [_item("Fresh", "Medical AI")]},
                standing={"papers": [settled]},
            )
        ],
    )

    body = theme_blocks(part, ["papers"])[0]

    assert "Currently in your list" in body
    assert "Old but good" in body
    # No reason, no verdict — the settled half of the document argues nothing.
    assert "why Old but good" not in body


def test_a_theme_with_no_news_produces_no_section() -> None:
    """It is one line in the quiet list, not a heading over a settled list."""
    part = _part(
        "Personal",
        "personal",
        [
            _section(
                "Ocean",
                standing={"papers": [_item("Settled", "Ocean", entrant=False)]},
            )
        ],
        quiet=[("Ocean", 1)],
    )

    assert theme_blocks(part, ["papers"]) == []

    body, _ = generate_report_body("A researcher.", ["papers"], part, [])
    assert "## Ocean" not in body
    assert "Quiet today:" in body
    assert "Ocean (1 standing)" in body


def test_the_lead_paragraph_opens_the_body() -> None:
    part = _part(
        "Personal",
        "personal",
        [_section("Medical AI", entrants={"papers": [_item("A", "Medical AI")]})],
    )

    body, used_llm = generate_report_body(
        "A researcher.",
        ["papers"],
        part,
        [],
        narrative={
            "lead": "Today is about segmentation.",
            "lead_origin": "llm",
            "themes": [
                {
                    "cluster_id": "c-medical-ai",
                    "label": "Medical AI",
                    "read": "A read on the theme.",
                    "origin": "llm",
                }
            ],
        },
    )

    assert used_llm is True
    assert body.startswith("Today is about segmentation.")
    assert body.index("Today is about") < body.index("## Medical AI")
    assert "A read on the theme." in body


def test_a_free_report_is_quieter_not_broken() -> None:
    """No narrative payload: the same sections, the same navigation, no prose."""
    part = _part(
        "Personal",
        "personal",
        [_section("Medical AI", entrants={"papers": [_item("A", "Medical AI")]})],
    )

    body, used_llm = generate_report_body("A researcher.", ["papers"], part, [])

    assert used_llm is False
    assert body.startswith("## Medical AI")
    assert "### Papers" in body
    assert "1. **[A]" in body


def test_each_project_gets_its_own_part_after_the_themes() -> None:
    personal = _part(
        "Personal",
        "personal",
        [_section("Med AI", entrants={"papers": [_item("Mine", "Med AI")]})],
    )
    project = ScopePart(
        key="coral",
        label="Coral Atlas",
        kind="project",
        scope="",
        counts={"grants": 1},
        items={"grants": [_item("Reef award", "Sea")]},
    )

    body, _ = generate_report_body(
        "A researcher.", ["papers", "grants"], personal, [project]
    )

    assert body.index("## Med AI") < body.index("## Project · Coral Atlas")
    project_block = body[body.index("## Project ·") :]
    assert "Reef award" in project_block
    assert "Mine" not in project_block


def test_a_quiet_project_gets_no_section_at_all() -> None:
    """A heading with nothing under it is the crowding this report is ending."""
    personal = _part(
        "Personal",
        "personal",
        [_section("Med AI", entrants={"papers": [_item("Mine", "Med AI")]})],
    )
    quiet_project = ScopePart(
        key="quiet", label="Quiet Project", kind="project", scope="",
        counts={}, items={"papers": []},
    )

    body, _ = generate_report_body(
        "A researcher.", ["papers"], personal, [quiet_project]
    )

    assert "Quiet Project" not in body
