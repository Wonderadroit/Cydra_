from datetime import datetime, timezone
import hashlib
import json

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.foundry import FoundryResult, result_to_evidence
from cydra.hypotheses import HypothesisState
from cydra.planner import Hypothesis, Observation
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.system_model import Node, SystemModel
from cydra.updater import EvidencePolarity


def _request():
    return ExecutionRequest(execution_id="recovery-exec-001", adapter="foundry", target="/fixture", command=("forge", "test"), project_fingerprint="project:fixture", authorization_id="recovery-auth", scope_status="AUTHORIZED_EXECUTION")


def _result(request):
    return FoundryResult(command=request.command, returncode=0, stdout="ok", stderr="", started_at="2026-09-02T12:00:00+00:00", finished_at="2026-09-02T12:00:01+00:00", duration_seconds=1.0, project_dir=request.target, project_fingerprint=request.project_fingerprint, forge_version="forge 1.0.0", authorization_id=request.authorization_id, scope_status=request.scope_status, execution_id=request.execution_id, timed_out=False, request_digest=request.digest)


def _receipt_node(request, result):
    payload = result.canonical_payload()
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return Node(f"execution_result:{request.digest}", "execution_result", request.digest, {"execution_id": request.execution_id, "request_digest": request.digest, "adapter": request.adapter, "payload": payload, "fingerprint": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()})


def _fixture():
    request = _request(); result = _result(request); model = SystemModel(); observation_id = "observation:check"; request_id = f"execution_request:{request.digest}"
    hypothesis = Hypothesis(name="vault-preserves-balance", probability=0.7, predictions={"check": {"NO_COUNTEREXAMPLE": 1.0, "COUNTEREXAMPLE": 0.0}}, state=HypothesisState.UNRESOLVED)
    model.add_node(Node(observation_id, "observation", "check", {"planned": True, "authorized": True, "execution_id": request.execution_id, "execution_request_digest": request.digest}))
    model.add_node(Node(request_id, "execution_request", request.digest, {**request.canonical_payload(), "digest": request.digest, "execution_state": "OUTCOME_UNRECORDED"}))
    model.add_node(_receipt_node(request, result)); model.connect(observation_id, "executes_request", request_id, provenance="explicit_execution_binding")
    model.add_node(Node(hypothesis.hypothesis_id, "hypothesis", hypothesis.name, {"probability": hypothesis.probability, "predictions": {name: dict(outcomes) for name, outcomes in hypothesis.predictions.items()}, "state": hypothesis.state.value, "subject_id": hypothesis.hypothesis_id}))
    orchestrator = ReasoningOrchestrator(model)
    observation = Observation(name="check", outcomes=["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], cost=1.0, authorized=True, execution_id=request.execution_id, execution_request_digest=request.digest)
    return orchestrator, request, observation, hypothesis


def test_recovery_retry_after_terminal_state_persistence_failure_is_idempotent():
    orchestrator, request, observation, hypothesis = _fixture(); result = _result(request); original_set_state = orchestrator._set_gateway_execution_state; calls = []
    def fail_completion(request_obj, state):
        if state == "COMPLETED" and not calls: calls.append("failed"); raise RuntimeError("simulated completion persistence crash")
        return original_set_state(request_obj, state)
    orchestrator.external_gateway._set_execution_state = fail_completion
    with pytest.raises(RuntimeError, match="simulated completion persistence crash"):
        orchestrator.reconcile_external_observation_result(result, observation, [hypothesis], "recovery-evidence-001", evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS})
    evidence_id = "evidence:recovery-evidence-001"; first_beliefs = [edge.target for edge in orchestrator.model.edges if edge.source == "observation:check" and edge.relation == "updates"]
    assert evidence_id in orchestrator.model.nodes; assert len(first_beliefs) == 1; assert orchestrator.model.nodes[f"execution_request:{request.digest}"].attributes["execution_state"] == "OUTCOME_UNRECORDED"
    orchestrator.external_gateway._set_execution_state = original_set_state
    update = orchestrator.reconcile_external_observation_result(result, observation, [hypothesis], "recovery-evidence-001", evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS})
    second_beliefs = [edge.target for edge in orchestrator.model.edges if edge.source == "observation:check" and edge.relation == "updates"]
    assert second_beliefs == first_beliefs; assert len([node for node in orchestrator.model.nodes.values() if node.kind == "evidence" and node.node_id == evidence_id]) == 1; assert update.belief_node_ids == first_beliefs; assert orchestrator.model.nodes[f"execution_request:{request.digest}"].attributes["execution_state"] == "COMPLETED"


def test_recovery_fails_closed_on_partial_belief_update():
    orchestrator, request, observation, hypothesis = _fixture()
    second = Hypothesis(name="vault-preserves-liquidity", probability=0.3, predictions={"check": {"NO_COUNTEREXAMPLE": 1.0, "COUNTEREXAMPLE": 0.0}}, state=HypothesisState.UNRESOLVED)
    orchestrator.model.add_node(Node(second.hypothesis_id, "hypothesis", second.name, {"probability": second.probability, "predictions": {name: dict(outcomes) for name, outcomes in second.predictions.items()}, "state": second.state.value, "subject_id": second.hypothesis_id}))
    result = _result(request); evidence_id = "recovery-evidence-partial"; orchestrator.graph.add_evidence(result_to_evidence(result, evidence_id)); belief_id = "belief:partial"
    orchestrator.model.add_node(Node(belief_id, "belief", hypothesis.name, {"hypothesis_id": hypothesis.hypothesis_id, "evidence_id": f"evidence:{evidence_id}", "causal_chain_id": None})); orchestrator.model.connect("observation:check", "updates", belief_id)
    with pytest.raises(RuntimeError, match="partial or ambiguous belief update"):
        orchestrator.reconcile_external_observation_result(result, observation, [hypothesis, second], evidence_id, evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS, second.name: EvidencePolarity.SUPPORTS})


def test_recovery_rejects_result_without_durable_evidence_receipt():
    orchestrator, request, observation, hypothesis = _fixture(); orchestrator.model.nodes.pop(f"execution_result:{request.digest}")
    with pytest.raises(RuntimeError, match="durable result receipt"):
        orchestrator.reconcile_external_observation_result(_result(request), observation, [hypothesis], "never-persisted", evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS})


def test_completed_execution_can_resume_reasoning_from_durable_result_receipt():
    orchestrator, request, observation, hypothesis = _fixture()
    orchestrator.model.nodes[f"execution_request:{request.digest}"] = Node(f"execution_request:{request.digest}", "execution_request", request.digest, {**request.canonical_payload(), "digest": request.digest, "execution_state": "COMPLETED"})
    update = orchestrator.reconcile_external_observation_result(_result(request), observation, [hypothesis], "completed-recovery", evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS})
    assert len(update.belief_node_ids) == 1; assert orchestrator.model.nodes[f"execution_request:{request.digest}"].attributes["execution_state"] == "COMPLETED"
