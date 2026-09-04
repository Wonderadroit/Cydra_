from dataclasses import dataclass

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionAdapter, ExternalExecutionGateway, require_external_execution_contract
from cydra.foundry import FoundryAuthorization, FoundryRunner
from cydra.planner import Observation
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.system_model import Node, SystemModel


@dataclass(frozen=True)
class FakeResult:
    execution_id: str
    request_digest: str | None
    outcome: str

    def canonical_payload(self):
        return {"execution_id": self.execution_id, "request_digest": self.request_digest, "outcome": self.outcome}


class FakeAdapter:
    def __init__(self, events):
        self.events = events
        self.gateway_capability = None

    def _bind_gateway_capability(self, capability):
        if self.gateway_capability is not None and self.gateway_capability is not capability:
            raise RuntimeError("adapter is already bound to a different gateway")
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization, command=None):
        return ExecutionRequest(execution_id=execution_id, adapter="fake", target="fixture", command=("fake", "check"), project_fingerprint="project:fixture", authorization_id=authorization.authorization_id)

    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.events.append("execute")
        return FakeResult(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")

    def rehydrate_result(self, *, payload, request):
        self.events.append("rehydrate")
        return FakeResult(payload["execution_id"], payload["request_digest"], payload["outcome"])


class TamperingRehydrateAdapter(FakeAdapter):
    def rehydrate_result(self, *, payload, request):
        self.events.append("rehydrate")
        return FakeResult(payload["execution_id"], payload["request_digest"], "NO_COUNTEREXAMPLE")


class WrongResultAdapter(FakeAdapter):
    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.events.append("execute")
        return FakeResult(request.execution_id, "execution-request:substituted", "NO_COUNTEREXAMPLE")


class InvalidResultAdapter(FakeAdapter):
    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.events.append("execute")
        return object()


class FailingAdapter(FakeAdapter):
    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.events.append("execute")
        raise RuntimeError("external infrastructure failure")


def request():
    return ExecutionRequest(execution_id="exec-001", adapter="fake", target="fixture", command=("fake", "check"), project_fingerprint="project:fixture", authorization_id="auth-001")


def auth():
    return FoundryAuthorization("auth-001")


def make_gateway(events, states=None, persist_result=True, result_sink=None):
    sink = result_sink if result_sink is not None else ((lambda req, result: events.append("result")) if persist_result else None)
    return ExternalExecutionGateway(
        lambda req: events.append("persist"),
        (lambda req, state: states.__setitem__(req.digest, state)) if states is not None else None,
        (lambda req: states.get(req.digest)) if states is not None else None,
        sink,
    )


def test_gateway_requires_structural_adapter_contract():
    adapter = FakeAdapter([])
    assert isinstance(adapter, ExternalExecutionAdapter)
    assert require_external_execution_contract(adapter) is adapter


def test_gateway_persists_before_external_execution_and_validates_result():
    events = []
    gateway = make_gateway(events)
    gateway.register("fake", FakeAdapter(events))
    result = gateway.execute("fake", request(), authorization=auth())
    assert result.request_digest == request().digest
    assert events == ["persist", "execute", "result"]


def test_gateway_persists_lifecycle_in_order():
    events = []
    states = {}
    gateway = make_gateway(events, states)
    gateway.register("fake", FakeAdapter(events))
    gateway.execute("fake", request(), authorization=auth())
    assert states[request().digest] == "COMPLETED"
    assert events == ["persist", "execute", "result"]


def test_gateway_rehydrates_recorded_receipt_without_execution():
    req = request()
    events = []
    states = {req.digest: "COMPLETED"}
    receipt = FakeResult(req.execution_id, req.digest, "NO_COUNTEREXAMPLE").canonical_payload()
    gateway = make_gateway(events, states)
    adapter = FakeAdapter(events)
    gateway.register("fake", adapter)
    result = gateway.rehydrate_result("fake", req, receipt)
    assert result.canonical_payload() == receipt
    assert events == ["rehydrate"]


def test_gateway_rehydration_rejects_tampered_receipt():
    req = request()
    states = {req.digest: "COMPLETED"}
    receipt = FakeResult(req.execution_id, req.digest, "COUNTEREXAMPLE").canonical_payload()
    events = []
    gateway = make_gateway(events, states)
    gateway.register("fake", TamperingRehydrateAdapter(events))
    with pytest.raises(ValueError, match="rehydrated result does not exactly match"):
        gateway.rehydrate_result("fake", req, receipt)
    assert events == ["rehydrate"]


def test_gateway_rehydration_rejects_unrecorded_state():
    req = request()
    states = {req.digest: "RUNNING"}
    events = []
    gateway = make_gateway(events, states)
    gateway.register("fake", FakeAdapter(events))
    with pytest.raises(RuntimeError, match="recorded external result"):
        gateway.rehydrate_result("fake", req, FakeResult(req.execution_id, req.digest, "NO_COUNTEREXAMPLE").canonical_payload())
    assert events == []


def test_gateway_rehydration_rejects_payload_substitution():
    req = request()
    states = {req.digest: "COMPLETED"}
    receipt = FakeResult(req.execution_id, "wrong-digest", "NO_COUNTEREXAMPLE").canonical_payload()
    events = []
    gateway = make_gateway(events, states)
    gateway.register("fake", FakeAdapter(events))
    with pytest.raises(ValueError, match="request digest"):
        gateway.rehydrate_result("fake", req, receipt)


def test_gateway_rehydrates_after_process_reload_state():
    req = request()
    receipt = FakeResult(req.execution_id, req.digest, "NO_COUNTEREXAMPLE").canonical_payload()
    states = {req.digest: "COMPLETED"}
    first_events = []
    first_gateway = make_gateway(first_events, states)
    first_gateway.register("fake", FakeAdapter(first_events))
    first_gateway.rehydrate_result("fake", req, receipt)

    second_events = []
    second_gateway = make_gateway(second_events, states)
    second_gateway.register("fake", FakeAdapter(second_events))
    second_result = second_gateway.rehydrate_result("fake", req, receipt)
    assert second_result.canonical_payload() == receipt
    assert second_events == ["rehydrate"]


def test_gateway_rejects_invalid_lifecycle_transition():
    req = request()
    states = {req.digest: "COMPLETED"}
    gateway = ExternalExecutionGateway(lambda request: None, lambda request, state: states.__setitem__(request.digest, state), lambda request: states.get(request.digest), lambda request, result: None)
    with pytest.raises(RuntimeError, match="COMPLETED -> RUNNING"):
        gateway._state(req, "RUNNING")
    assert states[req.digest] == "COMPLETED"


def test_gateway_rejects_replay_in_same_process():
    events = []
    gateway = make_gateway(events)
    gateway.register("fake", FakeAdapter(events))
    req = request()
    gateway.execute("fake", req, authorization=auth())
    with pytest.raises(RuntimeError, match="already been executed"):
        gateway.execute("fake", req, authorization=auth())
    assert events == ["persist", "execute", "result"]


def test_gateway_rejects_persisted_replay_after_reload():
    states = {request().digest: "COMPLETED"}
    events = []
    gateway = make_gateway(events, states)
    gateway.register("fake", FakeAdapter(events))
    with pytest.raises(RuntimeError, match="COMPLETED"):
        gateway.execute("fake", request(), authorization=auth())
    assert events == []


def test_gateway_rejects_persisted_running_replay_after_reload():
    states = {request().digest: "RUNNING"}
    events = []
    gateway = make_gateway(events, states)
    gateway.register("fake", FakeAdapter(events))
    with pytest.raises(RuntimeError, match="RUNNING"):
        gateway.execute("fake", request(), authorization=auth())
    assert events == []


def test_gateway_marks_failed_execution_and_blocks_retry():
    states = {}
    events = []
    gateway = make_gateway(events, states)
    gateway.register("fake", FailingAdapter(events))
    req = request()
    with pytest.raises(RuntimeError, match="infrastructure failure"):
        gateway.execute("fake", req, authorization=auth())
    assert states[req.digest] == "FAILED"
    with pytest.raises(RuntimeError, match="FAILED"):
        gateway.execute("fake", req, authorization=auth())
    assert events == ["persist", "execute"]


def test_gateway_marks_outcome_unrecorded_when_completion_persistence_fails():
    req = request()
    states = {}
    events = []

    def set_state(request_obj, state):
        if state == "COMPLETED":
            raise RuntimeError("completion persistence unavailable")
        states[request_obj.digest] = state

    gateway = ExternalExecutionGateway(lambda r: events.append("persist"), set_state, lambda r: states.get(r.digest), lambda r, result: events.append("result"))
    gateway.register("fake", FakeAdapter(events))
    with pytest.raises(RuntimeError, match="succeeded but completion state"):
        gateway.execute("fake", req, authorization=auth())
    assert states[req.digest] == "OUTCOME_UNRECORDED"
    with pytest.raises(RuntimeError, match="OUTCOME_UNRECORDED"):
        gateway.execute("fake", req, authorization=auth())
    assert events == ["persist", "execute", "result"]


def test_gateway_rejects_duplicate_adapter_registration():
    gateway = ExternalExecutionGateway(lambda req: None, persist_result=lambda req, result: None)
    adapter = FakeAdapter([])
    gateway.register("fake", adapter)
    with pytest.raises(ValueError, match="already registered"):
        gateway.register("fake", adapter)


def test_gateway_rejects_adapter_rebinding_across_gateways():
    """An adapter bound to one gateway must never be silently hijacked by another."""
    adapter = FakeAdapter([])
    first_gateway = ExternalExecutionGateway(lambda req: None, persist_result=lambda req, result: None)
    second_gateway = ExternalExecutionGateway(lambda req: None, persist_result=lambda req, result: None)

    first_gateway.register("fake", adapter)
    first_capability = adapter.gateway_capability

    with pytest.raises(RuntimeError, match="different gateway"):
        second_gateway.register("fake", adapter)

    assert adapter.gateway_capability is first_capability
    assert first_gateway.registered_adapters == ("fake",)
    assert second_gateway.registered_adapters == ()


def test_gateway_rejects_unregistered_adapter():
    gateway = ExternalExecutionGateway(lambda req: None, persist_result=lambda req, result: None)
    with pytest.raises(KeyError, match="not registered"):
        gateway.execute("fake", request(), authorization=auth())


def test_gateway_rejects_request_adapter_substitution():
    gateway = ExternalExecutionGateway(lambda req: None, persist_result=lambda req, result: None)
    gateway.register("other", FakeAdapter([]))
    with pytest.raises(ValueError, match="adapter does not match"):
        gateway.execute("other", request(), authorization=auth())


def test_gateway_rejects_authorization_substitution_before_persistence():
    events = []
    gateway = make_gateway(events)
    gateway.register("fake", FakeAdapter(events))
    with pytest.raises(PermissionError, match="authorization identity"):
        gateway.execute("fake", request(), authorization=FoundryAuthorization("wrong-auth"))
    assert events == []


def test_gateway_rejects_result_substitution_after_external_execution():
    events = []
    gateway = make_gateway(events)
    gateway.register("fake", WrongResultAdapter(events))
    with pytest.raises(ValueError, match="request digest"):
        gateway.execute("fake", request(), authorization=auth())
    assert events == ["persist", "execute"]


def test_gateway_rejects_invalid_result_contract_after_external_execution():
    events = []
    gateway = make_gateway(events)
    gateway.register("fake", InvalidResultAdapter(events))
    with pytest.raises(TypeError, match="result contract"):
        gateway.execute("fake", request(), authorization=auth())
    assert events == ["persist", "execute"]


def test_gateway_requires_request_and_result_persistence():
    gateway = ExternalExecutionGateway()
    gateway.register("fake", FakeAdapter([]))
    with pytest.raises(RuntimeError, match="request and result persistence"):
        gateway.execute("fake", request(), authorization=auth())


def test_foundry_runner_implements_canonical_gateway_adapter_contract():
    runner = FoundryRunner("tests/fixtures/foundry")
    assert isinstance(runner, ExternalExecutionAdapter)
    assert hasattr(runner, "execute")
    assert hasattr(runner, "rehydrate_result")
    assert hasattr(runner, "_bind_gateway_capability")


def test_foundry_runner_rejects_direct_execute_without_gateway_capability(tmp_path):
    runner = FoundryRunner(str(tmp_path))
    authorization = FoundryAuthorization("auth-001")
    request_obj = runner.build_request(authorization=authorization, execution_id="exec-direct")
    with pytest.raises(PermissionError, match="canonical external execution gateway"):
        runner.execute(request=request_obj, authorization=authorization, gateway_capability=object())


def _orchestrator_with_planned_observation():
    request_obj = request()
    model = SystemModel()
    model.add_node(Node("observation:check", "observation", "check", {"planned": True, "authorized": True, "execution_id": request_obj.execution_id, "execution_request_digest": request_obj.digest}))
    model.add_node(Node(f"execution_request:{request_obj.digest}", "execution_request", request_obj.digest, {**request_obj.canonical_payload(), "digest": request_obj.digest, "execution_state": "PERSISTED"}))
    model.connect("observation:check", "executes_request", f"execution_request:{request_obj.digest}", provenance="explicit_execution_binding")
    return ReasoningOrchestrator(model), request_obj


def test_orchestrator_rejects_unauthorized_observation_before_gateway_execution():
    orchestrator, request_obj = _orchestrator_with_planned_observation()
    observation = Observation(name="check", outcomes=["NO_COUNTEREXAMPLE"], cost=1.0, authorized=False, execution_id=request_obj.execution_id, execution_request_digest=request_obj.digest)
    with pytest.raises(ValueError, match="unauthorized observations"):
        orchestrator.execute_external_observation("fake", observation, authorization=auth())


def test_orchestrator_rejects_stale_observation_execution_identity():
    orchestrator, request_obj = _orchestrator_with_planned_observation()
    observation = Observation(name="check", outcomes=["NO_COUNTEREXAMPLE"], cost=1.0, authorized=True, execution_id="stale-execution-id", execution_request_digest=request_obj.digest)
    with pytest.raises(ValueError, match="execution identity"):
        orchestrator.execute_external_observation("fake", observation, authorization=auth())
