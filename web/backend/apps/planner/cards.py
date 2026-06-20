"""Source cards: the planner's ground truth about each graph source.

A card describes one graph backend. The planner routes only over the
*introspected* fields (``node_labels``, ``relationship_types``,
``allowed_edge_patterns``); ``entity_descriptions`` is human context, never
routing truth (briefing 1.1). Cross-source joins are allowed only on a
declared, canonical join key present in every joined card (briefing 1.2).
Every card carries a safety block that bounds traversal (briefing 3.5) and
content-probe expectations used to confirm the graph is really loaded
(briefing 2.2).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SafetyLimits:
    """Per-source ceilings every sub-question against this source must respect."""

    max_traversal_depth: int
    max_result_rows: int

    def __post_init__(self) -> None:
        if self.max_traversal_depth < 1:
            raise ValueError("max_traversal_depth must be >= 1")
        if self.max_result_rows < 1:
            raise ValueError("max_result_rows must be >= 1")


@dataclass(frozen=True)
class EdgePattern:
    """A directed, label-typed edge the graph actually supports."""

    start_label: str
    relationship_type: str
    end_label: str

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.start_label, self.relationship_type, self.end_label)


@dataclass(frozen=True)
class JoinKey:
    """A declared, canonical bridge identifier.

    A join is only legal across sources that each declare a join key with the
    same ``name`` (the canonical bridge). ``canonical_form`` documents the
    normalized form so two catalogs that store the same id differently still
    bind. The planner never invents a join key (briefing 1.2).
    """

    name: str
    node_label: str
    property: str
    canonical_form: str = ""


@dataclass(frozen=True)
class ProbeExpectations:
    """What a content probe must observe to call this source live (briefing 2.2)."""

    expected_labels: frozenset[str]
    min_node_count: int = 1

    def __post_init__(self) -> None:
        if not self.expected_labels:
            raise ValueError("probe expectations need at least one expected label")
        if self.min_node_count < 1:
            raise ValueError("min_node_count must be >= 1")


@dataclass(frozen=True)
class SourceCard:
    """Everything the planner knows about a single graph source."""

    name: str
    title: str
    description: str
    node_labels: frozenset[str]
    relationship_types: frozenset[str]
    allowed_edge_patterns: tuple[EdgePattern, ...]
    safety: SafetyLimits
    probe: ProbeExpectations
    join_keys: tuple[JoinKey, ...] = ()
    entity_descriptions: Mapping[str, str] = field(default_factory=dict)

    # -- routing-truth lookups -------------------------------------------------

    def has_entity(self, entity: str) -> bool:
        """True if ``entity`` is a known node label or relationship type."""

        return entity in self.node_labels or entity in self.relationship_types

    def allows_edge(self, start: str, rel: str, end: str) -> bool:
        return EdgePattern(start, rel, end) in self.allowed_edge_patterns

    def join_key(self, name: str) -> JoinKey | None:
        for key in self.join_keys:
            if key.name == name:
                return key
        return None

    def join_key_names(self) -> frozenset[str]:
        return frozenset(key.name for key in self.join_keys)

    # -- serialization ---------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SourceCard:
        return cls(
            name=str(data["name"]),
            title=str(data.get("title", data["name"])),
            description=str(data.get("description", "")),
            node_labels=frozenset(data.get("node_labels", [])),  # type: ignore[arg-type]
            relationship_types=frozenset(data.get("relationship_types", [])),  # type: ignore[arg-type]
            allowed_edge_patterns=tuple(
                EdgePattern(*pattern)
                for pattern in data.get("allowed_edge_patterns", [])  # type: ignore[union-attr]
            ),
            safety=SafetyLimits(**data["safety"]),  # type: ignore[arg-type]
            probe=ProbeExpectations(
                expected_labels=frozenset(
                    data["probe"]["expected_labels"]  # type: ignore[index]
                ),
                min_node_count=int(
                    data["probe"].get("min_node_count", 1)  # type: ignore[union-attr]
                ),
            ),
            join_keys=tuple(
                JoinKey(**key) for key in data.get("join_keys", [])  # type: ignore[arg-type]
            ),
            entity_descriptions=dict(data.get("entity_descriptions", {})),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "node_labels": sorted(self.node_labels),
            "relationship_types": sorted(self.relationship_types),
            "allowed_edge_patterns": [
                list(pattern.as_tuple()) for pattern in self.allowed_edge_patterns
            ],
            "safety": {
                "max_traversal_depth": self.safety.max_traversal_depth,
                "max_result_rows": self.safety.max_result_rows,
            },
            "probe": {
                "expected_labels": sorted(self.probe.expected_labels),
                "min_node_count": self.probe.min_node_count,
            },
            "join_keys": [
                {
                    "name": key.name,
                    "node_label": key.node_label,
                    "property": key.property,
                    "canonical_form": key.canonical_form,
                }
                for key in self.join_keys
            ],
            "entity_descriptions": dict(self.entity_descriptions),
        }


def validate_card_consistency(card: SourceCard) -> list[str]:
    """Return human-readable issues where a card's prose drifts from its graph.

    Card drift is the root cause behind briefing 1.1: hand-authored fields must
    not reference structure the introspected fields do not contain. An empty
    list means the card is internally consistent. The self-eval gate re-checks
    these invariants before trusting the card for routing.
    """

    issues: list[str] = []

    for pattern in card.allowed_edge_patterns:
        if pattern.start_label not in card.node_labels:
            issues.append(
                f"edge pattern start label '{pattern.start_label}' is not in "
                f"node_labels"
            )
        if pattern.end_label not in card.node_labels:
            issues.append(
                f"edge pattern end label '{pattern.end_label}' is not in node_labels"
            )
        if pattern.relationship_type not in card.relationship_types:
            issues.append(
                f"edge pattern relationship '{pattern.relationship_type}' is not in "
                f"relationship_types"
            )

    for key in card.join_keys:
        if key.node_label not in card.node_labels:
            issues.append(
                f"join key '{key.name}' binds unknown node label '{key.node_label}'"
            )

    for label in card.probe.expected_labels:
        if label not in card.node_labels:
            issues.append(
                f"probe expects label '{label}' which is not in node_labels"
            )

    known = card.node_labels | card.relationship_types
    for described in card.entity_descriptions:
        if described not in known:
            issues.append(
                f"entity_descriptions references unknown entity '{described}'"
            )

    return issues


class CardRegistry:
    """An indexed, consistency-checked collection of source cards."""

    def __init__(self, cards: Iterable[SourceCard]):
        self._cards: dict[str, SourceCard] = {}
        for card in cards:
            if card.name in self._cards:
                raise ValueError(f"duplicate source card '{card.name}'")
            self._cards[card.name] = card

    def __contains__(self, name: object) -> bool:
        return name in self._cards

    def __iter__(self):
        return iter(self._cards.values())

    def __len__(self) -> int:
        return len(self._cards)

    def names(self) -> frozenset[str]:
        return frozenset(self._cards)

    def get(self, name: str) -> SourceCard | None:
        return self._cards.get(name)

    def require(self, name: str) -> SourceCard:
        card = self._cards.get(name)
        if card is None:
            raise KeyError(f"unknown source card '{name}'")
        return card

    def validate(self) -> dict[str, list[str]]:
        """Map of source name -> consistency issues; empty values are consistent."""

        return {name: validate_card_consistency(card) for name, card in
                self._cards.items()}

    def sources_with_join_key(self, name: str) -> frozenset[str]:
        """Names of sources that declare a canonical join key called ``name``."""

        return frozenset(
            source for source, card in self._cards.items()
            if card.join_key(name) is not None
        )

    def supports_cross_source_join(
        self, key_name: str, sources: Iterable[str]
    ) -> bool:
        """True if ``key_name`` is declared on every named source (briefing 1.2)."""

        targets = list(sources)
        if not targets:
            return False
        declaring = self.sources_with_join_key(key_name)
        return all(source in declaring for source in targets)
