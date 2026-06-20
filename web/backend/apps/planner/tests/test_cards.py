"""Tests for source cards: routing-truth lookups, consistency, join keys."""

import pytest

from apps.planner.cards import (
    CardRegistry,
    EdgePattern,
    JoinKey,
    ProbeExpectations,
    SafetyLimits,
    SourceCard,
    validate_card_consistency,
)
from apps.planner.fixtures import default_registry


def test_default_registry_has_three_sources():
    registry = default_registry()

    assert len(registry) == 3
    assert registry.names() == {"lab_graph", "evidence_graph", "opportunity_graph"}


def test_builtin_cards_are_internally_consistent():
    registry = default_registry()

    issues = registry.validate()

    assert issues == {
        "lab_graph": [],
        "evidence_graph": [],
        "opportunity_graph": [],
    }


def test_has_entity_uses_introspected_fields_only():
    card = default_registry().require("lab_graph")

    assert card.has_entity("Paper")  # node label
    assert card.has_entity("AUTHORED_BY")  # relationship type
    assert not card.has_entity("Grant")  # belongs to another source
    assert not card.has_entity("nonsense")


def test_allows_edge_matches_declared_patterns():
    card = default_registry().require("lab_graph")

    assert card.allows_edge("Paper", "AUTHORED_BY", "Person")
    assert not card.allows_edge("Person", "AUTHORED_BY", "Paper")  # wrong direction
    assert not card.allows_edge("Paper", "SUPPORTS", "Claim")  # not in this source


def test_cross_source_join_keys():
    registry = default_registry()

    # topic-id bridges all three graphs.
    assert registry.sources_with_join_key("topic-id") == {
        "lab_graph",
        "evidence_graph",
        "opportunity_graph",
    }
    assert registry.supports_cross_source_join(
        "topic-id", ["lab_graph", "opportunity_graph"]
    )

    # paper-doi bridges lab + evidence only, not opportunity.
    assert registry.sources_with_join_key("paper-doi") == {
        "lab_graph",
        "evidence_graph",
    }
    assert registry.supports_cross_source_join(
        "paper-doi", ["lab_graph", "evidence_graph"]
    )
    assert not registry.supports_cross_source_join(
        "paper-doi", ["lab_graph", "opportunity_graph"]
    )

    # An undeclared key never supports a join.
    assert not registry.supports_cross_source_join("made-up-key", ["lab_graph"])
    assert not registry.supports_cross_source_join("topic-id", [])


def test_validate_card_consistency_flags_drift():
    drifted = SourceCard(
        name="drifted",
        title="Drifted",
        description="prose that disagrees with structure",
        node_labels=frozenset({"Paper"}),
        relationship_types=frozenset({"ABOUT"}),
        allowed_edge_patterns=(
            # Topic is not in node_labels; CITES is not a relationship type.
            EdgePattern("Paper", "CITES", "Topic"),
        ),
        safety=SafetyLimits(max_traversal_depth=2, max_result_rows=10),
        probe=ProbeExpectations(expected_labels=frozenset({"Author"})),
        join_keys=(JoinKey("k", "Venue", "name"),),
        entity_descriptions={"Ghost": "not a real entity"},
    )

    issues = validate_card_consistency(drifted)

    joined = " | ".join(issues)
    assert "end label 'Topic'" in joined
    assert "relationship 'CITES'" in joined
    assert "node label 'Venue'" in joined
    assert "probe expects label 'Author'" in joined
    assert "unknown entity 'Ghost'" in joined


def test_card_dict_round_trip():
    original = default_registry().require("evidence_graph")

    restored = SourceCard.from_dict(original.to_dict())

    assert restored == original


def test_duplicate_card_name_rejected():
    card = default_registry().require("lab_graph")

    with pytest.raises(ValueError, match="duplicate source card"):
        CardRegistry([card, card])


def test_safety_and_probe_reject_bad_values():
    with pytest.raises(ValueError):
        SafetyLimits(max_traversal_depth=0, max_result_rows=10)
    with pytest.raises(ValueError):
        SafetyLimits(max_traversal_depth=2, max_result_rows=0)
    with pytest.raises(ValueError):
        ProbeExpectations(expected_labels=frozenset())
    with pytest.raises(ValueError):
        ProbeExpectations(expected_labels=frozenset({"X"}), min_node_count=0)


def test_require_unknown_source_raises():
    with pytest.raises(KeyError, match="unknown source card"):
        default_registry().require("ghost_graph")
