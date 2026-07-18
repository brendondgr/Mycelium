"""The paper briefing section groups its write-up by focus cluster."""

from apps.content.briefing_agents import _cluster_groups, write_section


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
