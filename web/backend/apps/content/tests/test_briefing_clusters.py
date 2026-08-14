"""The paper briefing section groups its write-up by focus cluster."""

from apps.content.briefing import ScopePart
from apps.content.briefing_sections import _cluster_groups, write_section


def _item(title, cluster, match=80):
    return {"title": title, "cluster_label": cluster, "match_percent": match,
            "reason": f"why {title}", "url": f"https://x/{title}"}


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


def test_section_fallback_groups_by_cluster() -> None:
    items = [_item("Paper A", "Medical AI"), _item("Paper B", "Oceanography")]
    # complete=lambda -> None forces the deterministic fallback path.
    body, from_llm = write_section(
        "papers", "profile", items, complete=lambda _s, _p: None
    )
    assert from_llm is False
    # A theme is a heading carrying the theme's own name — nothing else on the line.
    # "**In your Medical AI focus:**" was a sentence, and a sentence in heading
    # position reads as prose the reader skims past however it is styled.
    assert "#### Medical AI" in body
    assert "#### Oceanography" in body
    assert "In your" not in body
    assert "Paper A" in body and "Paper B" in body


def test_section_fallback_numbers_its_items_across_clusters() -> None:
    """The list is a ranking, so it is numbered — and the ranks do not restart."""
    items = [
        _item("Paper A", "Medical AI"),
        _item("Paper B", "Medical AI"),
        _item("Paper C", "Oceanography"),
    ]
    body, _ = write_section("papers", "profile", items, complete=lambda _s, _p: None)
    assert "1. **[Paper A]" in body
    assert "2. **[Paper B]" in body
    assert "3. **[Paper C]" in body


def test_a_new_item_carries_the_marker_and_its_match() -> None:
    """The two facts a reader scans a ranked list for sit on the title line."""
    entrant = _item("Fresh", "Medical AI", match=91) | {"is_entrant": True}
    body, _ = write_section(
        "papers", "profile", [entrant], complete=lambda _s, _p: None
    )
    assert "**NEW**" in body
    assert "91% match" in body


# --------------------------------------------------------------------------- #
# Report structure: Personal first, then a part per project. Themes live *inside*
# a category section (above), which is the level where naming a theme helps —
# organising the whole report by theme instead put the reader's own matches and
# their projects' matches in the same bucket, which is what this replaces.
# --------------------------------------------------------------------------- #
def _themed(title: str, cluster: str) -> dict:
    return {
        "title": title,
        "cluster_label": cluster,
        "match_percent": 80,
        "reason": "fits your focus",
        "url": "https://example.org",
    }


def _part(label: str, kind: str, items: dict) -> ScopePart:
    return ScopePart(
        key=label.lower(),
        label=label,
        kind=kind,
        scope="",
        counts={c: len(v) for c, v in items.items()},
        items=items,
    )


def test_the_report_leads_with_the_readers_own_part() -> None:
    from apps.content.briefing_sections import generate_report_body

    personal = _part(
        "Personal",
        "personal",
        {
            "papers": [_themed("Segmentation nets", "Medical AI")],
            "grants": [_themed("NIH imaging call", "Medical AI")],
        },
    )
    body, _used_llm = generate_report_body(
        "A researcher.",
        ["papers", "grants"],
        personal,
        [],
        complete=lambda _s, _p: None,  # deterministic path
    )

    assert "## Personal" in body
    assert "### Papers" in body
    assert "### Grants" in body
    assert "Segmentation nets" in body


def test_each_project_gets_its_own_part_after_the_personal_one() -> None:
    from apps.content.briefing_sections import generate_report_body

    personal = _part("Personal", "personal", {"papers": [_themed("Mine", "Med AI")]})
    reef = {"grants": [_themed("Reef award", "Sea")]}
    project = _part("Coral Atlas", "project", reef)

    body, _ = generate_report_body(
        "A researcher.",
        ["papers", "grants"],
        personal,
        [project],
        complete=lambda _s, _p: None,
    )

    assert body.index("## Personal") < body.index("## Project · Coral Atlas")
    # A project's items are written under that project, not folded into Personal.
    personal_block = body[body.index("## Personal") : body.index("## Project ·")]
    assert "Mine" in personal_block
    assert "Reef award" not in personal_block


def test_a_project_part_is_shaped_like_the_readers_own() -> None:
    """Same category headings, same numbered items — and no tally sentence.

    The counts are the summary table's whole job. Restating them in prose above a
    list that already shows them item by item put noise between a heading and the
    thing it was heading, which is what made project sections read as unstructured.
    """
    from apps.content.briefing_sections import generate_report_body

    project = _part(
        "Coral Atlas",
        "project",
        {
            "papers": [_themed("A", "Ocean"), _themed("B", "Ocean")],
            "grants": [_themed("C", "Ocean")],
        },
    )
    body, _ = generate_report_body(
        "A researcher.",
        ["papers", "grants"],
        _part("Personal", "personal", {}),
        [project],
        complete=lambda _s, _p: None,
    )

    assert "## Project · Coral Atlas" in body
    assert "### Papers" in body and "### Grants" in body
    assert "1. **[A]" in body and "2. **[B]" in body
    assert "2 papers" not in body


def test_a_quiet_project_gets_no_section_at_all() -> None:
    """A heading with nothing under it is the crowding this report is ending.

    The project keeps its row in the summary table — that is where "nothing today"
    belongs — but the body stays about what actually arrived.
    """
    from apps.content.briefing_sections import generate_report_body

    body, _ = generate_report_body(
        "A researcher.",
        ["papers"],
        _part("Personal", "personal", {"papers": [_themed("Mine", "Medical AI")]}),
        [_part("Quiet Project", "project", {"papers": []})],
        complete=lambda _s, _p: None,
    )

    assert "Quiet Project" not in body
