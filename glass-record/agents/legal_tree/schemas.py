"""Pydantic schemas for the legal case tree."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeStrength(str, Enum):
    STRONG = "strong"       # well-supported by multiple credible sources
    MODERATE = "moderate"   # supported but gaps remain
    WEAK = "weak"           # single source or low credibility
    CONTESTED = "contested" # contradicted by other evidence


class LegalNode(BaseModel):
    """A single node in the legal case tree."""
    node_id: str = Field(description="Unique identifier, e.g. 'n1', 'n1.1'")
    node_type: str = Field(
        description="One of: ALLEGATION, LEGAL_BASIS, PRECEDENT, EVIDENCE, OBLIGATION, VIOLATION, REMEDY"
    )
    title: str = Field(description="Short label for this node (max 10 words)")
    description: str = Field(description="One to three sentence explanation")
    strength: NodeStrength
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs from the evidence locker that support this node",
    )
    statutes: list[str] = Field(
        default_factory=list,
        description="Relevant statutes, treaties, or resolutions (e.g. 'ICCPR Art. 6')",
    )
    children: list[LegalNode] = Field(
        default_factory=list,
        description="Sub-nodes that branch from this node",
    )


class LegalTree(BaseModel):
    """The complete legal case tree for one investigation cycle."""
    tree_id: str
    journalist_id: str
    cycle_id: str
    story_title: str
    summary: str = Field(description="Two to three sentence overview of the legal case")
    overall_strength: NodeStrength
    root_nodes: list[LegalNode] = Field(description="Top-level allegations or legal questions")
    caveats: list[str] = Field(
        default_factory=list,
        description="Limitations, missing evidence, or areas requiring further investigation",
    )


# Allow self-referential model
LegalNode.model_rebuild()
