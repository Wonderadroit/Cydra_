from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .finding import Finding
    from .reasoning_graph import ReasoningGraph


class GateDecision(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class FindingCandidate:
    in_scope: bool
    known_issue: bool
    evidence: bool
    reproducible: bool
    causal_verified: bool
    impact_assessed: bool
    hypothesis_resolved: bool = True


@dataclass(frozen=True)
class GateResult:
    decision: GateDecision
    reasons: List[str]


def evaluate_finding(candidate: FindingCandidate) -> GateResult:
    """Apply conservative promotion rules before a candidate becomes a finding."""
    if not candidate.in_scope:
        return GateResult(GateDecision.BLOCKED, ["target is out of scope"])
    if candidate.known_issue:
        return GateResult(GateDecision.BLOCKED, ["candidate matches a known issue"])
    if not candidate.hypothesis_resolved:
        return GateResult(GateDecision.UNRESOLVED, ["hypothesis remains unresolved"])
    missing = []
    if not candidate.evidence:
        missing.append("evidence")
    if not candidate.reproducible:
        missing.append("reproducibility")
    if not candidate.causal_verified:
        missing.append("causal verification")
    if not candidate.impact_assessed:
        missing.append("impact assessment")
    if missing:
        return GateResult(GateDecision.BLOCKED, missing)
    return GateResult(GateDecision.READY, [])


def _validate_canonical_security_claim(graph: "ReasoningGraph", claim_node, finding: "Finding") -> str | None:
    """Reconstruct and independently validate the canonical verified security claim."""
    from .causal_verification import verify_persisted_causal_chain
    from .security_reasoning import (
        SecurityClaimProposal,
        VerifiedSecurityClaim,
        verified_security_claim_fingerprint,
    )

    attributes = claim_node.attributes
    hypothesis_id = attributes.get("hypothesis_id")
    observation_id = attributes.get("observation_id")
    causal_chain_id = attributes.get("causal_chain_id")
    evidence_ids = attributes.get("evidence_ids")
    claim_payload = attributes.get("claim")
    fingerprint = attributes.get("claim_fingerprint")

    if not isinstance(hypothesis_id, str) or hypothesis_id != finding.hypothesis_id:
        return "security claim hypothesis does not match finding hypothesis"
    if not isinstance(observation_id, str) or not observation_id.startswith("observation:"):
        return "security claim observation reference is invalid"
    if not isinstance(causal_chain_id, str) or causal_chain_id != finding.causal_chain_id:
        return "security claim causal chain does not match finding causal chain"
    if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
        return "security claim evidence references are invalid"
    if not isinstance(claim_payload, dict):
        return "security claim payload is invalid"
    if not isinstance(fingerprint, str):
        return "security claim fingerprint is missing"

    hypothesis = graph.model.nodes.get(hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        return "finding hypothesis is not a canonical hypothesis node"
    if claim_payload != hypothesis.attributes.get("security_claim"):
        return "security claim payload does not match canonical hypothesis metadata"

    # A verified security claim is the canonical source for the report-level
    # finding identity. Do not allow a caller to reuse a verified claim while
    # silently changing its title, severity, impact, evidence, or other report
    # semantics at promotion time.
    if claim_payload.get("claim_kind", "finding") == "finding":
            expected_optional_poc = claim_payload.get("poc_reference") if isinstance(claim_payload.get("poc_reference"), str) else None
            expected_optional_session = claim_payload.get("audit_session_id") if isinstance(claim_payload.get("audit_session_id"), str) else None
            expected_prerequisites = claim_payload.get("prerequisites", ())
            if not isinstance(expected_prerequisites, (list, tuple)):
                return "security claim prerequisites are invalid"
            if finding.finding_id != claim_payload.get("finding_id"):
                return "finding ID does not match verified security claim"
            if finding.title != claim_payload.get("title"):
                return "finding title does not match verified security claim"
            if finding.summary != claim_payload.get("summary"):
                return "finding summary does not match verified security claim"
            if finding.severity != str(claim_payload.get("severity", "")).upper():
                return "finding severity does not match verified security claim"
            if finding.affected_components != tuple(claim_payload.get("affected_components", ())):
                return "finding affected components do not match verified security claim"
            if finding.evidence_ids != tuple(claim_payload.get("evidence_ids", ())):
                return "finding evidence does not match verified security claim"
            if finding.impact.asset_at_risk != claim_payload.get("asset_at_risk"):
                return "finding impact asset does not match verified security claim"
            if finding.impact.consequence != claim_payload.get("consequence"):
                return "finding impact consequence does not match verified security claim"
            if finding.impact.prerequisites != tuple(expected_prerequisites):
                return "finding impact prerequisites do not match verified security claim"
            if finding.impact.evidence_ids != tuple(claim_payload.get("impact_evidence_ids", claim_payload.get("evidence_ids", ()))):
                return "finding impact evidence does not match verified security claim"
            if finding.hypothesis_id != hypothesis_id:
                return "finding hypothesis does not match verified security claim"
            if finding.poc_reference != expected_optional_poc:
                return "finding PoC reference does not match verified security claim"
            if finding.audit_session_id != expected_optional_session:
                return "finding audit-session reference does not match verified security claim"


    claim = VerifiedSecurityClaim(
        SecurityClaimProposal(
            hypothesis_id,
            observation_id.removeprefix("observation:"),
            claim_payload,
        ),
        causal_chain_id,
        tuple(evidence_ids),
    )
    if fingerprint != verified_security_claim_fingerprint(claim):
        return "security claim fingerprint does not match canonical claim payload"

    observation = graph.model.nodes.get(observation_id)
    if observation is None or observation.kind != "observation":
        return "security claim observation is not canonical"
    if observation.attributes.get("planned") is not True:
        return "security claim observation is not planned"

    competing_id = claim_payload.get("competing_hypothesis_id")
    if not isinstance(competing_id, str):
        return "security claim competing hypothesis binding is invalid"
    if tuple(observation.attributes.get("discriminates_hypothesis_ids", ())) != (hypothesis_id, competing_id):
        return "security claim observation binding does not match canonical claim"

    try:
        verification = verify_persisted_causal_chain(graph.model, causal_chain_id)
    except (KeyError, ValueError):
        return "security claim causal chain is not canonical"
    if verification.state.value != "verified" or verification.trace is None:
        return "security claim causal chain is not verified"
    trace = verification.trace
    if trace.hypothesis_id != hypothesis_id:
        return "security claim causal chain hypothesis does not match claim"
    if trace.observation_id != observation_id:
        return "security claim causal chain observation does not match claim"
    if tuple(verification.evidence_ids) != tuple(evidence_ids):
        return "security claim evidence references do not match canonical causal chain"

    return None


def evaluate_finding_graph(graph: "ReasoningGraph", candidate: FindingCandidate, finding: "Finding") -> GateResult:
    """Validate a ready candidate against canonical graph evidence and audit state."""
    base = evaluate_finding(candidate)
    if base.decision != GateDecision.READY:
        return base

    audit_errors = graph.verify_history_integrity()
    if audit_errors:
        return GateResult(GateDecision.BLOCKED, ["reasoning audit history is invalid"])

    if not finding.finding_id.strip():
        return GateResult(GateDecision.BLOCKED, ["finding ID is empty"])
    if not finding.hypothesis_id:
        return GateResult(GateDecision.BLOCKED, ["finding hypothesis is missing"])
    if not finding.evidence_ids:
        return GateResult(GateDecision.BLOCKED, ["finding has no canonical evidence IDs"])
    if not finding.causal_chain_id:
        return GateResult(GateDecision.BLOCKED, ["finding has no causal-chain reference"])

    hypothesis = graph.model.nodes.get(finding.hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        return GateResult(GateDecision.BLOCKED, ["finding hypothesis is not a canonical hypothesis node"])

    # Security hypotheses carry a claim proposal in canonical state. Such a finding
    # must cross the verified-claim boundary; probability, evidence, and causal state
    # alone are insufficient to turn a security claim into a reportable finding.
    security_claim = hypothesis.attributes.get("security_claim")
    if security_claim is not None:
        claim_id = f"security_claim:{finding.hypothesis_id}"
        claim_node = graph.model.nodes.get(claim_id)
        if claim_node is None or claim_node.kind != "security_claim":
            return GateResult(GateDecision.BLOCKED, ["security finding requires a persisted verified security claim"])
        if claim_node.attributes.get("verified") is not True:
            return GateResult(GateDecision.BLOCKED, ["security claim is not canonically verified"])
        claim_error = _validate_canonical_security_claim(graph, claim_node, finding)
        if claim_error:
            return GateResult(GateDecision.BLOCKED, [claim_error])

    missing_evidence = [evidence_id for evidence_id in finding.evidence_ids if evidence_id not in graph.model.nodes or graph.model.nodes[evidence_id].kind != "evidence"]
    if missing_evidence:
        return GateResult(GateDecision.BLOCKED, [f"missing canonical evidence: {', '.join(missing_evidence)}"])

    from .causal_verification import verify_persisted_causal_chain
    verification = verify_persisted_causal_chain(graph.model, finding.causal_chain_id)
    trace = verification.trace
    if trace is None:
        if verification.state.value == "rejected":
            reason = verification.reasons[0] if verification.reasons else "causal chain was rejected"
            return GateResult(GateDecision.BLOCKED, [f"causal verification rejected: {reason}"])
        return GateResult(GateDecision.BLOCKED, ["causal chain has no reconstructed trace"])

    if trace.hypothesis_id != finding.hypothesis_id:
        return GateResult(GateDecision.BLOCKED, ["causal chain hypothesis does not match finding hypothesis"])

    trace_evidence = set(verification.evidence_ids)
    finding_evidence = set(finding.evidence_ids)
    if not finding_evidence.issubset(trace_evidence):
        return GateResult(GateDecision.BLOCKED, ["finding evidence must be grounded in the causal trace"])

    impact_evidence = set(finding.impact.evidence_ids)
    if not impact_evidence.issubset(trace_evidence):
        return GateResult(GateDecision.BLOCKED, ["impact evidence must be grounded in the causal trace"])

    if verification.state.value == "rejected":
        reason = verification.reasons[0] if verification.reasons else "causal chain was rejected"
        return GateResult(GateDecision.BLOCKED, [f"causal verification rejected: {reason}"])
    if verification.state.value == "unresolved":
        reason = verification.reasons[0] if verification.reasons else "causal chain remains unresolved"
        return GateResult(GateDecision.UNRESOLVED, [f"causal verification unresolved: {reason}"])

    claim_errors = finding.claim_validation_errors(trace_evidence)
    if claim_errors:
        return GateResult(GateDecision.BLOCKED, claim_errors)

    unsupported = [
        evidence_id for evidence_id in finding.evidence_ids
        if not any(edge.source == evidence_id and edge.relation == "supports" and edge.target == finding.hypothesis_id for edge in graph.model.edges)
    ]
    if unsupported:
        return GateResult(GateDecision.BLOCKED, [f"finding evidence does not explicitly support the finding hypothesis: {', '.join(unsupported)}"])

    unsupported_impact = [
        evidence_id for evidence_id in finding.impact.evidence_ids
        if not any(edge.source == evidence_id and edge.relation == "supports" and edge.target == finding.hypothesis_id for edge in graph.model.edges)
    ]
    if unsupported_impact:
        return GateResult(GateDecision.BLOCKED, [f"finding impact evidence does not explicitly support the finding hypothesis: {', '.join(unsupported_impact)}"])

    audit_session_nodes = [node for node in graph.model.nodes.values() if node.kind == "audit_session"]
    if audit_session_nodes:
        if not finding.audit_session_id:
            return GateResult(GateDecision.BLOCKED, ["finding is missing audit-session provenance"])
        if finding.audit_session_id not in graph.model.nodes:
            return GateResult(GateDecision.BLOCKED, ["finding audit session is not canonical"])
        session = graph.model.nodes[finding.audit_session_id]
        if session.kind != "audit_session":
            return GateResult(GateDecision.BLOCKED, ["finding audit-session reference has the wrong node kind"])
        from .audit_session import RepositoryAuditSession
        provenance_errors = RepositoryAuditSession.validate_persisted_provenance(graph.model, finding.audit_session_id)
        if provenance_errors:
            return GateResult(GateDecision.BLOCKED, ["audit-session provenance is invalid"])

    return GateResult(GateDecision.READY, [])
