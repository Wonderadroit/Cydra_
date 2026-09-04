import pytest

from cydra.foundry import FoundryAuthorization, FoundryResult, result_to_evidence
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator


AUTHORIZATION = FoundryAuthorization("test-execution-binding")


def _result(execution_id):
    return FoundryResult(
        command=("forge", "test", "--match-test", "testInvariant"),
        returncode=0,
        stdout="passed",
        stderr="",
        authorization_id=AUTHORIZATION.authorization_id,
        scope_status=AUTHORIZATION.scope_status,
        execution_id=execution_id,
    )


def _hypothesis():
    return Hypothesis(
        "balance_invariant_holds",
        0.5,
        {"check": {"PASS": 0.9, "FAIL": 0.1}},
    )


def test_planned_observation_gets_stable_execution_identity():
    observation = Observation("check", ["PASS", "FAIL"], 1.0)
    assert observation.planned_execution_id
    assert observation.planned_execution_id == observation.execution_id


def test_external_result_must_match_planned_execution_identity():
    orchestrator = ReasoningOrchestrator()
    observation = Observation("check", ["PASS", "FAIL"], 1.0)
    plan = Plan("check", 1.0, 1.0, "test")
    orchestrator.record_authorized_plan(plan, [_hypothesis()], observation)

    with pytest.raises(ValueError, match="execution identity does not match"):
        orchestrator.ingest_observation_result(
            _result("execution:wrong"),
            observation,
            [_hypothesis()],
            "evidence:mismatch",
        )

    assert "evidence:evidence:mismatch" not in orchestrator.model.nodes


def test_matching_external_result_is_ingested():
    orchestrator = ReasoningOrchestrator()
    observation = Observation("check", ["PASS", "FAIL"], 1.0)
    plan = Plan("check", 1.0, 1.0, "test")
    orchestrator.record_authorized_plan(plan, [_hypothesis()], observation)

    update = orchestrator.ingest_observation_result(
        _result(observation.planned_execution_id),
        observation,
        [_hypothesis()],
        "evidence:match",
    )

    assert update.evidence_node_id == "evidence:evidence:match"
    assert orchestrator.model.nodes["evidence:evidence:match"].attributes["value"]["execution_id"] == observation.planned_execution_id


def test_foundry_evidence_rejects_missing_execution_identity():
    result = _result(None)
    with pytest.raises(PermissionError, match="execution identity"):
        result_to_evidence(result, "evidence:missing-execution")
