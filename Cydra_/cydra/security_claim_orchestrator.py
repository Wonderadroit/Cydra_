"""Canonical orchestration bridge for verified security-claim finalization.

The orchestrator remains responsible for lifecycle coordination while the security
reasoning module remains authoritative for the fail-closed claim boundary. This
module deliberately performs no inference, execution, or finding synthesis.
"""
from __future__ import annotations

from .security_reasoning import (
    SecurityReasoningInputs,
    emit_verified_security_claims,
    persist_verified_security_claim,
)


def finalize_verified_security_claims(orchestrator, inputs: SecurityReasoningInputs) -> tuple[str, ...]:
    """Finalize all currently verifiable security claims on an orchestrator.

    This is a pure lifecycle bridge: claim emission still requires the canonical
    supported hypothesis, exact competing observation binding, explicit belief
    polarity, and a verified causal chain. Persistence performs its own complete
    canonical-state validation before creating the security-claim node.

    The function never executes an observation, infers evidentiary polarity, or
    bypasses the finding gate.
    """
    if not isinstance(inputs, SecurityReasoningInputs):
        raise TypeError("verified security claim finalization requires SecurityReasoningInputs")
    graph = getattr(orchestrator, "graph", None)
    if graph is None:
        raise TypeError("verified security claim finalization requires a reasoning orchestrator")

    emitted = emit_verified_security_claims(graph, inputs)
    return tuple(persist_verified_security_claim(graph, claim) for claim in emitted)
