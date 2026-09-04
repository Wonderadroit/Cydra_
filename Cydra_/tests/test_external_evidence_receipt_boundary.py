import pytest

from cydra.execution_request import ExecutionRequest
from cydra.foundry import FoundryAuthorization, FoundryResult
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator


def test_external_result_ingestion_requires_durable_receipt():
    authorization = FoundryAuthorization("auth-receipt-boundary")
    request = ExecutionRequest(
        execution_id="exec-receipt-boundary",
        adapter="foundry",
        target="fixture",
        command=("forge", "test"),
        project_fingerprint="project:fixture",
        authorization_id=authorization.authorization_id,
    )
    observation = Observation(
        "receipt-check",
        ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"],
        1.0,
        authorized=True,
        execution_id=request.execution_id,
        execution_request_digest=request.digest,
        execution_request=request,
    )
    hypothesis = Hypothesis(
        "receipt-bound hypothesis",
        0.5,
        {observation.name: {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}},
    )
    orchestrator = ReasoningOrchestrator()
    orchestrator.record_authorized_plan(
        Plan(observation.name, 1.0, 1.0, "receipt boundary"),
        [hypothesis],
        observation,
    )

    result = FoundryResult(
        ("forge", "test"),
        0,
        "ok",
        "",
        authorization_id=authorization.authorization_id,
        scope_status=authorization.scope_status,
        execution_id=request.execution_id,
        request_digest=request.digest,
    )

    with pytest.raises(RuntimeError, match="durable result receipt"):
        orchestrator.ingest_observation_result(
            result,
            observation,
            [hypothesis],
            "receipt-boundary",
        )

    assert "evidence:receipt-boundary" not in orchestrator.model.nodes
    assert not any(node.kind == "belief" for node in orchestrator.model.nodes.values())
