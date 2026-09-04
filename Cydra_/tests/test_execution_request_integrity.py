import hashlib
import json
import math

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.foundry import FoundryAuthorization, FoundryResult, FoundryRunner
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.system_model import Node
from cydra.updater import EvidencePolarity

AUTH = FoundryAuthorization("test-request-integrity")


def test_execution_request_digest_is_deterministic_and_sensitive_to_command():
    base = ExecutionRequest("execution:test", "foundry", "tests/fixtures/foundry", ("forge", "test", "--match-test", "testA"), "project:abc", AUTH.authorization_id)
    same = ExecutionRequest("execution:test", "foundry", "tests/fixtures/foundry", ("forge", "test", "--match-test", "testA"), "project:abc", AUTH.authorization_id)
    changed = ExecutionRequest("execution:test", "foundry", "tests/fixtures/foundry", ("forge", "test", "--match-test", "testB"), "project:abc", AUTH.authorization_id)
    assert base.digest == same.digest
    assert base.digest != changed.digest


def test_execution_request_freezes_nested_parameters_and_preserves_sequences():
    parameters = {"nested": {"items": ["alpha", "beta"]}, "pairs": [("a", 1), ("b", 2)]}
    request = ExecutionRequest("execution:immutable", "fake", "target", ("tool",), "project:abc", AUTH.authorization_id, parameters=parameters)
    original_digest = request.digest
    parameters["nested"]["items"].append("tampered")
    parameters["pairs"].append(("c", 3))
    assert request.digest == original_digest
    assert request.canonical_payload()["parameters"] == {"nested": {"items": ["alpha", "beta"]}, "pairs": [["a", 1], ["b", 2]]}
    with pytest.raises(TypeError):
        request.parameters["new"] = "value"


def test_execution_request_rejects_non_string_mapping_keys():
    with pytest.raises(TypeError, match="mapping keys must be strings"):
        ExecutionRequest("execution:key", "fake", "target", ("tool",), "project:abc", AUTH.authorization_id, parameters={1: "ambiguous"})


def test_execution_request_rejects_non_finite_numbers():
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(TypeError, match="finite numbers"):
            ExecutionRequest("execution:number", "fake", "target", ("tool",), "project:abc", AUTH.authorization_id, parameters={"value": value})


def test_foundry_runner_rejects_mismatched_request_digest():
    runner = FoundryRunner("tests/fixtures/foundry")
    request = runner.build_request("testFuzz_TotalDepositsMustTrackOutstandingBalance", authorization=AUTH, execution_id="execution:request-integrity")
    with pytest.raises(ValueError, match="request_digest"):
        runner.run_test("testFuzz_TotalDepositsMustTrackOutstandingBalance", authorization=AUTH, execution_id="execution:request-integrity", request_digest=request.digest + "-tampered")


def test_ingestion_rejects_result_when_request_digest_differs():
    runner = FoundryRunner("tests/fixtures/foundry")
    request = runner.build_request("testFuzz_TotalDepositsMustTrackOutstandingBalance", authorization=AUTH, execution_id="execution:bound")
    observation = Observation("foundry_bound_observation", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0, execution_id="execution:bound", execution_request=request)
    hypothesis = Hypothesis("vault invariant holds", 0.5, {observation.name: {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.record_authorized_plan(Plan(observation.name, 1.0, 1.0, "test"), [hypothesis], observation)
    result = FoundryResult(command=request.command, returncode=0, stdout="", stderr="", project_dir=request.target, project_fingerprint=request.project_fingerprint, authorization_id=AUTH.authorization_id, scope_status=AUTH.scope_status, execution_id=observation.execution_id, request_digest=request.digest + "-tampered")
    with pytest.raises(ValueError, match="request digest"):
        orchestrator.ingest_observation_result(result, observation, [hypothesis], "evidence:request-integrity", evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS})


def test_matching_request_digest_is_ingested_and_persisted():
    runner = FoundryRunner("tests/fixtures/foundry")
    request = runner.build_request("testFuzz_TotalDepositsMustTrackOutstandingBalance", authorization=AUTH, execution_id="execution:bound-ok")
    observation = Observation("foundry_bound_observation", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0, execution_id="execution:bound-ok", execution_request=request)
    hypothesis = Hypothesis("vault invariant holds", 0.5, {observation.name: {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.record_authorized_plan(Plan(observation.name, 1.0, 1.0, "test"), [hypothesis], observation)
    result = FoundryResult(command=request.command, returncode=0, stdout="", stderr="", project_dir=request.target, project_fingerprint=request.project_fingerprint, authorization_id=AUTH.authorization_id, scope_status=AUTH.scope_status, execution_id=observation.execution_id, request_digest=request.digest)
    payload = result.canonical_payload()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    orchestrator.model.add_node(Node(
        f"execution_result:{request.digest}",
        "execution_result",
        request.digest,
        {
            "execution_id": request.execution_id,
            "request_digest": request.digest,
            "adapter": request.adapter,
            "payload": payload,
            "fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        },
    ))
    update = orchestrator.ingest_observation_result(result, observation, [hypothesis], "evidence:request-integrity-ok", evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS})
    assert update.evidence_node_id == "evidence:evidence:request-integrity-ok"
    assert orchestrator.model.nodes[f"execution_request:{request.digest}"].attributes["digest"] == request.digest
