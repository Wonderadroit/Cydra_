"""Persistence boundary for canonical CYDRA findings."""
from __future__ import annotations

import hashlib
import json

from .audit_session import RepositoryAuditSession
from .causal_reconstruction import reconstruct_causal_chain
from .finding import Finding
from .graph_semantics import validate_graph
from .reasoning_graph import ReasoningGraph
from .security_reasoning import (
    SecurityClaimProposal,
    VerifiedSecurityClaim,
    verified_security_claim_fingerprint,
)
from .system_model import Edge, Node, SystemModel


def _finding_fingerprint(finding: Finding) -> str:
    payload = finding.as_report_data()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verified_claim_from_node(claim_node: Node) -> VerifiedSecurityClaim:
    observation_id = claim_node.attributes.get("observation_id")
    if not isinstance(observation_id, str) or not observation_id.startswith("observation:"):
        raise ValueError("security claim observation reference is invalid")
    hypothesis_id = claim_node.attributes.get("hypothesis_id")
    causal_chain_id = claim_node.attributes.get("causal_chain_id")
    evidence_ids = claim_node.attributes.get("evidence_ids")
    claim_payload = claim_node.attributes.get("claim")
    if not isinstance(hypothesis_id, str) or not isinstance(causal_chain_id, str):
        raise ValueError("security claim canonical references are invalid")
    if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
        raise ValueError("security claim evidence references are invalid")
    if not isinstance(claim_payload, dict):
        raise ValueError("security claim payload is invalid")
    return VerifiedSecurityClaim(
        SecurityClaimProposal(hypothesis_id, observation_id.removeprefix("observation:"), claim_payload),
        causal_chain_id,
        tuple(evidence_ids),
    )


def persist_finding(graph: ReasoningGraph, finding: Finding) -> str:
    """Persist a finding only after validating its canonical reasoning references."""
    if not finding.finding_id.strip():
        raise ValueError("finding ID must not be empty")
    if finding.finding_id in graph.model.nodes:
        raise ValueError(f"finding already exists: {finding.finding_id}")

    hypothesis = graph.model.nodes.get(finding.hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        raise KeyError(f"finding hypothesis missing: {finding.hypothesis_id}")
    if not finding.evidence_ids:
        raise ValueError("finding requires canonical evidence IDs")
    if not finding.causal_chain_id:
        raise ValueError("finding requires a causal-chain reference")

    security_claim_id = None
    security_claim_fingerprint = None
    if hypothesis.attributes.get("security_claim") is not None:
        security_claim_id = f"security_claim:{finding.hypothesis_id}"
        claim_node = graph.model.nodes.get(security_claim_id)
        if claim_node is None or claim_node.kind != "security_claim":
            raise ValueError("security finding requires a persisted verified security claim")
        if claim_node.attributes.get("verified") is not True:
            raise ValueError("security claim is not canonically verified")
        if claim_node.attributes.get("hypothesis_id") != finding.hypothesis_id:
            raise ValueError("security claim hypothesis does not match finding hypothesis")
        if claim_node.attributes.get("causal_chain_id") != finding.causal_chain_id:
            raise ValueError("security claim causal chain does not match finding causal chain")
        canonical_claim = _verified_claim_from_node(claim_node)
        claim_payload = canonical_claim.proposal.claim
        if claim_payload != hypothesis.attributes.get("security_claim"):
            raise ValueError("security claim payload does not match canonical hypothesis metadata")
        if claim_payload.get("claim_kind", "finding") == "finding":
                    expected_prerequisites = claim_payload.get("prerequisites", ())
                    expected_impact_evidence = claim_payload.get("impact_evidence_ids", claim_payload.get("evidence_ids", ()))
                    expected_poc = claim_payload.get("poc_reference") if isinstance(claim_payload.get("poc_reference"), str) else None
                    expected_session = claim_payload.get("audit_session_id") if isinstance(claim_payload.get("audit_session_id"), str) else None
                    if finding.finding_id != claim_payload.get("finding_id"):
                        raise ValueError("finding ID does not match verified security claim")
                    if finding.title != claim_payload.get("title"):
                        raise ValueError("finding title does not match verified security claim")
                    if finding.summary != claim_payload.get("summary"):
                        raise ValueError("finding summary does not match verified security claim")
                    if finding.severity != str(claim_payload.get("severity", "")).upper():
                        raise ValueError("finding severity does not match verified security claim")
                    if finding.affected_components != tuple(claim_payload.get("affected_components", ())):
                        raise ValueError("finding affected components do not match verified security claim")
                    if finding.evidence_ids != tuple(claim_payload.get("evidence_ids", ())):
                        raise ValueError("finding evidence does not match verified security claim")
                    if finding.impact.asset_at_risk != claim_payload.get("asset_at_risk"):
                        raise ValueError("finding impact asset does not match verified security claim")
                    if finding.impact.consequence != claim_payload.get("consequence"):
                        raise ValueError("finding impact consequence does not match verified security claim")
                    if finding.impact.prerequisites != tuple(expected_prerequisites):
                        raise ValueError("finding impact prerequisites do not match verified security claim")
                    if finding.impact.evidence_ids != tuple(expected_impact_evidence):
                        raise ValueError("finding impact evidence does not match verified security claim")
                    if finding.poc_reference != expected_poc:
                        raise ValueError("finding PoC reference does not match verified security claim")
                    if finding.audit_session_id != expected_session:
                        raise ValueError("finding audit-session reference does not match verified security claim")
        security_claim_fingerprint = verified_security_claim_fingerprint(canonical_claim)
        if claim_node.attributes.get("claim_fingerprint") != security_claim_fingerprint:
            raise ValueError("security claim fingerprint does not match canonical claim payload")

    for evidence_id in finding.evidence_ids:
        node = graph.model.nodes.get(evidence_id)
        if node is None or node.kind != "evidence":
            raise KeyError(f"finding evidence missing: {evidence_id}")

    audit_session_nodes = [node for node in graph.model.nodes.values() if node.kind == "audit_session"]
    if audit_session_nodes:
        if not finding.audit_session_id:
            raise ValueError("finding requires audit-session provenance")
        session = graph.model.nodes.get(finding.audit_session_id)
        if session is None or session.kind != "audit_session":
            raise KeyError(f"finding audit session missing: {finding.audit_session_id}")
        provenance_errors = RepositoryAuditSession.validate_persisted_provenance(
            graph.model, finding.audit_session_id
        )
        if provenance_errors:
            raise ValueError("audit-session provenance is invalid")

    trace = reconstruct_causal_chain(graph.model, finding.causal_chain_id)
    if trace.hypothesis_id != finding.hypothesis_id:
        raise ValueError("causal chain hypothesis does not match finding hypothesis")
    if finding.audit_session_id is not None and trace.audit_session_id != finding.audit_session_id:
        raise ValueError("causal chain audit-session provenance does not match finding")
    trace_evidence = set(trace.evidence_ids)
    finding_evidence = set(finding.evidence_ids)
    if not finding_evidence.issubset(trace_evidence):
        raise ValueError("finding evidence must be grounded in the causal trace")

    claim_errors = finding.claim_validation_errors(trace_evidence)
    if claim_errors:
        raise ValueError(claim_errors[0])

    for evidence_id in finding.evidence_ids:
        if not any(
            edge.source == evidence_id
            and edge.relation == "supports"
            and edge.target == finding.hypothesis_id
            for edge in graph.model.edges
        ):
            raise ValueError(
                f"finding evidence does not explicitly support the finding hypothesis: {evidence_id}"
            )

    for evidence_id in finding.impact.evidence_ids:
        node = graph.model.nodes.get(evidence_id)
        if node is None or node.kind != "evidence":
            raise KeyError(f"finding impact evidence missing: {evidence_id}")
        if not any(
            edge.source == evidence_id
            and edge.relation == "supports"
            and edge.target == finding.hypothesis_id
            for edge in graph.model.edges
        ):
            raise ValueError(
                f"finding impact evidence does not explicitly support the finding hypothesis: {evidence_id}"
            )

    graph_errors = validate_graph(graph.model)
    if graph_errors:
        raise ValueError(f"canonical graph is invalid: {graph_errors[0]}")
    audit_errors = graph.verify_history_integrity()
    if audit_errors:
        raise ValueError("reasoning audit history is invalid")

    attributes = finding.as_report_data()
    attributes["persisted"] = True
    attributes["canonical_evidence_ids"] = list(finding.evidence_ids)
    attributes["canonical_impact_evidence_ids"] = list(finding.impact.evidence_ids)
    attributes["canonical_hypothesis_id"] = finding.hypothesis_id
    attributes["canonical_causal_chain_id"] = finding.causal_chain_id
    attributes["canonical_audit_session_id"] = finding.audit_session_id
    attributes["canonical_security_claim_id"] = security_claim_id
    attributes["claim_fingerprint"] = security_claim_fingerprint or _finding_fingerprint(finding)
    node = Node(finding.finding_id, "finding", finding.title, attributes)

    prospective_nodes = dict(graph.model.nodes)
    prospective_edges = list(graph.model.edges)
    prospective_nodes[node.node_id] = node
    prospective_edges.extend(
        Edge(finding.finding_id, "supported_by", evidence_id, {"provenance": "explicit_finding_gate"})
        for evidence_id in finding.evidence_ids
    )
    prospective_edges.append(Edge(
        finding.finding_id,
        "about",
        finding.hypothesis_id,
        {"provenance": "explicit_finding_gate"},
    ))
    prospective_edges.append(Edge(
        finding.finding_id,
        "traced_by",
        finding.causal_chain_id,
        {"provenance": "explicit_finding_gate"},
    ))
    if security_claim_id:
        prospective_edges.append(Edge(
            finding.finding_id,
            "derived_from_security_claim",
            security_claim_id,
            {"provenance": "explicit_verified_security_claim"},
        ))
    if finding.audit_session_id:
        prospective_edges.append(Edge(
            finding.finding_id,
            "originates_from",
            finding.audit_session_id,
            {"provenance": "explicit_finding_gate"},
        ))

    prospective = SystemModel()
    prospective.nodes = prospective_nodes
    prospective.edges = prospective_edges
    semantic_errors = validate_graph(prospective)
    if semantic_errors:
        raise ValueError(f"finding violates graph semantics: {semantic_errors[0]}")

    graph.model.add_node(node)
    for edge in prospective_edges[len(graph.model.edges):]:
        graph.model.add_edge(edge)
    graph._event(
        "FINDING_PERSISTED",
        finding=finding.finding_id,
        hypothesis=finding.hypothesis_id,
        evidence=list(finding.evidence_ids),
        impact_evidence=list(finding.impact.evidence_ids),
        causal_chain=finding.causal_chain_id,
        audit_session=finding.audit_session_id,
        security_claim=security_claim_id,
        claim_fingerprint=attributes["claim_fingerprint"],
    )
    return finding.finding_id
