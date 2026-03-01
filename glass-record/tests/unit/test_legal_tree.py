import pytest

from agents.legal_tree.schemas import LegalNode, LegalTree, NodeStrength


def test_legal_node_schema_valid():
    node = LegalNode(
        node_id="n1",
        node_type="ALLEGATION",
        title="Veto blocks humanitarian aid",
        description="The Security Council veto was used to block a resolution requiring safe passage.",
        strength=NodeStrength.MODERATE,
        evidence_ids=["abc123"],
        statutes=["UN Charter Art. 27"],
        children=[],
    )
    assert node.node_id == "n1"
    assert node.strength == NodeStrength.MODERATE


def test_legal_tree_serialises_to_dict():
    node = LegalNode(
        node_id="n1",
        node_type="ALLEGATION",
        title="Test allegation",
        description="Test description.",
        strength=NodeStrength.WEAK,
    )
    tree = LegalTree(
        tree_id="tree-001",
        journalist_id="j-001",
        cycle_id="cycle-001",
        story_title="Test story",
        summary="A test legal case.",
        overall_strength=NodeStrength.WEAK,
        root_nodes=[node],
        caveats=["Limited sources available."],
    )
    d = tree.model_dump()
    assert d["overall_strength"] == "weak"
    assert len(d["root_nodes"]) == 1
    assert d["root_nodes"][0]["node_type"] == "ALLEGATION"


def test_legal_node_nested_children():
    child = LegalNode(
        node_id="n1.1",
        node_type="EVIDENCE",
        title="Security Council minutes",
        description="Official minutes showing veto cast by P5 member.",
        strength=NodeStrength.STRONG,
        evidence_ids=["def456"],
    )
    parent = LegalNode(
        node_id="n1",
        node_type="ALLEGATION",
        title="Veto abuse",
        description="Use of veto to block humanitarian access.",
        strength=NodeStrength.MODERATE,
        children=[child],
    )
    assert len(parent.children) == 1
    assert parent.children[0].node_id == "n1.1"
