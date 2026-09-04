import copy

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.foundry import FoundryAuthorization, FoundryResult, FoundryRunner
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.system_model import SystemModel
from cydra.updater import EvidencePolarity

AUTH = FoundryAuthorization("test-persistent-request")


def _request_and_observation():
    runner = FoundryRunner("tests/fixtures/foundry")
    request = runner.build_request(
        "testFuzz_TotalDepositsMustTrackOutstandingBalance",
        authorization=AUTH,
        execution_id="execution:persistent-request",
    )
    observation = Observation(
        "persistent_request_observation",
        ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"],
        1.0,
        execution_id=request.execution_id,
        execution_request=request,
    )
    hypothesis = Hypothesis(
        "vault invariant holds", 0.5,
        {observation.name: {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}},
    )
    return request, observation, hypothesis


def test_exact_execution_request_is_first_class_and_round_trips():
    request, observation, hypothesis = _request_and_observation()
    orchestrator = ReasoningOrchestrator()
    orchestrator.record_authorized_plan(
        Plan(observation.name, 1.0, 1.0, "persist exact request"), [hypothesis], observation
    )

    request_id = f"execution_request:{request.digest}"
    node = orchestrator.model.nodes[request_id]
    assert node.kind == "execution_request"
    assert node.attributes["digest"] == request.digest
    assert node.attributes["command"] == list(request.command)
    assert any(
        edge.source == f"observation:{observation.name}"
        and edge.relation == "executes_request"
        and edge.target == request_id
        for edge in orchestrator.model.edges
    )

    restored = SystemModel.from_dict(orchestrator.model.export())
    restored_request = ExecutionRequest.from_canonical_payload(
        restored.nodes[request_id].attributes, expected_digest=request.digest
    )
    assert restored_request == request


def test_persisted_request_tampering_fails_closed_at_ingestion():
    request, observation, hypothesis = _request_and_observation()
    orchestrator = ReasoningOrchestrator()
    orchestrator.record_authorized_plan(
        Plan(observation.name, 1.0, 1.0, "persist exact request"), [hypothesis], observation
    )
    request_id = f"execution_request:{request.digest}"
    tampered = copy.deepcopy(orchestrator.model.nodes[request_id].attributes)
    tampered["command"] = ["forge", "test", "--match-test", "differentTest"]
    orchestrator.model.nodes[request_id] = type(orchestrator.model.nodes[request_id])(
        request_id, "execution_request", request.digest, tampered
    )

    result = FoundryResult(
        command=request.command,
        returncode=0,
        stdout="",
        stderr="",
        project_dir=request.target,
        project_fingerprint=request.project_fingerprint,
        authorization_id=AUTH.authorization_id,
        scope_status=AUTH.scope_status,
        execution_id=request.execution_id,
        request_digest=request.digest,
    )
    with pytest.raises(ValueError, match="persisted execution request digest"):
        orchestrator.ingest_observation_result(
            result,
            observation,
            [hypothesis],
            "evidence:persistent-request",
            evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS},
        )


def test_missing_request_node_cannot_be_replaced_by_digest_only():
    request, observation, hypothesis = _request_and_observation()
    orchestrator = ReasoningOrchestrator()
    orchestrator.record_authorized_plan(
        Plan(observation.name, 1.0, 1.0, "persist exact request"), [hypothesis], observation
    )
    del orchestrator.model.nodes[f"execution_request:{request.digest}"]

    result = FoundryResult(
        command=request.command,
        returncode=0,
        stdout="",
        stderr="",
        project_dir=request.target,
        project_fingerprint=request.project_fingerprint,
        authorization_id=AUTH.authorization_id,
        scope_status=AUTH.scope_status,
        execution_id=request.execution_id,
        request_digest=request.digest,
    )
    with pytest.raises(ValueError, match="request is missing"):
        orchestrator.ingest_observation_result(
            result,
            observation,
            [hypothesis],
            "evidence:missing-request",
            evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS},
        )
