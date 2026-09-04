from dataclasses import replace

import pytest

from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.hypotheses import HypothesisState
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.planner import Plan
from cydra.reasoning_graph import ReasoningGraph
from cydra.security_reasoning import (
    SecurityReasoningInputs,
    VerifiedSecurityClaim,
    emit_verified_security_claims,
    persist_security_claims,
    persist_verified_security_claim,
    security_reasoning_inputs,
)
from cydra.system_model import Node
from cydra.updater import EvidencePolarity, update_hypotheses

from test_security_reasoning_hypothesis_binding import vulnerable_order_model


def prepared_graph():
    inputs = security_reasoning_inputs(vulnerable_order_model())
    graph = ReasoningGraph()
    graph.add_hypotheses(list(inputs.hypotheses))
    persist_security_claims(graph, inputs)
    observation = inputs.observations[0]
    graph.record_plan(
        Plan(
            observation=observation.name,
            expected_information_gain=1.0,
            utility=1.0,
            rationale="distinguish the explicit competing security hypotheses",
            discriminates_hypothesis_ids=observation.discriminates_hypothesis_ids,
        ),
        list(inputs.hypotheses),
        observation,
    )
    return graph, inputs


def add_verified_update(graph, inputs):
    primary, alternative = inputs.hypotheses
    outcome_id = "evidence:callback-confirmed"
    graph.model.add_node(Node(outcome_id, "evidence", "callback-confirmed", {}))
    updated = update_hypotheses(
        [
            replace(primary, state=HypothesisState.SUPPORTED),
            replace(alternative, state=HypothesisState.CONTRADICTED),
        ],
        inputs.observations[0].name,
        "CALLBACK_CONFIRMED",
        evidence_strength=1.0,
        evidence_polarity={
            primary.name: EvidencePolarity.SUPPORTS,
            alternative.name: EvidencePolarity.CONTRADICTS,
        },
    )
    update = graph.record_update(
        updated,
        f"observation:{inputs.observations[0].name}",
        outcome_id,
    )
    return primary, outcome_id, update.belief_node_ids[0]


def add_verified_causal_chain(graph, inputs, outcome_id, belief_id):
    verification_id = "evidence:callback-verification"
    graph.model.add_node(Node(verification_id, "evidence", "callback-verification", {}))
    graph.model.connect(outcome_id, "informs", verification_id, provenance="explicit_test")
    graph.model.connect(
        verification_id,
        "supports",
        inputs.hypotheses[0].hypothesis_id,
        provenance="explicit_test",
    )
    persist_causal_chain(
        graph.model,
        CausalChain(
            "causal:security-claim",
            inputs.hypotheses[0].hypothesis_id,
            f"observation:{inputs.observations[0].name}",
            outcome_id,
            verification_id,
            belief_id,
        ),
    )
    return verification_id


def security_finding(graph, inputs, claim):
    return Finding(
        finding_id="finding:security-claim",
        title="Verified security claim",
        summary="A verified security claim is ready for reporting.",
        severity="HIGH",
        impact=ImpactAssessment(
            ImpactLevel.HIGH,
            "asset:target",
            "security impact",
            evidence_ids=(claim.evidence_ids[0],),
        ),
        affected_components=("component:target",),
        evidence_ids=claim.evidence_ids,
        hypothesis_id=inputs.hypotheses[0].hypothesis_id,
        causal_chain_id=claim.causal_chain_id,
    )


def test_security_claim_is_not_emitted_from_probability_or_proposal_alone():
    graph, inputs = prepared_graph()
    assert isinstance(inputs, SecurityReasoningInputs)
    assert emit_verified_security_claims(graph, inputs) == ()


def test_security_claim_requires_verified_belief_transition_and_causal_chain():
    graph, inputs = prepared_graph()
    primary, outcome_id, belief_id = add_verified_update(graph, inputs)

    assert emit_verified_security_claims(graph, inputs) == ()

    verification_id = add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    emitted = emit_verified_security_claims(graph, inputs)

    assert len(emitted) == 1
    claim = emitted[0]
    assert claim.proposal.hypothesis_id == primary.hypothesis_id
    assert claim.causal_chain_id == "causal:security-claim"
    assert claim.evidence_ids == (outcome_id, verification_id)


def test_security_claim_emission_fails_closed_when_hypothesis_state_is_reopened():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)

    node = graph.model.nodes[inputs.hypotheses[0].hypothesis_id]
    graph.model.nodes[node.node_id] = Node(
        node.node_id,
        node.kind,
        node.label,
        {**node.attributes, "state": HypothesisState.UNRESOLVED.value},
    )

    assert emit_verified_security_claims(graph, inputs) == ()


def test_persisted_verified_claim_rejects_mismatched_causal_evidence():
    graph, inputs = prepared_graph()
    primary, outcome_id, belief_id = add_verified_update(graph, inputs)
    verification_id = add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    emitted = emit_verified_security_claims(graph, inputs)
    assert len(emitted) == 1
    valid = emitted[0]

    tampered = VerifiedSecurityClaim(
        valid.proposal,
        valid.causal_chain_id,
        (verification_id, outcome_id),
    )
    with pytest.raises(ValueError, match="evidence references do not match canonical causal chain"):
        persist_verified_security_claim(graph, tampered)


def test_persisted_verified_claim_rejects_mismatched_observation():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    valid = emit_verified_security_claims(graph, inputs)[0]

    tampered = VerifiedSecurityClaim(
        type(valid.proposal)(
            valid.proposal.hypothesis_id,
            "verify:unrelated-observation",
            valid.proposal.claim,
        ),
        valid.causal_chain_id,
        valid.evidence_ids,
    )
    with pytest.raises(ValueError, match="observation is not canonical"):
        persist_verified_security_claim(graph, tampered)


def test_finding_gate_rejects_tampered_verified_security_claim_payload():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    claim = emit_verified_security_claims(graph, inputs)[0]
    persist_verified_security_claim(graph, claim)
    finding = security_finding(graph, inputs, claim)

    node_id = f"security_claim:{claim.proposal.hypothesis_id}"
    node = graph.model.nodes[node_id]
    graph.model.nodes[node_id] = Node(
        node.node_id,
        node.kind,
        node.label,
        {**node.attributes, "claim": {**node.attributes["claim"], "impact": "tampered"}},
    )

    result = evaluate_finding_graph(
        graph,
        FindingCandidate(True, False, True, True, True, True, True),
        finding,
    )
    assert result.decision == GateDecision.BLOCKED
    assert result.reasons == ["security claim payload does not match canonical hypothesis metadata"]


def test_finding_gate_rejects_tampered_verified_security_claim_fingerprint():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    claim = emit_verified_security_claims(graph, inputs)[0]
    persist_verified_security_claim(graph, claim)
    finding = security_finding(graph, inputs, claim)

    node_id = f"security_claim:{claim.proposal.hypothesis_id}"
    node = graph.model.nodes[node_id]
    graph.model.nodes[node_id] = Node(
        node.node_id,
        node.kind,
        node.label,
        {**node.attributes, "claim_fingerprint": "tampered"},
    )

    result = evaluate_finding_graph(
        graph,
        FindingCandidate(True, False, True, True, True, True, True),
        finding,
    )
    assert result.decision == GateDecision.BLOCKED
    assert result.reasons == ["security claim fingerprint does not match canonical claim payload"]
