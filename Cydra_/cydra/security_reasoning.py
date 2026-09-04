"""Security-hypothesis generation and verified claim emission.

This module is a reasoning layer, not a finding detector. It derives competing
security hypotheses and the observations that distinguish them from canonical
AST-backed relationships. Claim proposals are emitted before verification; a
separate canonical-state gate emits verified security claims only after the exact
hypothesis, observation, belief transition, supporting evidence, and causal chain
all agree.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
from .hypotheses import HypothesisState
from .planner import Hypothesis, Observation
from .reasoning_driver import ReasoningInputs
from .system_model import Edge, Node, SystemModel


@dataclass(frozen=True)
class SecurityClaimProposal:
    """A security claim at hypothesis level, before causal verification/finding gate."""

    hypothesis_id: str
    observation_name: str
    claim: Mapping[str, object]


@dataclass(frozen=True)
class VerifiedSecurityClaim:
    """A security claim whose canonical reasoning state has passed verification."""

    proposal: SecurityClaimProposal
    causal_chain_id: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class SecurityReasoningInputs(ReasoningInputs):
    """Normal planning inputs plus explicit security-claim metadata."""

    security_claims: tuple[SecurityClaimProposal, ...] = ()


def _offset(edge: Edge) -> int | None:
    location = edge.attributes.get("source_location")
    if not isinstance(location, (list, tuple)) or not location:
        return None
    value = location[0]
    return value if isinstance(value, int) else None


def _edge_evidence_ref(edge: Edge) -> str:
    """Stable reference to semantic evidence without inventing an evidence node."""
    return (
        f"{edge.attributes.get('provenance', '')}:"
        f"{edge.attributes.get('ast_node_id', 'unknown')}"
    )


def _same_function_reentrancy_proposals(model: SystemModel, max_claims: int) -> tuple[
    tuple[Hypothesis, ...], tuple[Observation, ...], tuple[SecurityClaimProposal, ...]
]:
    by_function: dict[str, dict[str, list[Edge]]] = {}
    for edge in model.edges:
        if not edge.attributes.get("evidence_backed") or not edge.attributes.get("candidate"):
            continue
        if edge.relation not in {"external_call", "writes"}:
            continue
        function = model.nodes.get(edge.source)
        if function is None or function.kind != "function":
            continue
        if function.label == "constructor":
            continue
        by_function.setdefault(edge.source, {"external_call": [], "writes": []})[edge.relation].append(edge)

    hypotheses: list[Hypothesis] = []
    observations: list[Observation] = []
    claims: list[SecurityClaimProposal] = []
    for function_id in sorted(by_function):
        calls = by_function[function_id]["external_call"]
        writes = by_function[function_id]["writes"]
        for call in sorted(calls, key=lambda edge: (_offset(edge) is None, _offset(edge) or 0, edge.target)):
            call_offset = _offset(call)
            if call_offset is None:
                continue
            for write in sorted(writes, key=lambda edge: (_offset(edge) is None, _offset(edge) or 0, edge.target)):
                write_offset = _offset(write)
                if write_offset is None or call_offset >= write_offset:
                    continue
                state_id = write.target
                suffix = f"{function_id}:{state_id}"
                hypothesis_name = f"security:reentrancy:{suffix}"
                alternative_name = f"security:benign-external-interaction:{suffix}"
                observation_name = f"verify:{hypothesis_name}"
                if any(item.name == hypothesis_name for item in hypotheses):
                    continue

                call_confidence = float(call.attributes.get("confidence", 0.0))
                write_confidence = float(write.attributes.get("confidence", 0.0))
                confidence = min(call_confidence, write_confidence)
                claim = {
                    "claim_kind": "security_hypothesis",
                    "statement": (
                        f"{function_id} performs an external call before writing {state_id}; "
                        "the ordering is consistent with a reentrancy-driven state inconsistency "
                        "and requires causal verification."
                    ),
                    "mechanism": "external_call_precedes_state_write",
                    "function_id": function_id,
                    "affected_components": [function_id, state_id],
                    "evidence_refs": [_edge_evidence_ref(call), _edge_evidence_ref(write)],
                    "confidence": confidence,
                    "competing_hypothesis_id": f"hypothesis:{alternative_name}",
                    "verification_outcomes": ["CALLBACK_CONFIRMED", "CALLBACK_NOT_REPRODUCED", "INCONCLUSIVE"],
                }
                primary = Hypothesis(
                    name=hypothesis_name,
                    probability=confidence,
                    predictions={observation_name: {
                        "CALLBACK_CONFIRMED": 0.80,
                        "CALLBACK_NOT_REPRODUCED": 0.15,
                        "INCONCLUSIVE": 0.05,
                    }},
                )
                alternative = Hypothesis(
                    name=alternative_name,
                    probability=max(0.0, 1.0 - confidence),
                    predictions={observation_name: {
                        "CALLBACK_CONFIRMED": 0.10,
                        "CALLBACK_NOT_REPRODUCED": 0.80,
                        "INCONCLUSIVE": 0.10,
                    }},
                )
                observation = Observation(
                    name=observation_name,
                    outcomes=["CALLBACK_CONFIRMED", "CALLBACK_NOT_REPRODUCED", "INCONCLUSIVE"],
                    cost=1.0,
                    authorized=True,
                    domain="target",
                    discriminates_hypothesis_ids=(primary.hypothesis_id, alternative.hypothesis_id),
                )
                hypotheses.extend((primary, alternative))
                observations.append(observation)
                claims.append(SecurityClaimProposal(primary.hypothesis_id, observation_name, claim))
                if len(claims) >= max_claims:
                    return tuple(hypotheses), tuple(observations), tuple(claims)
    return tuple(hypotheses), tuple(observations), tuple(claims)


def security_reasoning_inputs(
    model: SystemModel,
    *,
    max_claims: int = 16,
) -> SecurityReasoningInputs:
    """Derive bounded competing security hypotheses from canonical AST-backed relationships."""
    if not isinstance(model, SystemModel):
        raise TypeError("security reasoning requires the canonical SystemModel")
    if max_claims < 1:
        raise ValueError("max_claims must be positive")
    hypotheses, observations, claims = _same_function_reentrancy_proposals(model, max_claims)
    return SecurityReasoningInputs(hypotheses, observations, claims)


def persist_security_claims(graph, inputs: SecurityReasoningInputs) -> None:
    """Persist security metadata and canonical competing-hypothesis bindings."""
    if not isinstance(inputs, SecurityReasoningInputs):
        return
    changed: list[str] = []
    for proposal in inputs.security_claims:
        node = graph.model.nodes.get(proposal.hypothesis_id)
        if node is None or node.kind != "hypothesis":
            raise ValueError(f"security claim hypothesis is not canonical: {proposal.hypothesis_id}")
        attributes = {**node.attributes, "security_claim": dict(proposal.claim)}
        graph.model.nodes[proposal.hypothesis_id] = type(node)(
            node.node_id, node.kind, node.label, attributes
        )
        competing_id = proposal.claim.get("competing_hypothesis_id")
        if not isinstance(competing_id, str) or not competing_id.strip():
            raise ValueError("security claim requires a competing hypothesis binding")
        competing = graph.model.nodes.get(competing_id)
        if competing is None or competing.kind != "hypothesis":
            raise ValueError(f"competing security hypothesis is not canonical: {competing_id}")
        graph.model.connect(
            proposal.hypothesis_id,
            "competes_with",
            competing_id,
            provenance="explicit_security_reasoning",
            rationale="canonical competing hypothesis emitted with the security hypothesis",
        )
        changed.append(proposal.hypothesis_id)
    if changed:
        graph._event("SECURITY_HYPOTHESES_EMITTED", hypotheses=changed)


def emit_verified_security_claims(
    graph,
    inputs: SecurityReasoningInputs,
) -> tuple[VerifiedSecurityClaim, ...]:
    """Emit only security claims backed by a fully verified canonical reasoning chain."""
    if not isinstance(inputs, SecurityReasoningInputs):
        raise TypeError("verified security claim emission requires SecurityReasoningInputs")

    emitted: list[VerifiedSecurityClaim] = []
    for proposal in inputs.security_claims:
        hypothesis = graph.model.nodes.get(proposal.hypothesis_id)
        if hypothesis is None or hypothesis.kind != "hypothesis":
            continue
        if hypothesis.attributes.get("state") != HypothesisState.SUPPORTED.value:
            continue

        claim = hypothesis.attributes.get("security_claim")
        if not isinstance(claim, Mapping) or dict(claim) != dict(proposal.claim):
            continue
        competing_id = claim.get("competing_hypothesis_id")
        if not isinstance(competing_id, str):
            continue
        competing = graph.model.nodes.get(competing_id)
        if competing is None or competing.kind != "hypothesis":
            continue
        if not any(
            edge.source == proposal.hypothesis_id
            and edge.target == competing_id
            and edge.relation == "competes_with"
            for edge in graph.model.edges
        ):
            continue

        observation_id = f"observation:{proposal.observation_name}"
        observation = graph.model.nodes.get(observation_id)
        if observation is None or observation.kind != "observation":
            continue
        if observation.attributes.get("planned") is not True:
            continue
        expected_pair = (proposal.hypothesis_id, competing_id)
        if tuple(observation.attributes.get("discriminates_hypothesis_ids", ())) != expected_pair:
            continue

        supporting_beliefs = []
        for edge in graph.model.edges:
            if edge.source != observation_id or edge.relation != "updates":
                continue
            belief = graph.model.nodes.get(edge.target)
            if belief is None or belief.kind != "belief":
                continue
            if belief.attributes.get("hypothesis_id") != proposal.hypothesis_id:
                continue
            if belief.attributes.get("state") != HypothesisState.SUPPORTED.value:
                continue
            if belief.attributes.get("evidence_polarity") != "supports":
                continue
            supporting_beliefs.append(belief.node_id)
        if len(supporting_beliefs) != 1:
            continue

        candidate_chains = []
        for edge in graph.model.edges:
            if edge.source != proposal.hypothesis_id or edge.relation != "motivates":
                continue
            chain = graph.model.nodes.get(edge.target)
            if chain is None or chain.kind != "causal_chain":
                continue
            try:
                verification = verify_persisted_causal_chain(graph.model, chain.node_id)
            except (KeyError, ValueError):
                continue
            if verification.state != CausalVerificationState.VERIFIED or verification.trace is None:
                continue
            if verification.trace.hypothesis_id != proposal.hypothesis_id:
                continue
            if verification.trace.observation_id != observation_id:
                continue
            if verification.trace.belief_update_id != supporting_beliefs[0]:
                continue
            candidate_chains.append((chain.node_id, verification.evidence_ids))

        if len(candidate_chains) != 1:
            continue
        chain_id, evidence_ids = candidate_chains[0]
        emitted.append(VerifiedSecurityClaim(proposal, chain_id, evidence_ids))

    return tuple(emitted)


def security_claim_node_id(claim: VerifiedSecurityClaim) -> str:
    """Return the deterministic canonical node ID for a verified security claim."""
    return f"security_claim:{claim.proposal.hypothesis_id}"


def verified_security_claim_fingerprint(claim: VerifiedSecurityClaim) -> str:
    """Return a deterministic fingerprint of the exact verified-claim semantic payload."""
    payload = {
        "hypothesis_id": claim.proposal.hypothesis_id,
        "observation_name": claim.proposal.observation_name,
        "causal_chain_id": claim.causal_chain_id,
        "evidence_ids": list(claim.evidence_ids),
        "claim": dict(claim.proposal.claim),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def persist_verified_security_claim(graph, claim: VerifiedSecurityClaim) -> str:
    """Persist a verified claim as the canonical bridge into finding synthesis."""
    if not isinstance(claim, VerifiedSecurityClaim):
        raise TypeError("verified security claim is required")

    hypothesis_id = claim.proposal.hypothesis_id
    hypothesis = graph.model.nodes.get(hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        raise ValueError("verified security claim hypothesis is not canonical")
    if hypothesis.attributes.get("state") != HypothesisState.SUPPORTED.value:
        raise ValueError("verified security claim hypothesis is no longer supported")
    canonical_claim = hypothesis.attributes.get("security_claim")
    if not isinstance(canonical_claim, Mapping) or dict(canonical_claim) != dict(claim.proposal.claim):
        raise ValueError("verified security claim metadata no longer matches canonical state")

    observation_id = f"observation:{claim.proposal.observation_name}"
    observation = graph.model.nodes.get(observation_id)
    if observation is None or observation.kind != "observation":
        raise ValueError("verified security claim observation is not canonical")
    if observation.attributes.get("planned") is not True:
        raise ValueError("verified security claim observation is not planned")
    competing_id = claim.proposal.claim.get("competing_hypothesis_id")
    if not isinstance(competing_id, str):
        raise ValueError("verified security claim competing hypothesis binding is invalid")
    if tuple(observation.attributes.get("discriminates_hypothesis_ids", ())) != (hypothesis_id, competing_id):
        raise ValueError("verified security claim observation binding does not match canonical claim")

    try:
        verification = verify_persisted_causal_chain(graph.model, claim.causal_chain_id)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"verified security claim causal chain is not canonical: {exc}") from exc
    if verification.state != CausalVerificationState.VERIFIED or verification.trace is None:
        raise ValueError("verified security claim causal chain is not verified")
    trace = verification.trace
    if trace.hypothesis_id != hypothesis_id:
        raise ValueError("verified security claim causal chain hypothesis does not match claim")
    if trace.observation_id != observation_id:
        raise ValueError("verified security claim causal chain observation does not match claim")
    if tuple(verification.evidence_ids) != tuple(claim.evidence_ids):
        raise ValueError("verified security claim evidence references do not match canonical causal chain")

    node_id = security_claim_node_id(claim)
    existing = graph.model.nodes.get(node_id)
    fingerprint = verified_security_claim_fingerprint(claim)
    attributes = {
        "hypothesis_id": hypothesis_id,
        "observation_id": observation_id,
        "causal_chain_id": claim.causal_chain_id,
        "evidence_ids": list(claim.evidence_ids),
        "claim": dict(claim.proposal.claim),
        "claim_fingerprint": fingerprint,
        "verified": True,
    }
    if existing is not None:
        if existing.kind != "security_claim" or existing.attributes != attributes:
            raise ValueError("canonical verified security claim already exists with different state")
        return node_id

    graph.model.add_node(Node(node_id, "security_claim", claim.proposal.observation_name, attributes))
    graph._event(
        "VERIFIED_SECURITY_CLAIM_PERSISTED",
        security_claim=node_id,
        hypothesis=hypothesis_id,
        observation=attributes["observation_id"],
        causal_chain=claim.causal_chain_id,
        evidence=list(claim.evidence_ids),
        claim_fingerprint=fingerprint,
    )
    return node_id
