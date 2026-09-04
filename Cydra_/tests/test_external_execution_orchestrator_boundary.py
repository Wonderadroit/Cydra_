from dataclasses import dataclass

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionAdapter
from cydra.foundry import FoundryAuthorization
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator


@dataclass(frozen=True)
class Result:
    execution_id: str
    request_digest: str
    outcome: str

    def canonical_payload(self):
        return {"execution_id": self.execution_id, "request_digest": self.request_digest, "outcome": self.outcome}


class Adapter:
    def __init__(self):
        self.calls = 0
        self.gateway_capability = None

    def _bind_gateway_capability(self, capability):
        if self.gateway_capability is not None and self.gateway_capability is not capability:
            raise RuntimeError("adapter is already bound to a different gateway")
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization, command=None):
        return ExecutionRequest(execution_id, "fake", "fixture", ("fake", "check"), "project:fixture", authorization.authorization_id)

    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.calls += 1
        return Result(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")

    def rehydrate_result(self, *, payload, request):
        return Result(payload["execution_id"], payload["request_digest"], payload["outcome"])


def test_orchestrator_executes_only_the_persisted_canonical_request():
    authorization = FoundryAuthorization("auth-boundary")
    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-boundary", authorization=authorization)
    observation = Observation(
        "boundary-check", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0,
        authorized=True, execution_id=request.execution_id, execution_request=request,
    )
    hypothesis = Hypothesis(
        "boundary hypothesis", 0.5,
        {observation.name: {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}},
    )
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan(observation.name, 1.0, 1.0, "authorized test"), [hypothesis], observation)

    result = orchestrator.execute_external_observation("fake", observation, authorization=authorization)

    assert adapter.calls == 1
    assert result.execution_id == request.execution_id
    assert result.request_digest == request.digest
    request_node = orchestrator.model.nodes[f"execution_request:{request.digest}"]
    result_node = orchestrator.model.nodes[f"execution_result:{request.digest}"]
    assert request_node.attributes["execution_state"] == "COMPLETED"
    assert result_node.kind == "execution_result"
    assert result_node.attributes["request_digest"] == request.digest


def test_orchestrator_rejects_execution_without_persisted_request():
    authorization = FoundryAuthorization("auth-missing")
    observation = Observation(
        "missing-request", ["NO_COUNTEREXAMPLE"], 1.0,
        authorized=True, execution_id="exec-missing",
    )
    hypothesis = Hypothesis("missing hypothesis", 0.5, {observation.name: {"NO_COUNTEREXAMPLE": 1.0}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", Adapter())
    orchestrator.record_authorized_plan(Plan(observation.name, 1.0, 1.0, "authorized test"), [hypothesis], observation)
    try:
        orchestrator.execute_external_observation("fake", observation, authorization=authorization)
    except ValueError as exc:
        assert "execution identity and request digest" in str(exc)
    else:
        raise AssertionError("execution without a canonical request must fail closed")


def test_orchestrator_rejects_result_substitution_before_evidence_ingestion():
    """Evidence ingestion must consume only the durable result receipt, not a forged in-memory result."""
    authorization = FoundryAuthorization("auth-receipt")
    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-receipt", authorization=authorization)
    observation = Observation(
        "receipt-boundary", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0,
        authorized=True, execution_id=request.execution_id, execution_request=request,
    )
    hypothesis = Hypothesis(
        "receipt hypothesis", 0.5,
        {observation.name: {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}},
    )
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan(observation.name, 1.0, 1.0, "authorized test"), [hypothesis], observation)
    canonical_result = orchestrator.execute_external_observation("fake", observation, authorization=authorization)
    forged_result = Result(canonical_result.execution_id, canonical_result.request_digest, "COUNTEREXAMPLE")

    try:
        orchestrator.ingest_observation_result(forged_result, observation, [hypothesis], "evidence:forged")
    except RuntimeError as exc:
        assert "durable canonical receipt" in str(exc)
    else:
        raise AssertionError("forged result must not become reasoning evidence")

    assert "evidence:forged" not in orchestrator.model.nodes


assert isinstance(Adapter(), ExternalExecutionAdapter)
