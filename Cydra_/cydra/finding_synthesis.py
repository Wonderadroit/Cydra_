"""Strict reasoning-output to finding materialization boundary.

This module is deliberately a claim-materialization boundary, not a vulnerability
scanner. A reasoning component must explicitly provide the report claims and the
canonical references that support them. Missing or ambiguous graph state is
rejected rather than converted into a finding by heuristic inference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .finding import Finding
from .finding_gate import FindingCandidate
from .impact import ImpactAssessment
from .reasoning_graph import ReasoningGraph


@dataclass(frozen=True)
class ReasoningFindingDraft:
    """Explicit security claim emitted by the reasoning layer.

    The draft contains no benchmark truth. It is only admissible when every
    referenced hypothesis, evidence item, and causal chain already exists in the
    canonical graph. The caller remains responsible for providing the semantic
    claim and impact assessment; this boundary never invents either one.
    """

    finding_id: str
    title: str
    summary: str
    severity: str
    impact: ImpactAssessment
    affected_components: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    hypothesis_id: str
    causal_chain_id: str
    candidate: FindingCandidate
    poc_reference: str | None = None
    audit_session_id: str | None = None

    def to_finding(self, graph: ReasoningGraph) -> Finding:
        """Materialize an explicit draft only against canonical graph state."""
        if not isinstance(graph, ReasoningGraph):
            raise TypeError("finding synthesis requires the canonical ReasoningGraph")
        if not self.finding_id.strip():
            raise ValueError("finding draft ID must not be empty")
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("finding draft title and summary must not be empty")
        if not self.hypothesis_id.strip():
            raise ValueError("finding draft hypothesis must not be empty")
        if not self.causal_chain_id.strip():
            raise ValueError("finding draft causal chain must not be empty")
        if not self.evidence_ids:
            raise ValueError("finding draft requires evidence IDs")
        if not self.affected_components:
            raise ValueError("finding draft requires affected components")

        hypothesis = graph.model.nodes.get(self.hypothesis_id)
        if hypothesis is None or hypothesis.kind != "hypothesis":
            raise ValueError("finding draft hypothesis is not canonical")
        chain = graph.model.nodes.get(self.causal_chain_id)
        if chain is None or chain.kind != "causal_chain":
            raise ValueError("finding draft causal chain is not canonical")
        if chain.attributes.get("audit_session_id") is not None and self.audit_session_id != chain.attributes.get("audit_session_id"):
            raise ValueError("finding draft audit-session provenance does not match causal chain")
        for evidence_id in self.evidence_ids:
            evidence = graph.model.nodes.get(evidence_id)
            if evidence is None or evidence.kind != "evidence":
                raise ValueError(f"finding draft evidence is not canonical: {evidence_id}")

        return Finding(
            finding_id=self.finding_id,
            title=self.title,
            summary=self.summary,
            severity=self.severity,
            impact=self.impact,
            affected_components=self.affected_components,
            evidence_ids=self.evidence_ids,
            hypothesis_id=self.hypothesis_id,
            poc_reference=self.poc_reference,
            causal_chain_id=self.causal_chain_id,
            audit_session_id=self.audit_session_id,
        )


@dataclass(frozen=True)
class SynthesizedFinding:
    """Reasoning output ready for the canonical finding gate."""

    candidate: FindingCandidate
    finding: Finding


def synthesize_reasoning_findings(
    graph: ReasoningGraph,
    drafts: Iterable[ReasoningFindingDraft],
) -> tuple[SynthesizedFinding, ...]:
    """Convert explicit reasoning drafts into canonical gate-ready output.

    No historical oracle, title matching, vulnerability dictionary, or evidence
    inference is performed here. The output still has to pass the normal graph-aware
    finding gate before persistence.
    """
    if not isinstance(graph, ReasoningGraph):
        raise TypeError("finding synthesis requires the canonical ReasoningGraph")
    result: list[SynthesizedFinding] = []
    seen: set[str] = set()
    for draft in drafts:
        if not isinstance(draft, ReasoningFindingDraft):
            raise TypeError("finding synthesis drafts must use the canonical draft type")
        if draft.finding_id in seen:
            raise ValueError(f"duplicate finding draft ID: {draft.finding_id}")
        seen.add(draft.finding_id)
        result.append(SynthesizedFinding(draft.candidate, draft.to_finding(graph)))
    return tuple(result)
