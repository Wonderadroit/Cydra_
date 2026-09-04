"""Canonical semantic binding for explicit security predicates.

A security predicate is not trusted merely because a claim names compatible node IDs.
Its canonical graph binding must connect the exact hypothesis to the exact predicate,
the predicate to each exact required invariant, and the predicate to the exact causal
trace. Each required invariant must also semantically inform the exact claim hypothesis.
Verification is derived from the referenced canonical state and never from historical
benchmark truth.
"""
from __future__ import annotations

from dataclasses import dataclass

from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
from .reasoning_graph import ReasoningGraph


SECURITY_PREDICATE_KIND = "security_predicate"
HYPOTHESIS_PREDICATE_RELATION = "asserts_security_predicate"
INVARIANT_PREDICATE_RELATION = "grounds_invariant"
INVARIANT_HYPOTHESIS_RELATION = "informs"
TRACE_PREDICATE_RELATION = "verified_by_trace"


@dataclass(frozen=True)
class SecurityPredicateVerification:
    """Result of verifying one canonical security-predicate binding."""

    verified: bool
    reasons: tuple[str, ...] = ()


def verify_security_predicate(
    graph: ReasoningGraph,
    predicate_id: str,
    hypothesis_id: str,
    invariant_ids: tuple[str, ...],
    causal_chain_id: str,
) -> SecurityPredicateVerification:
    """Verify exact semantic edges and referenced verification state.

    A predicate succeeds only when the graph itself proves the complete binding:

        hypothesis -> security_predicate -> invariant(s)
        invariant(s) -> informs -> exact hypothesis
        security_predicate -> causal_chain

    The causal trace must independently verify to the same hypothesis. Every required
    invariant must be supported and semantically bound to the exact claim hypothesis,
    and the predicate must be explicitly marked verified.
    """

    if not isinstance(graph, ReasoningGraph):
        raise TypeError("security predicate verification requires the canonical ReasoningGraph")
    if not predicate_id.strip():
        return SecurityPredicateVerification(False, ("security predicate ID is empty",))
    if not hypothesis_id.strip():
        return SecurityPredicateVerification(False, ("security predicate hypothesis ID is empty",))
    if not causal_chain_id.strip():
        return SecurityPredicateVerification(False, ("security predicate causal chain ID is empty",))
    if not invariant_ids:
        return SecurityPredicateVerification(False, ("security predicate requires at least one invariant",))

    predicate = graph.model.nodes.get(predicate_id)
    if predicate is None or predicate.kind != SECURITY_PREDICATE_KIND:
        return SecurityPredicateVerification(False, ("security predicate is not canonical",))
    if predicate.attributes.get("verification_state") != "verified":
        return SecurityPredicateVerification(False, ("security predicate is not verified",))

    hypothesis = graph.model.nodes.get(hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        return SecurityPredicateVerification(False, ("security predicate hypothesis is not canonical",))
    if hypothesis.attributes.get("state") != "supported":
        return SecurityPredicateVerification(False, ("security predicate hypothesis is not supported",))

    hypothesis_edges = [
        edge
        for edge in graph.model.edges
        if edge.relation == HYPOTHESIS_PREDICATE_RELATION
        and edge.source == hypothesis_id
        and edge.target == predicate_id
    ]
    if len(hypothesis_edges) != 1:
        return SecurityPredicateVerification(
            False,
            ("security predicate is not uniquely asserted by the exact claim hypothesis",),
        )

    for invariant_id in invariant_ids:
        invariant = graph.model.nodes.get(invariant_id)
        if invariant is None or invariant.kind != "invariant":
            return SecurityPredicateVerification(
                False,
                (f"required invariant is not canonical: {invariant_id}",),
            )
        state = invariant.attributes.get("verification_state")
        if state == "contradicted":
            return SecurityPredicateVerification(
                False,
                (f"required invariant is contradicted: {invariant_id}",),
            )
        if state != "supported":
            return SecurityPredicateVerification(
                False,
                (f"required invariant is not supported: {invariant_id}",),
            )

        predicate_edges = [
            edge
            for edge in graph.model.edges
            if edge.relation == INVARIANT_PREDICATE_RELATION
            and edge.source == predicate_id
            and edge.target == invariant_id
        ]
        if len(predicate_edges) != 1:
            return SecurityPredicateVerification(
                False,
                (f"security predicate is not uniquely bound to required invariant: {invariant_id}",),
            )

        semantic_edges = [
            edge
            for edge in graph.model.edges
            if edge.relation == INVARIANT_HYPOTHESIS_RELATION
            and edge.source == invariant_id
            and edge.target == hypothesis_id
        ]
        if len(semantic_edges) != 1:
            return SecurityPredicateVerification(
                False,
                (f"required invariant is not semantically bound to the exact claim hypothesis: {invariant_id}",),
            )

        contradiction_edges = [
            edge
            for edge in graph.model.edges
            if edge.relation == "contradicts"
            and edge.source == invariant_id
            and edge.target == hypothesis_id
        ]
        if contradiction_edges:
            return SecurityPredicateVerification(
                False,
                (f"required invariant contradicts the exact claim hypothesis: {invariant_id}",),
            )

    trace_edges = [
        edge
        for edge in graph.model.edges
        if edge.relation == TRACE_PREDICATE_RELATION
        and edge.source == predicate_id
        and edge.target == causal_chain_id
    ]
    if len(trace_edges) != 1:
        return SecurityPredicateVerification(
            False,
            ("security predicate is not uniquely bound to the exact causal trace",),
        )

    verification = verify_persisted_causal_chain(graph.model, causal_chain_id)
    if verification.state == CausalVerificationState.REJECTED:
        reason = verification.reasons[0] if verification.reasons else "causal chain rejected"
        return SecurityPredicateVerification(False, (f"causal trace is rejected: {reason}",))
    if verification.state == CausalVerificationState.UNRESOLVED:
        reason = verification.reasons[0] if verification.reasons else "causal chain unresolved"
        return SecurityPredicateVerification(False, (f"causal trace is unresolved: {reason}",))
    if verification.trace is None:
        return SecurityPredicateVerification(False, ("verified causal trace has no trace payload",))
    if verification.trace.hypothesis_id != hypothesis_id:
        return SecurityPredicateVerification(
            False,
            ("security predicate causal trace does not match the exact claim hypothesis",),
        )

    return SecurityPredicateVerification(True)
