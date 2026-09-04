"""Trusted recovery boundary for persisted CYDRA findings.

A serialized finding is report data, not trusted reasoning state. This module
rehydrates persisted finding nodes only after checking that their duplicated
canonical references, graph relationships, report claims, and audit-bound
canonical state agree.
"""
from __future__ import annotations

import hashlib
import json

from .causal_reconstruction import reconstruct_causal_chain
from .finding import Finding
from .graph_semantics import validate_graph
from .reasoning_graph import ReasoningGraph

_CANONICAL_FIELDS = {"canonical_evidence_ids": "evidence_ids", "canonical_impact_evidence_ids": "impact.evidence_ids", "canonical_hypothesis_id": "hypothesis_id", "canonical_causal_chain_id": "causal_chain_id", "canonical_audit_session_id": "audit_session_id"}


def _claim_fingerprint(finding: Finding) -> str:
    payload = finding.as_report_data()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"persisted finding {field_name} must be a non-empty string")
    return value


def _require_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"persisted finding {field_name} must be a sequence of strings")
    return tuple(value)


def _validate_persisted_node(graph: ReasoningGraph, finding_id: str, node) -> Finding:
    if node.kind != "finding": raise ValueError(f"node is not a finding: {finding_id}")
    if node.attributes.get("persisted") is not True: raise ValueError(f"finding is not marked as canonical persisted state: {finding_id}")
    finding = Finding.from_report_data(node.attributes)
    if finding.finding_id != finding_id: raise ValueError("persisted finding ID does not match canonical node identity")
    if not finding.evidence_ids: raise ValueError("persisted finding requires canonical evidence IDs")
    if not finding.impact.evidence_ids: raise ValueError("persisted finding requires canonical impact evidence IDs")
    if not finding.causal_chain_id: raise ValueError("persisted finding requires a causal-chain reference")

    attrs = node.attributes
    for canonical_field, finding_field in _CANONICAL_FIELDS.items():
        if canonical_field not in attrs: raise ValueError(f"persisted finding is missing {canonical_field}")
        expected = tuple(finding.impact.evidence_ids) if finding_field == "impact.evidence_ids" else getattr(finding, finding_field)
        actual = attrs[canonical_field]
        if isinstance(expected, tuple):
            actual = _require_sequence(actual, canonical_field)
            if actual != expected: raise ValueError(f"persisted finding {canonical_field} disagrees with report claims")
        elif actual != expected: raise ValueError(f"persisted finding {canonical_field} disagrees with report claims")

    trace = reconstruct_causal_chain(graph.model, finding.causal_chain_id)
    if trace.hypothesis_id != finding.hypothesis_id: raise ValueError("persisted finding causal chain does not match hypothesis")
    if finding.audit_session_id is not None and trace.audit_session_id != finding.audit_session_id:
        raise ValueError("persisted finding causal chain audit-session provenance does not match")
    trace_evidence = set(trace.evidence_ids)
    claim_errors = finding.claim_validation_errors(trace_evidence)
    if claim_errors: raise ValueError(claim_errors[0])

    for evidence_id in tuple(finding.evidence_ids) + tuple(finding.impact.evidence_ids):
        evidence = graph.model.nodes.get(evidence_id)
        if evidence is None or evidence.kind != "evidence": raise ValueError(f"persisted finding references non-canonical evidence: {evidence_id}")
        if not any(edge.source == evidence_id and edge.relation == "supports" and edge.target == finding.hypothesis_id for edge in graph.model.edges):
            raise ValueError(f"persisted finding evidence does not support its hypothesis: {evidence_id}")

    hypothesis = graph.model.nodes.get(finding.hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis": raise ValueError("persisted finding hypothesis reference is not canonical")
    if finding.audit_session_id is not None:
        session = graph.model.nodes.get(finding.audit_session_id)
        if session is None or session.kind != "audit_session": raise ValueError("persisted finding audit-session reference is not canonical")

    required_edges = {(finding.finding_id, "about", finding.hypothesis_id), (finding.finding_id, "traced_by", finding.causal_chain_id)}
    required_edges.update((finding.finding_id, "supported_by", evidence_id) for evidence_id in finding.evidence_ids)
    if finding.audit_session_id: required_edges.add((finding.finding_id, "originates_from", finding.audit_session_id))
    actual_edges = {(edge.source, edge.relation, edge.target) for edge in graph.model.edges}
    missing = sorted(required_edges - actual_edges)
    if missing: raise ValueError(f"persisted finding is missing canonical graph edges: {missing[0]}")

    audit_errors = graph.verify_history_integrity()
    if audit_errors: raise ValueError("reasoning audit history is invalid")
    correspondence_errors = graph.verify_state_correspondence()
    if correspondence_errors: raise ValueError(f"audit state does not correspond to canonical graph: {correspondence_errors[0]}")

    stored_claim_fingerprint = attrs.get("claim_fingerprint")
    if not isinstance(stored_claim_fingerprint, str) or not stored_claim_fingerprint:
        raise ValueError("persisted finding is missing immutable claim fingerprint")
    if stored_claim_fingerprint != _claim_fingerprint(finding):
        raise ValueError("persisted finding claim fingerprint does not match report claims")

    graph_errors = validate_graph(graph.model)
    if graph_errors: raise ValueError(f"canonical graph is invalid: {graph_errors[0]}")
    return finding


def rehydrate_persisted_finding(graph: ReasoningGraph, finding_id: str) -> Finding:
    """Rehydrate one canonical finding without trusting serialized claim fields."""
    _require_string(finding_id, "ID")
    node = graph.model.nodes.get(finding_id)
    if node is None: raise KeyError(f"persisted finding missing: {finding_id}")
    return _validate_persisted_node(graph, finding_id, node)


def validate_persisted_findings(graph: ReasoningGraph) -> list[str]:
    """Return all persisted-finding recovery errors without mutating the graph."""
    errors: list[str] = []
    for node_id, node in sorted(graph.model.nodes.items()):
        if node.kind != "finding" or node.attributes.get("persisted") is not True: continue
        try: _validate_persisted_node(graph, node_id, node)
        except (KeyError, TypeError, ValueError) as exc: errors.append(f"{node_id}: {exc}")
    return errors
