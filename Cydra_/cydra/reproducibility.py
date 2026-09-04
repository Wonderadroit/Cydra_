"""Deterministic reproducibility manifests for persisted CYDRA findings."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .causal_reconstruction import reconstruct_causal_chain
from .finding import Finding
from .reasoning_graph import ReasoningGraph


@dataclass(frozen=True)
class ReproducibilityManifest:
    finding_id: str
    audit_session_id: str | None
    evidence_ids: tuple[str, ...]
    impact_evidence_ids: tuple[str, ...]
    hypothesis_id: str
    causal_chain_id: str
    graph_fingerprint: str
    claim_fingerprint: str
    reasoning_node_ids: tuple[str, ...] = ()
    audit_history_fingerprint: str = ""
    schema: str = "cydra.reproducibility.v3"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "finding_id": self.finding_id,
            "audit_session_id": self.audit_session_id,
            "evidence_ids": list(self.evidence_ids),
            "impact_evidence_ids": list(self.impact_evidence_ids),
            "hypothesis_id": self.hypothesis_id,
            "causal_chain_id": self.causal_chain_id,
            "graph_fingerprint": self.graph_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "reasoning_node_ids": list(self.reasoning_node_ids),
            "audit_history_fingerprint": self.audit_history_fingerprint,
        }


def _audit_history_fingerprint(graph: ReasoningGraph) -> str:
    errors = graph.verify_history_integrity()
    if errors:
        raise ValueError(f"reasoning audit history is invalid: {errors[0]}")
    encoded = json.dumps(
        graph.history,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reasoning_node_ids(graph: ReasoningGraph, finding: Finding) -> tuple[str, ...]:
    node_ids = set(finding.evidence_ids) | set(finding.impact.evidence_ids) | {
        finding.finding_id,
        finding.hypothesis_id,
        finding.causal_chain_id,
    }
    if finding.audit_session_id:
        node_ids.add(finding.audit_session_id)

    try:
        trace = reconstruct_causal_chain(graph.model, finding.causal_chain_id)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"causal chain is not reproducible: {exc}") from exc

    node_ids.update({
        trace.chain_id,
        trace.hypothesis_id,
        trace.observation_id,
        trace.outcome_evidence_id,
        trace.verification_id,
        trace.belief_update_id,
    })
    return tuple(sorted(node_ids))


def _canonical_graph_payload(graph: ReasoningGraph, node_ids: tuple[str, ...]) -> dict[str, Any]:
    nodes = []
    node_set = set(node_ids)
    for node_id in node_ids:
        node = graph.model.nodes.get(node_id)
        if node is None:
            raise KeyError(f"reproducibility node missing: {node_id}")
        nodes.append({
            "id": node.node_id,
            "kind": node.kind,
            "label": node.label,
            "attributes": node.attributes,
        })

    edges = [
        {
            "source": edge.source,
            "relation": edge.relation,
            "target": edge.target,
            "attributes": edge.attributes,
        }
        for edge in graph.model.edges
        if edge.source in node_set and edge.target in node_set
    ]
    edges.sort(key=lambda edge: (
        edge["source"],
        edge["relation"],
        edge["target"],
        json.dumps(edge["attributes"], sort_keys=True, default=str),
    ))
    return {"nodes": nodes, "edges": edges}


def _canonical_claim_payload(finding: Finding) -> dict[str, Any]:
    """Return report-facing claims that must remain bound to the manifest."""
    return {
        "finding_id": finding.finding_id,
        "title": finding.title,
        "summary": finding.summary,
        "severity": finding.severity,
        "impact": {
            "level": finding.impact.level.value,
            "asset_at_risk": finding.impact.asset_at_risk,
            "consequence": finding.impact.consequence,
            "prerequisites": list(finding.impact.prerequisites),
            "evidence_ids": list(finding.impact.evidence_ids),
        },
        "affected_components": list(finding.affected_components),
        "evidence_ids": list(finding.evidence_ids),
        "hypothesis_id": finding.hypothesis_id,
        "poc_reference": finding.poc_reference,
        "causal_chain_id": finding.causal_chain_id,
        "audit_session_id": finding.audit_session_id,
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_reproducibility_manifest(
    graph: ReasoningGraph,
    finding: Finding,
) -> ReproducibilityManifest:
    """Build a deterministic manifest from canonical reasoning state and finding claims."""
    if not finding.finding_id.strip():
        raise ValueError("finding ID must not be empty")

    node_ids = _reasoning_node_ids(graph, finding)
    payload = _canonical_graph_payload(graph, node_ids)
    return ReproducibilityManifest(
        finding_id=finding.finding_id,
        audit_session_id=finding.audit_session_id,
        evidence_ids=tuple(finding.evidence_ids),
        impact_evidence_ids=tuple(finding.impact.evidence_ids),
        hypothesis_id=finding.hypothesis_id,
        causal_chain_id=finding.causal_chain_id,
        graph_fingerprint=_fingerprint(payload),
        claim_fingerprint=_fingerprint(_canonical_claim_payload(finding)),
        reasoning_node_ids=node_ids,
        audit_history_fingerprint=_audit_history_fingerprint(graph),
    )


def verify_reproducibility_manifest(
    graph: ReasoningGraph,
    finding: Finding,
    manifest: ReproducibilityManifest,
) -> list[str]:
    """Verify a manifest against canonical state without mutation or execution."""
    errors: list[str] = []
    if manifest.schema != "cydra.reproducibility.v3":
        errors.append("unsupported reproducibility manifest schema")
    if manifest.finding_id != finding.finding_id:
        errors.append("manifest finding identity does not match")
    if manifest.audit_session_id != finding.audit_session_id:
        errors.append("manifest audit-session identity does not match")
    if manifest.evidence_ids != tuple(finding.evidence_ids):
        errors.append("manifest evidence identities do not match")
    if manifest.impact_evidence_ids != tuple(finding.impact.evidence_ids):
        errors.append("manifest impact evidence identities do not match")
    if manifest.hypothesis_id != finding.hypothesis_id:
        errors.append("manifest hypothesis identity does not match")
    if manifest.causal_chain_id != finding.causal_chain_id:
        errors.append("manifest causal-chain identity does not match")

    current_claim_fingerprint = _fingerprint(_canonical_claim_payload(finding))
    if current_claim_fingerprint != manifest.claim_fingerprint:
        errors.append("finding claim fingerprint does not match")

    try:
        current = build_reproducibility_manifest(graph, finding)
    except (KeyError, ValueError) as exc:
        errors.append(f"canonical state cannot be fingerprinted: {exc}")
    else:
        if current.graph_fingerprint != manifest.graph_fingerprint:
            errors.append("canonical graph fingerprint does not match")
        if current.reasoning_node_ids != manifest.reasoning_node_ids:
            errors.append("manifest reasoning-node closure does not match")
        if current.audit_history_fingerprint != manifest.audit_history_fingerprint:
            errors.append("audit history fingerprint does not match")
    return errors
