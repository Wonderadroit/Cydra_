"""Derive security claims only after a canonical causal trace is verified.

This module is deliberately an intermediate reasoning boundary. It does not
promote findings, assign severity, or infer impact. It takes an already emitted
security hypothesis and turns it into an explicit claim only when the persisted
causal chain is independently reconstructable and verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
from .reasoning_graph import ReasoningGraph


@dataclass(frozen=True)
class VerifiedSecurityClaim:
    """A security claim grounded in a verified canonical causal trace."""

    hypothesis_id: str
    causal_chain_id: str
    statement: str
    mechanism: str
    evidence_ids: tuple[str, ...]
    affected_components: tuple[str, ...]
    confidence: float


def _strings(value: object, field: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"security claim {field} must be a sequence of strings")
    if required and not value:
        raise ValueError(f"security claim {field} must not be empty")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"security claim {field} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"security claim {field} must be a non-empty string")
    return value.strip()


def _claim_from_verified_chain(
    graph: ReasoningGraph,
    hypothesis_id: str,
    chain_id: str,
) -> VerifiedSecurityClaim | None:
    hypothesis = graph.model.nodes.get(hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        return None
    metadata = hypothesis.attributes.get("security_claim")
    if not isinstance(metadata, Mapping) or metadata.get("claim_kind") != "security_hypothesis":
        return None

    verification = verify_persisted_causal_chain(graph.model, chain_id)
    if verification.state is not CausalVerificationState.VERIFIED or verification.trace is None:
        return None
    if verification.trace.hypothesis_id != hypothesis_id:
        return None

    declared_chain = metadata.get("causal_chain_id")
    if declared_chain is not None and declared_chain != chain_id:
        return None

    confidence_value = metadata.get("confidence", 0.0)
    if not isinstance(confidence_value, (int, float)) or not 0.0 <= float(confidence_value) <= 1.0:
        raise ValueError("security claim confidence must be between 0 and 1")

    return VerifiedSecurityClaim(
        hypothesis_id=hypothesis_id,
        causal_chain_id=chain_id,
        statement=_text(metadata.get("statement"), "statement"),
        mechanism=_text(metadata.get("mechanism"), "mechanism"),
        evidence_ids=verification.evidence_ids,
        affected_components=_strings(metadata.get("affected_components"), "affected_components"),
        confidence=float(confidence_value),
    )


def derive_verified_security_claims(graph: ReasoningGraph, *, max_claims: int = 16) -> tuple[VerifiedSecurityClaim, ...]:
    """Emit explicit security claims from verified causal chains only.

    A claim is not created merely because a hypothesis looks security-relevant.
    The chain must reconstruct, every evidence anchor must explicitly support the
    chain hypothesis, and the canonical belief-transition anchor must agree with
    the hypothesis. Historical benchmark truth is never consulted.
    """
    if not isinstance(graph, ReasoningGraph):
        raise TypeError("verified security reasoning requires the canonical ReasoningGraph")
    if max_claims < 1:
        raise ValueError("max_claims must be positive")

    claims: list[VerifiedSecurityClaim] = []
    seen: set[str] = set()
    for chain in sorted(graph.model.nodes.values(), key=lambda item: item.node_id):
        if chain.kind != "causal_chain":
            continue
        verification = verify_persisted_causal_chain(graph.model, chain.node_id)
        if verification.state is not CausalVerificationState.VERIFIED or verification.trace is None:
            continue
        hypothesis_id = verification.trace.hypothesis_id
        if hypothesis_id in seen:
            continue
        claim = _claim_from_verified_chain(graph, hypothesis_id, chain.node_id)
        if claim is None:
            continue
        claims.append(claim)
        seen.add(hypothesis_id)
        if len(claims) >= max_claims:
            break
    return tuple(claims)
