from dataclasses import dataclass

from cydra.execution_recovery import rehydrate_external_observation_result
from cydra.execution_request import ExecutionRequest
from cydra.planner import Hypothesis, Observation
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.system_model import Node, SystemModel


@dataclass(frozen=True)
class RecoveryResult:
    execution_id: str
    request_digest: str
    outcome: str

    def canonical_payload(self):
        return {
            "execution_id": self.execution_id,
            "request_digest": self.request_digest,
            "outcome": self.outcome,
        }


class RecoveryAdapter:
    def __init__(self):
        self.executions = 0
        self.rehydrations = 0
        self.gateway_capability = None

    def _bind_gateway_capability(self, capability):
        if self.gateway_capability is not None and self.gateway_capability is not capability:
            raise RuntimeError("adapter is already bound to a different gateway")
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization, command=None):
        return ExecutionRequest(
            execution_id=execution_id,
            adapter="fake",
            target="fixture",
            command=("fake", "check"),
            project_fingerprint="project:fixture",
            authorization_id=authorization.authorization_id,
        )

    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.executions += 1
        raise AssertionError("recovery must never execute the external adapter")

    def rehydrate_result(self, *, payload, request):
        self.rehydrations += 1
        return RecoveryResult(payload["execution_id"], payload["request_digest"], payload["outcome"])


def _fixture():
    request = ExecutionRequest(
        execution_id="exec-recovery-001",
        adapter="fake",
        target="fixture",
        command=("fake", "check"),
        project_fingerprint="project:fixture",
        authorization_id="auth-001",
    )
    observation = Observation(
        name="check",
        outcomes=["NO_COUNTEREXAMPLE"],
        cost=1.0,
        authorized=True,
        execution_id=request.execution_id,
        execution_request_digest=request.digest,
        execution_request=request,
    )
    hypothesis = Hypothesis(
        name="safe",
        probability=0.5,
        predictions={"check": {"NO_COUNTEREXAMPLE": 1.0}},
    )
    model = SystemModel()
    model.add_node(Node(
        "observation:check", "observation", "check",
        {"planned": True, "authorized": True, "execution_id": request.execution_id, "execution_request_digest": request.digest},
    ))
    request_id = f"execution_request:{request.digest}"
    model.add_node(Node(
        request_id, "execution_request", request.digest,
        {**request.canonical_payload(), "digest": request.digest, "execution_state": "COMPLETED"},
    ))
    model.connect("observation:check", "executes_request", request_id, provenance="explicit_execution_binding")
    model.add_node(Node(
        "hypothesis:safe", "hypothesis", "safe",
        {"probability": 0.5, "predictions": {"check": {"NO_COUNTEREXAMPLE": 1.0}}, "state": "unresolved"},
    ))
    result = RecoveryResult(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")
    payload = result.canonical_payload()
    import hashlib
    import json
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    model.add_node(Node(
        f"execution_result:{request.digest}", "execution_result", request.digest,
        {"execution_id": request.execution_id, "request_digest": request.digest, "adapter": "fake", "payload": payload, "fingerprint": fingerprint},
    ))
    model = SystemModel.from_dict(model.export())
    orchestrator = ReasoningOrchestrator(model)
    _sign_history(orchestrator, [
        {"type": "EXECUTION_REQUEST_PERSISTED", "execution_request": request_id, "execution_id": request.execution_id, "digest": request.digest},
        {"type": "EXECUTION_STATE_CHANGED", "execution_request": request_id, "execution_id": request.execution_id, "previous_state": "PERSISTED", "state": "RUNNING", "request_digest": request.digest},
        {"type": "EXECUTION_RESULT_RECORDED", "execution_request": request_id, "execution_result": f"execution_result:{request.digest}", "execution_id": request.execution_id, "request_digest": request.digest, "fingerprint": fingerprint},
        {"type": "EXECUTION_STATE_CHANGED", "execution_request": request_id, "execution_id": request.execution_id, "previous_state": "RUNNING", "state": "RESULT_RECORDED", "request_digest": request.digest},
        {"type": "EXECUTION_STATE_CHANGED", "execution_request": request_id, "execution_id": request.execution_id, "previous_state": "RESULT_RECORDED", "state": "COMPLETED", "request_digest": request.digest},
        {"type": "EXTERNAL_EXECUTION_COMPLETED", "execution_request": request_id, "execution_id": request.execution_id},
    ])
    return orchestrator, request, observation, hypothesis


def _sign_history(orchestrator, history):
    previous = orchestrator.graph.AUDIT_GENESIS
    for sequence, event in enumerate(history):
        event["sequence"] = sequence
        event["previous_hash"] = previous
        event["event_hash"] = orchestrator.graph._audit_digest(event)
        previous = event["event_hash"]
    orchestrator.graph.history = history


def test_fresh_process_rehydrates_durable_receipt_and_resumes_reasoning():
    orchestrator, request, observation, hypothesis = _fixture()
    adapter = RecoveryAdapter()
    orchestrator.register_external_adapter("fake", adapter)

    update = rehydrate_external_observation_result(
        orchestrator,
        "fake",
        observation,
        [hypothesis],
        "recovered-evidence",
    )

    assert adapter.executions == 0
    assert adapter.rehydrations == 1
    assert update.evidence_node_id == "evidence:recovered-evidence"
    assert "evidence:recovered-evidence" in orchestrator.model.nodes
    assert any(
        node.kind == "belief" and node.attributes.get("evidence_id") == "evidence:recovered-evidence"
        for node in orchestrator.model.nodes.values()
    )


def test_fresh_process_recovery_rejects_tampered_receipt_fingerprint():
    orchestrator, request, observation, hypothesis = _fixture()
    receipt = orchestrator.model.nodes[f"execution_result:{request.digest}"]
    orchestrator.model.nodes[receipt.node_id] = Node(
        receipt.node_id,
        receipt.kind,
        receipt.label,
        {**receipt.attributes, "fingerprint": "tampered"},
    )
    adapter = RecoveryAdapter()
    orchestrator.register_external_adapter("fake", adapter)

    try:
        rehydrate_external_observation_result(orchestrator, "fake", observation, [hypothesis], "tampered-evidence")
    except RuntimeError as exc:
        assert "fingerprint" in str(exc)
    else:
        raise AssertionError("tampered receipt must fail closed")
    assert adapter.executions == 0
    assert adapter.rehydrations == 0


def test_rehydration_does_not_require_execution_authorization_object():
    orchestrator, request, observation, hypothesis = _fixture()
    adapter = RecoveryAdapter()
    orchestrator.register_external_adapter("fake", adapter)
    rehydrate_external_observation_result(orchestrator, "fake", observation, [hypothesis], "receipt-only")
    assert adapter.executions == 0


def test_fresh_process_recovery_rejects_inconsistent_execution_lifecycle():
    orchestrator, request, observation, hypothesis = _fixture()
    request_id = f"execution_request:{request.digest}"
    history = [
        {
            "type": "EXECUTION_REQUEST_PERSISTED",
            "execution_request": request_id,
            "execution_id": request.execution_id,
        },
        {
            "type": "EXECUTION_STATE_CHANGED",
            "execution_request": request_id,
            "execution_id": request.execution_id,
            "previous_state": "PERSISTED",
            "state": "COMPLETED",
            "request_digest": request.digest,
        },
    ]
    _sign_history(orchestrator, history)
    adapter = RecoveryAdapter()
    orchestrator.register_external_adapter("fake", adapter)

    try:
        rehydrate_external_observation_result(orchestrator, "fake", observation, [hypothesis], "blocked")
    except RuntimeError as exc:
        assert "execution lifecycle" in str(exc)
    else:
        raise AssertionError("inconsistent lifecycle must fail closed")
    assert adapter.executions == 0
    assert adapter.rehydrations == 0
