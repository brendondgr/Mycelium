"""The paper briefing section groups its write-up by focus cluster."""

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
    assert "**In your Medical AI focus:**" in body
    assert "**In your Oceanography focus:**" in body
    assert "Paper A" in body and "Paper B" in body


# --------------------------------------------------------------------------- #
# Cluster-first report structure (Phase D)
# --------------------------------------------------------------------------- #
def _item(title: str, cluster: str) -> dict:
    return {
        "title": title,
        "cluster_label": cluster,
        "match_percent": 80,
        "reason": "fits your focus",
        "url": "https://example.org",
    }


def test_the_report_is_organised_by_research_theme() -> None:
    """A researcher thinks in themes, not in paper/grant/conference.

    With every content type now carrying attribution, the report leads with one
    section per theme and puts the categories inside it.
    """
    from apps.content.briefing_sections import generate_report_body

    items = {
        "papers": [_item("Segmentation nets", "Medical AI")],
        "grants": [
            _item("NIH imaging call", "Medical AI"),
            _item("Soft actuator award", "Robotics"),
        ],
    }
    body, _used_llm = generate_report_body(
        "A researcher.",
        ["papers", "grants"],
        {"papers": 1, "grants": 2},
        {},
        items,
        complete=lambda _p: None,  # deterministic path
    )

    assert "## Medical AI" in body
    assert "## Robotics" in body
    # ...and the categories sit *inside* a theme, not above it.
    assert "## Papers" not in body
    # Each item is written under its own theme. (The title also appears in the
    # opening summary, which sits above every section — so look inside the section.)
    medical = body[body.index("## Medical AI") : body.index("## Robotics")]
    assert "Segmentation nets" in medical
    assert "NIH imaging call" in medical
    assert "Soft actuator award" not in medical


def test_a_theme_section_tallies_what_it_brought() -> None:
    from apps.content.briefing_sections import generate_report_body

    items = {
        "papers": [_item("A", "Medical AI"), _item("B", "Medical AI")],
        "grants": [_item("C", "Robotics")],
    }
    body, _ = generate_report_body(
        "A researcher.", ["papers", "grants"], {}, {}, items, complete=lambda _p: None
    )

    assert "2 papers" in body
    assert "1 grant" in body  # singular, not "1 grants"


def test_one_theme_keeps_the_old_category_first_report() -> None:
    """Nobody's report changes shape just because the capability now exists."""
    from apps.content.briefing_sections import generate_report_body

    items = {"papers": [_item("Solo", "Medical AI")]}
    body, _ = generate_report_body(
        "A researcher.", ["papers"], {"papers": 1}, {}, items, complete=lambda _p: None
    )

    assert "## Papers" in body
    assert "## Medical AI" not in body


def test_a_half_attributed_report_stays_category_first() -> None:
    """Better the whole report keeps its old shape than becomes quietly incomplete.

    If some items carry a theme and others do not, organising by theme would strand
    the unattributed ones somewhere the reader cannot account for.
    """
    from apps.content.briefing_sections import generate_report_body

    items = {
        "papers": [_item("Attributed", "Medical AI")],
        "grants": [{"title": "Unattributed", "match_percent": 70}],
    }
    body, _ = generate_report_body(
        "A researcher.", ["papers", "grants"], {}, {}, items, complete=lambda _p: None
    )

    assert "## Medical AI" not in body
    assert "## Papers" in body
