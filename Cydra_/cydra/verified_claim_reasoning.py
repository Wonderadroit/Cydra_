"""Derive explicit security-claim drafts from already verified canonical state.

This boundary is intentionally conservative: it does not decide that a piece of
code is vulnerable merely because a causal chain exists. A canonical hypothesis
must explicitly carry the security-claim metadata produced by a reasoning layer.
The component verifies that metadata is anchored to the verified causal trace,
then emits a ``ReasoningFindingDraft`` for the normal finding gate.
"""
from __future__ import annotations

from dataclasses import dataclass

from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
from .finding_gate import FindingCandidate
from .finding_synthesis import ReasoningFindingDraft
from .impact import ImpactAssessment, ImpactLevel
from .reasoning_graph import ReasoningGraph
from .security_reasoning import SecurityClaimProposal, VerifiedSecurityClaim, verified_security_claim_fingerprint


@dataclass(frozen=True)
class VerifiedClaimPolicy:
    """Bounds on explicit security claims accepted from canonical hypotheses."""

    max_claims: int = 16

    def __post_init__(self) -> None:
        if self.max_claims < 1:
            raise ValueError("max_claims must be positive")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"security claim {field} must be a non-empty string")
    return value.strip()


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"security claim {field} must be a non-empty sequence of strings")
    return tuple(item.strip() for item in value)


def _draft_from_hypothesis(graph: ReasoningGraph, hypothesis_id: str, causal_chain_id: str) -> ReasoningFindingDraft:
    claim = graph.model.nodes[hypothesis_id].attributes.get("security_claim")
    if not isinstance(claim, dict):
        raise ValueError(f"hypothesis has no explicit security_claim metadata: {hypothesis_id}")

    evidence_ids = _strings(claim.get("evidence_ids"), "evidence_ids")
    impact_evidence_ids = _strings(claim.get("impact_evidence_ids", evidence_ids), "impact_evidence_ids")
    affected_components = _strings(claim.get("affected_components"), "affected_components")
    severity = _text(claim.get("severity"), "severity").upper()
    try:
        impact_level = ImpactLevel(severity)
    except ValueError as exc:
        raise ValueError(f"security claim severity is not canonical: {severity}") from exc
    if impact_level == ImpactLevel.UNKNOWN:
        raise ValueError("security claim severity cannot be UNKNOWN")

    declared_chain = claim.get("causal_chain_id")
    if declared_chain is not None and declared_chain != causal_chain_id:
        raise ValueError("security claim causal chain does not match verified trace")

    prerequisites_value = claim.get("prerequisites", ())
    if not isinstance(prerequisites_value, (list, tuple)) or not all(isinstance(item, str) for item in prerequisites_value):
        raise ValueError("security claim prerequisites must be a sequence of strings")

    candidate = FindingCandidate(
        in_scope=bool(claim.get("in_scope", False)),
        known_issue=bool(claim.get("known_issue", False)),
        evidence=True,
        reproducible=bool(claim.get("reproducible", False)),
        causal_verified=True,
        impact_assessed=True,
        hypothesis_resolved=bool(claim.get("hypothesis_resolved", True)),
    )
    impact = ImpactAssessment(
        impact_level,
        _text(claim.get("asset_at_risk"), "asset_at_risk"),
        _text(claim.get("consequence"), "consequence"),
        tuple(prerequisites_value),
        impact_evidence_ids,
    )
    return ReasoningFindingDraft(
        finding_id=_text(claim.get("finding_id"), "finding_id"),
        title=_text(claim.get("title"), "title"),
        summary=_text(claim.get("summary"), "summary"),
        severity=severity,
        impact=impact,
        affected_components=affected_components,
        evidence_ids=evidence_ids,
        hypothesis_id=hypothesis_id,
        causal_chain_id=causal_chain_id,
        candidate=candidate,
        poc_reference=claim.get("poc_reference") if isinstance(claim.get("poc_reference"), str) else None,
        audit_session_id=claim.get("audit_session_id") if isinstance(claim.get("audit_session_id"), str) else None,
    )


def propose_verified_claims(
    graph: ReasoningGraph,
    *,
    policy: VerifiedClaimPolicy | None = None,
) -> tuple[ReasoningFindingDraft, ...]:
    """Emit drafts only from verified causal chains with complete finding claims.

    Hypothesis-level security claims are deliberately not promoted here. They are
    reasoning output that still needs causal verification and finding/impact data.
    No historical benchmark data, vulnerability signatures, source-code pattern,
    or severity heuristic is consulted here.
    """
    if not isinstance(graph, ReasoningGraph):
        raise TypeError("verified claim reasoning requires the canonical ReasoningGraph")
    active = policy or VerifiedClaimPolicy()
    drafts: list[ReasoningFindingDraft] = []
    seen: set[str] = set()

    for node in sorted(graph.model.nodes.values(), key=lambda item: item.node_id):
        if node.kind != "causal_chain":
            continue
        chain_id = node.node_id
        for edge in graph.model.edges:
            if edge.relation != "motivates" or edge.target != chain_id:
                continue
            hypothesis_id = edge.source
            if hypothesis_id in seen:
                continue
            verification = verify_persisted_causal_chain(graph.model, chain_id)
            if verification.state is not CausalVerificationState.VERIFIED:
                continue
            hypothesis = graph.model.nodes.get(hypothesis_id)
            if hypothesis is None or hypothesis.kind != "hypothesis":
                continue
            claim = hypothesis.attributes.get("security_claim")
            if not isinstance(claim, dict):
                continue
            if claim.get("claim_kind", "finding") != "finding":
                continue

            # The finding-facing provider must cross the persisted verified-claim
            # boundary, not merely observe a verified causal chain. The gate will
            # independently revalidate this state, but the provider must not emit a
            # promotion attempt that could never be admissible.
            claim_node = graph.model.nodes.get(f"security_claim:{hypothesis_id}")
            if claim_node is None or claim_node.kind != "security_claim":
                continue
            if claim_node.attributes.get("verified") is not True:
                continue
            if claim_node.attributes.get("hypothesis_id") != hypothesis_id:
                continue
            if claim_node.attributes.get("causal_chain_id") != chain_id:
                continue
            if claim_node.attributes.get("claim") != claim:
                continue
            observation_id = claim_node.attributes.get("observation_id")
            evidence_ids = claim_node.attributes.get("evidence_ids")
            fingerprint = claim_node.attributes.get("claim_fingerprint")
            if (
                not isinstance(observation_id, str)
                or not observation_id.startswith("observation:")
                or not isinstance(evidence_ids, list)
                or not all(isinstance(item, str) for item in evidence_ids)
                or not isinstance(fingerprint, str)
            ):
                continue
            verified_claim = VerifiedSecurityClaim(
                SecurityClaimProposal(hypothesis_id, observation_id.removeprefix("observation:"), claim),
                chain_id,
                tuple(evidence_ids),
            )
            if fingerprint != verified_security_claim_fingerprint(verified_claim):
                continue
            draft = _draft_from_hypothesis(graph, hypothesis_id, chain_id)
            drafts.append(draft)
            seen.add(hypothesis_id)
            if len(drafts) >= active.max_claims:
                return tuple(drafts)
    return tuple(drafts)


class VerifiedClaimDraftProvider:
    """Autonomous-driver adapter for verified canonical security claims."""

    def __init__(self, policy: VerifiedClaimPolicy | None = None) -> None:
        self.policy = policy or VerifiedClaimPolicy()

    def propose(self, model, step) -> tuple[ReasoningFindingDraft, ...]:
        return propose_verified_claims(model, policy=self.policy)
