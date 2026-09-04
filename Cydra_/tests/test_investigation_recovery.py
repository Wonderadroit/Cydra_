from dataclasses import replace
import time

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionAdapter
from cydra.foundry import FoundryAuthorization
from cydra.investigation_control import InvestigationBudget, InvestigationController, InvestigationLease, InvestigationScope
from cydra.investigation_execution import InvestigationExecutionAuthorization
from cydra.investigation_recovery import recover_investigation_plan
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator


class Result:
    def __init__(self, execution_id, request_digest, outcome):
        self.execution_id = execution_id
        self.request_digest = request_digest
        self.outcome = outcome

    def canonical_payload(self):
        return {"execution_id": self.execution_id, "request_digest": self.request_digest, "outcome": self.outcome}


class Adapter:
    def __init__(self):
        self.calls = 0
        self.gateway_capability = None

    def _bind_gateway_capability(self, capability):
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization):
        return ExecutionRequest(execution_id, "fake", "fixture", ("fake", "check"), "project:fixture", authorization.authorization_id)

    def execute(self, *, request, authorization, gateway_capability):
        assert gateway_capability is self.gateway_capability
        self.calls += 1
        return Result(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")

    def rehydrate_result(self, *, payload, request):
        return Result(payload["execution_id"], payload["request_digest"], payload["outcome"])


assert isinstance(Adapter(), ExternalExecutionAdapter)


def controller():
    now = time.time()
    return InvestigationController(
        investigation_id="inv-recovery",
        scope=InvestigationScope("scope-recovery", allowed_observations=frozenset({"check"})),
        budget=InvestigationBudget(max_observations=2, max_execution_cost=10.0),
        lease=InvestigationLease("lease-recovery", now - 1.0, now + 999999999.0, generation=3),
    )


def setup():
    base = FoundryAuthorization("auth-recovery")
    ctrl = controller()
    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-recovery", authorization=base)
    observation = Observation("check", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0, authorized=True, execution_id=request.execution_id, execution_request=request)
    hypothesis = Hypothesis("h-recovery", 0.5, {"check": {"NO_COUNTEREXAMPLE": 1.0}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    planned = orchestrator.record_investigation_plan(ctrl, Plan("check", 1.0, 1.0, "recovery"), [hypothesis], observation, authorization=base)
    return base, ctrl, adapter, orchestrator, planned


def test_recovery_requires_fresh_capability_not_persisted_snapshot():
    base, ctrl, adapter, orchestrator, planned = setup()
    persisted = orchestrator.model.nodes[f"execution_request:{planned.observation.execution_request_digest}"]
    binding = persisted.attributes["parameters"]["_cydra_investigation_authority"]
    assert not isinstance(binding, InvestigationExecutionAuthorization)
    with pytest.raises(PermissionError):
        orchestrator.execute_external_observation("fake", planned.observation, authorization=base)
    assert adapter.calls == 0
    recovered = recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    assert isinstance(recovered.authorization, InvestigationExecutionAuthorization)
    assert recovered.authorization is not planned.authorization
    assert recovered.authorization.canonical_payload() == binding
    assert ctrl.observations_used == 1
    result = orchestrator.execute_investigation_plan("fake", recovered)
    assert result.request_digest == planned.observation.execution_request_digest
    assert adapter.calls == 1


def test_recovery_rejects_changed_live_authority():
    base, ctrl, adapter, orchestrator, planned = setup()
    ctrl.scope = replace(ctrl.scope, target_id="changed")
    with pytest.raises(PermissionError, match="no longer matches live authority"):
        recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovery_rejects_wrong_base_authorization():
    base, ctrl, adapter, orchestrator, planned = setup()
    wrong = FoundryAuthorization("wrong-auth")
    with pytest.raises(PermissionError, match="base authorization"):
        recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=wrong)
    assert adapter.calls == 0


def test_recovery_does_not_consume_observation_budget_again():
    base, ctrl, adapter, orchestrator, planned = setup()
    before = (ctrl.observations_used, ctrl.execution_cost_used, set(ctrl.observed_execution_ids))
    recovered = recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    after = (ctrl.observations_used, ctrl.execution_cost_used, set(ctrl.observed_execution_ids))
    assert after == before
    assert recovered.observation.execution_request_digest == planned.observation.execution_request_digest


def test_recovery_rejects_tampered_persisted_investigation_binding():
    base, ctrl, adapter, orchestrator, planned = setup()
    request_id = f"execution_request:{planned.observation.execution_request_digest}"
    node = orchestrator.model.nodes[request_id]
    parameters = dict(node.attributes["parameters"])
    binding = dict(parameters["_cydra_investigation_authority"])
    binding["investigation_id"] = "attacker-investigation"
    parameters["_cydra_investigation_authority"] = binding
    orchestrator.model.nodes[request_id] = type(node)(node.node_id, node.kind, node.label, {**node.attributes, "parameters": parameters})
    with pytest.raises(ValueError, match="execution request digest"):
        recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovery_rejects_tampered_execution_identity():
    base, ctrl, adapter, orchestrator, planned = setup()
    request_id = f"execution_request:{planned.observation.execution_request_digest}"
    node = orchestrator.model.nodes[request_id]
    parameters = dict(node.attributes["parameters"])
    binding = dict(parameters["_cydra_investigation_authority"])
    binding["execution_id"] = "different-execution"
    parameters["_cydra_investigation_authority"] = binding
    orchestrator.model.nodes[request_id] = type(node)(node.node_id, node.kind, node.label, {**node.attributes, "parameters": parameters})
    with pytest.raises(ValueError, match="execution request digest"):
        recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovery_rejects_tampered_persisted_observation_identity():
    base, ctrl, adapter, orchestrator, planned = setup()
    request_id = f"execution_request:{planned.observation.execution_request_digest}"
    node = orchestrator.model.nodes[request_id]
    parameters = dict(node.attributes["parameters"])
    binding = dict(parameters["_cydra_investigation_authority"])
    binding["observation_name"] = "different-observation"
    parameters["_cydra_investigation_authority"] = binding
    orchestrator.model.nodes[request_id] = type(node)(node.node_id, node.kind, node.label, {**node.attributes, "parameters": parameters})
    with pytest.raises(ValueError, match="execution request digest"):
        recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovery_rejects_request_with_rebound_base_authorization_identity():
    base, ctrl, adapter, orchestrator, planned = setup()
    request_id = f"execution_request:{planned.observation.execution_request_digest}"
    node = orchestrator.model.nodes[request_id]
    parameters = dict(node.attributes["parameters"])
    parameters["authorization_id"] = "attacker-authorization"
    orchestrator.model.nodes[request_id] = type(node)(node.node_id, node.kind, node.label, {**node.attributes, "parameters": parameters})
    with pytest.raises(ValueError, match="execution request digest"):
        recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovery_rejects_tampered_serialized_usage_state():
    base, original, adapter, orchestrator, planned = setup()
    snapshot = original.snapshot()
    snapshot["usage"] = {**snapshot["usage"], "observations_used": 0, "observed_execution_ids": ["exec-recovery"]}
    recovered_controller = InvestigationController.from_snapshot(snapshot, expected_authority_fingerprint=original.authority_fingerprint)
    with pytest.raises(ValueError, match="observation usage"):
        recover_investigation_plan(orchestrator, recovered_controller, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovery_rejects_expired_controller():
    base, original, adapter, orchestrator, planned = setup()
    now = time.time()
    expired = replace(original, lease=replace(original.lease, issued_at=now - 2.0, expires_at=now - 1.0))
    with pytest.raises(RuntimeError, match="not active"):
        recover_investigation_plan(orchestrator, expired, planned.observation_id, authorization=base)
    assert adapter.calls == 0


def test_recovered_capability_fails_after_live_lease_generation_changes():
    base, ctrl, adapter, orchestrator, planned = setup()
    recovered = recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    ctrl.lease = replace(ctrl.lease, generation=ctrl.lease.generation + 1)
    with pytest.raises(PermissionError, match="authority changed"):
        orchestrator.execute_investigation_plan("fake", recovered)
    assert adapter.calls == 0


def test_recovered_capability_fails_after_controller_termination():
    base, ctrl, adapter, orchestrator, planned = setup()
    recovered = recover_investigation_plan(orchestrator, ctrl, planned.observation_id, authorization=base)
    ctrl.terminate(type(ctrl.termination).BUDGET_EXHAUSTED)
    with pytest.raises(RuntimeError, match="not active"):
        orchestrator.execute_investigation_plan("fake", recovered)
    assert adapter.calls == 0


def test_recovery_from_serialized_controller_requires_external_fingerprint_confirmation():
    base, original, adapter, orchestrator, planned = setup()
    snapshot = original.snapshot()
    expected = original.authority_fingerprint
    recovered_controller = InvestigationController.from_snapshot(snapshot, expected_authority_fingerprint=expected)
    recovered = recover_investigation_plan(orchestrator, recovered_controller, planned.observation_id, authorization=base)
    assert recovered.authorization is not planned.authorization
    assert recovered.authorization.controller is recovered_controller
    assert recovered_controller.observations_used == original.observations_used
    assert adapter.calls == 0


def test_recovery_rejects_forged_controller_snapshot_even_with_persisted_fingerprint():
    base, ctrl, adapter, orchestrator, planned = setup()
    snapshot = ctrl.snapshot()
    snapshot["scope"] = {**snapshot["scope"], "target_id": "forged-target"}
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        InvestigationController.from_snapshot(snapshot, expected_authority_fingerprint=ctrl.authority_fingerprint)
    assert adapter.calls == 0
