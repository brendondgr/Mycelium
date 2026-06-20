"""Built-in source cards for Mycelium's lab knowledge graphs.

These mirror the Month-3 cross-entity graph direction in ``docs/goals.md``:
a lab/people/projects graph, an evidence graph over claims and findings, and
an opportunity graph over grants and fellowships. They share canonical join
keys (``paper-doi``, ``topic-id``) so the planner can reason about real
cross-source joins. Swap these for introspected production cards later; the
planner only depends on the :class:`~apps.planner.cards.SourceCard` shape.
"""

from __future__ import annotations

from .cards import (
    CardRegistry,
    EdgePattern,
    JoinKey,
    ProbeExpectations,
    SafetyLimits,
    SourceCard,
)

LAB_GRAPH = SourceCard(
    name="lab_graph",
    title="Lab Knowledge Graph",
    description=(
        "People, projects, papers, and topics for a research lab and how they "
        "connect. Use for questions about who works on what, project ownership, "
        "authorship, and member interests."
    ),
    node_labels=frozenset(
        {"Lab", "Person", "Project", "Paper", "Topic", "ResearchArea"}
    ),
    relationship_types=frozenset(
        {"MEMBER_OF", "BELONGS_TO", "WORKS_ON", "AUTHORED_BY", "INTERESTED_IN", "ABOUT"}
    ),
    allowed_edge_patterns=(
        EdgePattern("Person", "MEMBER_OF", "Lab"),
        EdgePattern("Project", "BELONGS_TO", "Lab"),
        EdgePattern("Person", "WORKS_ON", "Project"),
        EdgePattern("Paper", "AUTHORED_BY", "Person"),
        EdgePattern("Person", "INTERESTED_IN", "Topic"),
        EdgePattern("Paper", "ABOUT", "Topic"),
        EdgePattern("Project", "ABOUT", "ResearchArea"),
    ),
    safety=SafetyLimits(max_traversal_depth=4, max_result_rows=200),
    probe=ProbeExpectations(
        expected_labels=frozenset({"Lab", "Person", "Project", "Paper"}),
        min_node_count=10,
    ),
    join_keys=(
        JoinKey("paper-doi", "Paper", "doi", canonical_form="lowercased DOI"),
        JoinKey("topic-id", "Topic", "slug", canonical_form="kebab-case slug"),
        JoinKey("person-orcid", "Person", "orcid", canonical_form="ORCID iD"),
    ),
    entity_descriptions={
        "Person": "A lab member: PI, student, postdoc, or staff.",
        "Project": "An active research project owned by the lab.",
        "Paper": "A publication authored by lab members.",
        "Topic": "A research topic that papers and people relate to.",
        "AUTHORED_BY": "Links a paper to the people who wrote it.",
    },
)

EVIDENCE_GRAPH = SourceCard(
    name="evidence_graph",
    title="Evidence & Claims Graph",
    description=(
        "Claims, findings, methods, and datasets extracted from papers, with "
        "support and contradiction edges. Use for questions about what is "
        "supported, challenged, or uncertain, and which evidence backs a claim."
    ),
    node_labels=frozenset(
        {"Paper", "Claim", "Finding", "Method", "Dataset", "Topic"}
    ),
    relationship_types=frozenset(
        {"REPORTS", "SUPPORTS", "CONTRADICTS", "USES", "ABOUT", "DERIVED_FROM"}
    ),
    allowed_edge_patterns=(
        EdgePattern("Paper", "REPORTS", "Finding"),
        EdgePattern("Finding", "SUPPORTS", "Claim"),
        EdgePattern("Finding", "CONTRADICTS", "Claim"),
        EdgePattern("Paper", "USES", "Method"),
        EdgePattern("Paper", "USES", "Dataset"),
        EdgePattern("Claim", "ABOUT", "Topic"),
        EdgePattern("Finding", "DERIVED_FROM", "Dataset"),
    ),
    safety=SafetyLimits(max_traversal_depth=5, max_result_rows=300),
    probe=ProbeExpectations(
        expected_labels=frozenset({"Paper", "Claim", "Finding"}),
        min_node_count=10,
    ),
    join_keys=(
        JoinKey("paper-doi", "Paper", "doi", canonical_form="lowercased DOI"),
        JoinKey("topic-id", "Topic", "slug", canonical_form="kebab-case slug"),
    ),
    entity_descriptions={
        "Claim": "An assertion a paper makes that evidence can support or refute.",
        "Finding": "A specific result reported by a paper.",
        "SUPPORTS": "A finding that backs a claim.",
        "CONTRADICTS": "A finding that challenges a claim.",
    },
)

OPPORTUNITY_GRAPH = SourceCard(
    name="opportunity_graph",
    title="Funding Opportunity Graph",
    description=(
        "Grants and fellowships, their funding agencies, eligibility rules, "
        "deadlines, and topics. Use for questions about funding fit, eligibility, "
        "and deadlines for the lab and its members."
    ),
    node_labels=frozenset(
        {"Grant", "Fellowship", "Agency", "Topic", "EligibilityRule", "Deadline"}
    ),
    relationship_types=frozenset(
        {"OFFERED_BY", "ABOUT", "REQUIRES", "HAS_DEADLINE"}
    ),
    allowed_edge_patterns=(
        EdgePattern("Grant", "OFFERED_BY", "Agency"),
        EdgePattern("Fellowship", "OFFERED_BY", "Agency"),
        EdgePattern("Grant", "ABOUT", "Topic"),
        EdgePattern("Fellowship", "ABOUT", "Topic"),
        EdgePattern("Grant", "REQUIRES", "EligibilityRule"),
        EdgePattern("Fellowship", "REQUIRES", "EligibilityRule"),
        EdgePattern("Grant", "HAS_DEADLINE", "Deadline"),
        EdgePattern("Fellowship", "HAS_DEADLINE", "Deadline"),
    ),
    safety=SafetyLimits(max_traversal_depth=3, max_result_rows=150),
    probe=ProbeExpectations(
        expected_labels=frozenset({"Grant", "Fellowship", "Topic"}),
        min_node_count=5,
    ),
    join_keys=(
        JoinKey("topic-id", "Topic", "slug", canonical_form="kebab-case slug"),
    ),
    entity_descriptions={
        "Grant": "A funding opportunity a lab can apply for.",
        "Fellowship": "A funding opportunity for an individual member.",
        "EligibilityRule": "A constraint that gates who may apply.",
        "Deadline": "A submission deadline for an opportunity.",
    },
)

MYCELIUM_CARDS: tuple[SourceCard, ...] = (
    LAB_GRAPH,
    EVIDENCE_GRAPH,
    OPPORTUNITY_GRAPH,
)


def default_registry() -> CardRegistry:
    """A registry of the built-in Mycelium source cards."""

    return CardRegistry(MYCELIUM_CARDS)
