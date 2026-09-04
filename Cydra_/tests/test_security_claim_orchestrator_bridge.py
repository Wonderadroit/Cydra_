import pytest

from cydra.security_claim_orchestrator import finalize_verified_security_claims
from cydra.security_reasoning import SecurityReasoningInputs
from cydra.reasoning_orchestrator import ReasoningOrchestrator

from test_security_claim_emission import (
    add_verified_causal_chain,
    add_verified_update,
    prepared_graph,
)


def _orchestrator_for_graph(graph):
    orchestrator = ReasoningOrchestrator()
    orchestrator.graph = graph
    return orchestrator


def test_orchestrator_bridge_is_fail_closed_until_causal_verification():
    graph, inputs = prepared_graph()
    orchestrator = _orchestrator_for_graph(graph)

    assert isinstance(inputs, SecurityReasoningInputs)
    assert finalize_verified_security_claims(orchestrator, inputs) == ()
    assert not any(node.kind == "security_claim" for node in graph.model.nodes.values())


def test_orchestrator_bridge_persists_only_verified_claims_and_is_idempotent():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    orchestrator = _orchestrator_for_graph(graph)

    claim_ids = finalize_verified_security_claims(orchestrator, inputs)
    assert claim_ids == (f"security_claim:{inputs.hypotheses[0].hypothesis_id}",)
    assert orchestrator.model.nodes[claim_ids[0]].attributes["verified"] is True

    event_count = sum(
        1
        for event in orchestrator.graph.history
        if event.get("type") == "VERIFIED_SECURITY_CLAIM_PERSISTED"
    )
    assert event_count == 1

    assert finalize_verified_security_claims(orchestrator, inputs) == claim_ids
    assert sum(
        1
        for event in orchestrator.graph.history
        if event.get("type") == "VERIFIED_SECURITY_CLAIM_PERSISTED"
    ) == event_count


def test_orchestrator_bridge_rejects_invalid_inputs():
    with pytest.raises(TypeError, match="SecurityReasoningInputs"):
        finalize_verified_security_claims(ReasoningOrchestrator(), object())
