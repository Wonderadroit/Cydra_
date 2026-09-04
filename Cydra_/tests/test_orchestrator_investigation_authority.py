from dataclasses import dataclass, replace

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionAdapter
from cydra.foundry import FoundryAuthorization
from cydra.investigation_control import (
    InvestigationBudget,
    InvestigationController,
    InvestigationLease,
    InvestigationScope,
)
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import AuthorizedInvestigationPlan, ReasoningOrchestrator


@dataclass(frozen=True)
class Result:
    execution_id: str
    request_digest: str
    outcome: str

    def canonical_payload(self):
        return {
            "execution_id": self.execution_id,
            "request_digest": self.request_digest,
            "outcome": self.outcome,
        }


class Adapter:
    def __init__(self):
        self.calls = 0
        self.gateway_capability = None

    def _bind_gateway_capability(self, capability):
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization):
        return ExecutionRequest(
            execution_id,
            "fake",
            "fixture",
            ("fake", "check"),
            "project:fixture",
            authorization.authorization_id,
        )

    def execute(self, *, request, authorization, gateway_capability):
        assert gateway_capability is self.gateway_capability
        self.calls += 1
        return Result(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")

    def rehydrate_result(self, *, payload, request):
        return Result(payload["execution_id"], payload["request_digest"], payload["outcome"])


assert isinstance(Adapter(), ExternalExecutionAdapter)


def make_controller(investigation_id="inv-1"):
    return InvestigationController(
        investigation_id=investigation_id,
        scope=InvestigationScope("scope-1", allowed_observations=frozenset({"check"})),
        budget=InvestigationBudget(max_observations=1, max_execution_cost=10.0),
        lease=InvestigationLease("lease-1", 100.0, 9999999999.0, generation=7),
    )


def make_observation(authorization):
    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-canonical", authorization=authorization)
    observation = Observation(
        "check",
        ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"],
        1.0,
        authorized=True,
        execution_id=request.execution_id,
        execution_request=request,
    )
    hypothesis = Hypothesis(
        "h-canonical",
        0.5,
        {"check": {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}},
    )
    return adapter, observation, hypothesis


def test_record_investigation_plan_is_the_canonical_binding_boundary():
    base = FoundryAuthorization("auth-canonical")
    controller = make_controller()
    adapter, observation, hypothesis = make_observation(base)
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)

    planned = orchestrator.record_investigation_plan(
        controller,
        Plan("check", 1.0, 1.0, "authority-bound"),
        [hypothesis],
        observation,
        authorization=base,
    )

    assert isinstance(planned, AuthorizedInvestigationPlan)
    assert planned.observation.execution_request_digest != observation.execution_request_digest
    node = orchestrator.model.nodes[planned.observation_id]
    assert node.attributes["execution_request_digest"] == planned.observation.execution_request_digest
    persisted = orchestrator.model.nodes[f"execution_request:{planned.observation.execution_request_digest}"]
    binding = persisted.attributes["parameters"]["_cydra_investigation_authority"]
    assert binding["investigation_id"] == "inv-1"
    assert binding["authority_fingerprint"] == controller.authority_fingerprint
    assert controller.observations_used == 1


def test_execute_investigation_plan_rechecks_live_authority_before_adapter():
    base = FoundryAuthorization("auth-live")
    controller = make_controller()
    adapter, observation, hypothesis = make_observation(base)
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    planned = orchestrator.record_investigation_plan(
        controller,
        Plan("check", 1.0, 1.0, "authority-bound"),
        [hypothesis],
        observation,
        authorization=base,
    )

    controller.scope = replace(controller.scope, target_id="changed-target")
    try:
        orchestrator.execute_investigation_plan("fake", planned)
    except PermissionError as exc:
        assert "authority changed" in str(exc)
    else:
        raise AssertionError("stale investigation authority must fail closed")
    assert adapter.calls == 0


def test_execute_investigation_plan_rejects_cross_investigation_capability():
    base = FoundryAuthorization("auth-cross")
    first = make_controller("inv-first")
    second = make_controller("inv-second")
    adapter, observation, hypothesis = make_observation(base)
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    planned = orchestrator.record_investigation_plan(
        first,
        Plan("check", 1.0, 1.0, "authority-bound"),
        [hypothesis],
        observation,
        authorization=base,
    )
    planned = AuthorizedInvestigationPlan(
        planned.observation_id,
        planned.observation,
        type(planned.authorization)(
            controller=second,
            investigation_id=second.investigation_id,
            authority_fingerprint=second.authority_fingerprint,
            lease_generation=second.lease.generation,
            execution_id=planned.observation.execution_id,
            observation_name=planned.observation.name,
            authorization_id=base.authorization_id,
            scope_status=base.scope_status,
        ),
    )

    try:
        orchestrator.execute_investigation_plan("fake", planned)
    except PermissionError as exc:
        assert "investigation authority" in str(exc) or "binding" in str(exc)
    else:
        raise AssertionError("cross-investigation execution must fail closed")
    assert adapter.calls == 0


def test_canonical_handoff_executes_exact_bound_request_once():
    base = FoundryAuthorization("auth-execute")
    controller = make_controller()
    adapter, observation, hypothesis = make_observation(base)
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    planned = orchestrator.record_investigation_plan(
        controller,
        Plan("check", 1.0, 1.0, "authority-bound"),
        [hypothesis],
        observation,
        authorization=base,
    )

    result = orchestrator.execute_investigation_plan("fake", planned)

    assert result.request_digest == planned.observation.execution_request_digest
    assert adapter.calls == 1
    persisted = orchestrator.model.nodes[f"execution_result:{result.request_digest}"]
    assert persisted.attributes["request_digest"] == planned.observation.execution_request_digest
