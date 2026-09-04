from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.reasoning_graph import ReasoningGraph
from cydra.security_reasoning import emit_verified_security_claims, persist_verified_security_claim
from cydra.system_model import SystemModel

from test_security_claim_emission import (
    add_verified_causal_chain,
    add_verified_update,
    prepared_graph,
    security_finding,
)


def test_verified_security_claim_survives_export_reload_and_remains_reportable():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    claim = emit_verified_security_claims(graph, inputs)[0]
    persist_verified_security_claim(graph, claim)
    finding = security_finding(graph, inputs, claim)

    restored = ReasoningGraph.from_state_dict(graph.export_state())
    result = evaluate_finding_graph(
        restored,
        FindingCandidate(True, False, True, True, True, True, True),
        finding,
    )

    assert result.decision == GateDecision.READY
    assert result.reasons == []


def test_reloaded_security_claim_payload_tampering_is_blocked_by_finding_gate():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    claim = emit_verified_security_claims(graph, inputs)[0]
    persist_verified_security_claim(graph, claim)
    finding = security_finding(graph, inputs, claim)

    payload = graph.export_state()
    claim_node = next(
        node
        for node in payload["model"]["nodes"]
        if node["id"] == f"security_claim:{claim.proposal.hypothesis_id}"
    )
    claim_node["attributes"]["claim"]["impact"] = "tampered"

    # Simulate a replay layer that recomputes the outer integrity fields after
    # mutating canonical state. The finding gate must still reject the claim.
    restored_model = SystemModel.from_dict(payload["model"])
    latest = payload["history"][-1]
    latest["state_digest"] = ReasoningGraph._state_digest(restored_model)
    latest["event_hash"] = ReasoningGraph._audit_digest(latest)

    restored = ReasoningGraph.from_state_dict(payload)
    result = evaluate_finding_graph(
        restored,
        FindingCandidate(True, False, True, True, True, True, True),
        finding,
    )

    assert result.decision == GateDecision.BLOCKED
    assert result.reasons == ["security claim payload does not match canonical hypothesis metadata"]
