"""Evidence-backed causal verification over the canonical reasoning graph."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .causal_reconstruction import CausalChainTrace, reconstruct_causal_chain
from .system_model import SystemModel


class CausalVerificationState(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CausalVerificationResult:
    state: CausalVerificationState
    chain_id: str
    trace: CausalChainTrace | None
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]


def verify_persisted_causal_chain(model: SystemModel, chain_id: str) -> CausalVerificationResult:
    """Verify a persisted causal trace without executing or inventing evidence."""
    try:
        trace = reconstruct_causal_chain(model, chain_id)
    except (KeyError, ValueError) as exc:
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, None, (), (str(exc),))

    # A verification anchor may be either evidence or a canonical invariant.
    # Only actual evidence nodes belong in the evidence-validation/support set.
    trace_evidence_ids = tuple(
        evidence_id
        for evidence_id in trace.evidence_ids
        if evidence_id in model.nodes and model.nodes[evidence_id].kind == "evidence"
    )
    missing = [
        evidence_id for evidence_id in trace.evidence_ids
        if evidence_id not in model.nodes
        or model.nodes[evidence_id].kind not in {"evidence", "invariant"}
    ]
    if missing:
        return CausalVerificationResult(
            CausalVerificationState.REJECTED, chain_id, trace, trace_evidence_ids,
            (f"causal evidence or verification anchor is missing: {', '.join(missing)}",),
        )

    supporting_evidence_ids = {
        edge.source
        for edge in model.edges
        if edge.source in trace_evidence_ids
        and edge.target == trace.hypothesis_id
        and edge.relation == "supports"
    }
    missing_support = [
        evidence_id for evidence_id in trace_evidence_ids
        if evidence_id not in supporting_evidence_ids
    ]
    if missing_support:
        return CausalVerificationResult(
            CausalVerificationState.UNRESOLVED, chain_id, trace, trace_evidence_ids,
            ("causal evidence does not explicitly support the chain hypothesis: "
             + ", ".join(missing_support),),
        )

    belief = model.nodes.get(trace.belief_update_id)
    if belief is None or belief.kind != "belief":
        return CausalVerificationResult(
            CausalVerificationState.REJECTED, chain_id, trace, trace_evidence_ids,
            ("causal chain belief-transition anchor is missing",),
        )
    declared_hypothesis = belief.attributes.get("hypothesis_id")
    if declared_hypothesis is not None and declared_hypothesis != trace.hypothesis_id:
        return CausalVerificationResult(
            CausalVerificationState.REJECTED, chain_id, trace, trace_evidence_ids,
            ("belief-transition hypothesis does not match causal-chain hypothesis",),
        )

    return CausalVerificationResult(
        CausalVerificationState.VERIFIED, chain_id, trace, trace_evidence_ids, ()
    )
