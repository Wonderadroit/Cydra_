from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from cydra.causal_verification import CausalVerificationState
from cydra.evidence import Evidence, EvidenceKind, Provenance
from cydra.execution_causal_adapter import ExecutionCausalEvidenceAdapter
from cydra.planner import Hypothesis, Observation
from cydra.reasoning_graph import GraphUpdate, ReasoningGraph
from cydra.system_model import Node, SystemModel
from cydra.updater import EvidencePolarity


@dataclass(frozen=True)
class Result:
    execution_id: str = "execution:adapter-1"
    request_digest: str = "request-digest"
    outcome: str = "NO_COUNTEREXAMPLE"
    authorization_id: str = "auth-1"
    scope_status: str = "AUTHORIZED_EXECUTION"
    finished_at: str = "2026-09-03T17:00:00+00:00"

    def canonical_payload(self):
        return {"execution_id": self.execution_id, "request_digest": self.request_digest, "outcome": self.outcome}


def _graph():
    model = SystemModel()
    hypothesis = Hypothesis(
        "security:reentrancy:Vault:withdraw:totalAssets",
        0.9,
        {"verify:security:reentrancy:Vault:withdraw:totalAssets": {"CALLBACK_CONFIRMED": 0.8, "CALLBACK_NOT_REPRODUCED": 0.15, "INCONCLUSIVE": 0.05}},
    )
    observation = Observation(
        "verify:security:reentrancy:Vault:withdraw:totalAssets",
        ["CALLBACK_CONFIRMED", "CALLBACK_NOT_REPRODUCED", "INCONCLUSIVE"],
        1.0,
        execution_id="execution:adapter-1",
    )
    graph = ReasoningGraph(model)
    graph.add_hypotheses([hypothesis])
    graph.add_observation(observation)
    graph.model.nodes[hypothesis.hypothesis_id] = Node(
        hypothesis.hypothesis_id,
        "hypothesis",
        hypothesis.name,
        {"security_claim": {"claim_kind": "security_hypothesis", "statement": "test", "mechanism": "test", "affected_components": ["Vault"]}},
    )
    graph.model.nodes["observation:" + observation.name] = Node(
        "observation:" + observation.name,
        "observation",
        observation.name,
        {"planned": True, "authorized": True, "execution_id": observation.execution_id, "execution_request_digest": "request-digest"},
    )
    evidence = Evidence(
        "execution-observation:execution:adapter-1",
        EvidenceKind.TEST_RESULT,
        {"outcome": "NO_COUNTEREXAMPLE"},
        Provenance("execution:execution:adapter-1", datetime.now(timezone.utc), "test", "AUTHORIZED_EXECUTION", {"execution_id": observation.execution_id}),
        "observed",
    )
    evidence_id = graph.add_evidence(evidence)
    belief_id = "belief:adapter-1"
    graph.model.add_node(Node(belief_id, "belief", belief_id, {"hypothesis_id": hypothesis.hypothesis_id}))
    return graph, hypothesis, observation, evidence_id, belief_id


def _update(graph, observation, evidence_id, belief_id):
    return GraphUpdate("observation:" + observation.name, [belief_id], evidence_id, None)


def _interpreter(result, observation, hypotheses):
    return "CALLBACK_CONFIRMED", {hypotheses[0].hypothesis_id: EvidencePolarity.SUPPORTS}


def _bind_and_finalize(adapter, result, graph, hypothesis, observation, evidence_id, belief_id):
    adapter.bind(result, observation, [hypothesis])
    return adapter.finalize(result, observation, [hypothesis], _update(graph, observation, evidence_id, belief_id))


def test_explicit_interpretation_builds_and_verifies_causal_chain():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()
    adapter = ExecutionCausalEvidenceAdapter(graph, _interpreter)
    state = _bind_and_finalize(adapter, Result(outcome="CALLBACK_CONFIRMED"), graph, hypothesis, observation, evidence_id, belief_id)
    assert state == CausalVerificationState.VERIFIED
    assert "causal:execution:execution:adapter-1" in graph.model.nodes
    assert any(edge.relation == "supports" and edge.target == hypothesis.hypothesis_id for edge in graph.model.edges)


def test_interpreter_runs_exactly_once_and_finalize_uses_captured_meaning():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()
    calls = []

    def interpreter(result, observation, hypotheses):
        calls.append(result.outcome)
        return ("CALLBACK_CONFIRMED" if len(calls) == 1 else "INCONCLUSIVE"), {hypotheses[0].hypothesis_id: EvidencePolarity.SUPPORTS}

    adapter = ExecutionCausalEvidenceAdapter(graph, interpreter)
    state = _bind_and_finalize(adapter, Result(outcome="CALLBACK_CONFIRMED"), graph, hypothesis, observation, evidence_id, belief_id)
    assert state == CausalVerificationState.VERIFIED
    assert calls == ["CALLBACK_CONFIRMED"]


def test_raw_success_does_not_become_security_proof_without_explicit_support():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()

    def interpreter(result, observation, hypotheses):
        return "INCONCLUSIVE", {hypotheses[0].hypothesis_id: EvidencePolarity.NEUTRAL}

    adapter = ExecutionCausalEvidenceAdapter(graph, interpreter)
    state = _bind_and_finalize(adapter, Result(outcome="NO_COUNTEREXAMPLE"), graph, hypothesis, observation, evidence_id, belief_id)
    assert state == CausalVerificationState.UNRESOLVED
    assert not any(edge.relation == "supports" and edge.target == hypothesis.hypothesis_id for edge in graph.model.edges)


def test_contradictory_execution_cannot_promote_security_claim():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()

    def interpreter(result, observation, hypotheses):
        return "CALLBACK_NOT_REPRODUCED", {hypotheses[0].hypothesis_id: EvidencePolarity.CONTRADICTS}

    adapter = ExecutionCausalEvidenceAdapter(graph, interpreter)
    state = _bind_and_finalize(adapter, Result(outcome="CALLBACK_NOT_REPRODUCED"), graph, hypothesis, observation, evidence_id, belief_id)
    assert state == CausalVerificationState.UNRESOLVED
    claim = graph.model.nodes[hypothesis.hypothesis_id].attributes["security_claim"]
    assert "causal_chain_id" not in claim
    assert not any(edge.relation == "supports" and edge.target == hypothesis.hypothesis_id for edge in graph.model.edges)


def test_mismatched_execution_identity_is_rejected_before_interpretation():
    graph, hypothesis, observation, _, _ = _graph()
    calls = []

    def interpreter(result, observation, hypotheses):
        calls.append(1)
        return "CALLBACK_CONFIRMED", {hypotheses[0].hypothesis_id: EvidencePolarity.SUPPORTS}

    adapter = ExecutionCausalEvidenceAdapter(graph, interpreter)
    with pytest.raises(ValueError, match="identity"):
        adapter.bind(Result(execution_id="execution:wrong"), observation, [hypothesis])
    assert calls == []


def test_mismatched_request_digest_is_rejected_before_interpretation():
    graph, hypothesis, observation, _, _ = _graph()
    calls = []

    def interpreter(result, observation, hypotheses):
        calls.append(1)
        return "CALLBACK_CONFIRMED", {hypotheses[0].hypothesis_id: EvidencePolarity.SUPPORTS}

    adapter = ExecutionCausalEvidenceAdapter(graph, interpreter)
    with pytest.raises(ValueError, match="request digest"):
        adapter.bind(Result(request_digest="tampered"), observation, [hypothesis])
    assert calls == []


def test_finalize_requires_the_exact_prior_binding():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()
    adapter = ExecutionCausalEvidenceAdapter(graph, _interpreter)
    with pytest.raises(ValueError, match="prior bind"):
        adapter.finalize(Result(), observation, [hypothesis], _update(graph, observation, evidence_id, belief_id))


def test_binding_cannot_be_reused_after_finalization():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()
    adapter = ExecutionCausalEvidenceAdapter(graph, _interpreter)
    result = Result(outcome="CALLBACK_CONFIRMED")
    _bind_and_finalize(adapter, result, graph, hypothesis, observation, evidence_id, belief_id)
    with pytest.raises(ValueError, match="already been causally bound"):
        adapter.bind(result, observation, [hypothesis])


def test_finalization_cannot_be_replayed_after_success():
    graph, hypothesis, observation, evidence_id, belief_id = _graph()
    adapter = ExecutionCausalEvidenceAdapter(graph, _interpreter)
    result = Result(outcome="CALLBACK_CONFIRMED")
    _bind_and_finalize(adapter, result, graph, hypothesis, observation, evidence_id, belief_id)
    with pytest.raises(ValueError, match="prior bind"):
        adapter.finalize(result, observation, [hypothesis], _update(graph, observation, evidence_id, belief_id))
