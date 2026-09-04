from dataclasses import dataclass, replace

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionAdapter
from cydra.foundry import FoundryAuthorization
from cydra.investigation_control import InvestigationBudget, InvestigationController, InvestigationLease, InvestigationScope
from cydra.investigation_execution import bind_observation_execution, issue_execution_authorization
from cydra.investigation_expansion import DependencyCandidate, DependencyExpansionGrant
from cydra.planner import Observation, Hypothesis, Plan
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
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization, command=None):
        return ExecutionRequest(execution_id, "fake", "fixture", ("fake", "check"), "project:fixture", authorization.authorization_id)

    def execute(self, *, request, authorization, gateway_capability):
        assert gateway_capability is self.gateway_capability
        self.calls += 1
        return Result(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")

    def rehydrate_result(self, *, payload, request):
        return Result(payload["execution_id"], payload["request_digest"], payload["outcome"])


assert isinstance(Adapter(), ExternalExecutionAdapter)


def controller(investigation_id="inv-1"):
    return InvestigationController(
        investigation_id=investigation_id,
        scope=InvestigationScope("scope-1", allowed_observations=frozenset({"check"})),
        budget=InvestigationBudget(max_observations=1, max_execution_cost=10.0),
        lease=InvestigationLease("lease-1", 100.0, 9999999999.0, generation=7),
    )


def observation(authorization):
    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-investigation", authorization=authorization)
    return adapter, Observation("check", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0, authorized=True, execution_id=request.execution_id, execution_request=request)




def test_investigation_binding_preserves_invariant_reasoning_targets_and_hypothesis_pair():
    base = FoundryAuthorization("auth-semantic-preservation")
    ctrl = controller()
    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-semantic", authorization=base)
    pair = ("hypothesis:holds:candidate:x", "hypothesis:violated:candidate:x")
    original = Observation(
        "check",
        ["INVARIANT_PRESERVED", "INVARIANT_VIOLATED", "INCONCLUSIVE"],
        1.0,
        authorized=True,
        execution_id=request.execution_id,
        execution_request=request,
        discriminates_hypothesis_ids=pair,
        target_ids=("function:deposit", "state:totalShares", "ast:42"),
        rationale="verify compiler-backed invariant transition",
    )
    token = issue_execution_authorization(ctrl, original, base)

    bound = bind_observation_execution(original, token)

    assert bound.discriminates_hypothesis_ids == pair
    assert bound.target_ids == original.target_ids
    assert bound.rationale == original.rationale
    assert bound.execution_request_digest == original.execution_request_digest or bound.execution_request_digest != ""


def test_investigation_bound_request_executes_only_with_live_controller_authority():
    base = FoundryAuthorization("auth-investigation")
    ctrl = controller()
    adapter, original = observation(base)
    token = issue_execution_authorization(ctrl, original, base)
    bound = bind_observation_execution(original, token)
    hypothesis = Hypothesis("h", 0.5, {"check": {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan("check", 1.0, 1.0, "authority-bound"), [hypothesis], bound)

    result = orchestrator.execute_external_observation("fake", bound, authorization=token)

    assert result.execution_id == "exec-investigation"
    assert adapter.calls == 1
    persisted = orchestrator.model.nodes[f"execution_request:{bound.execution_request_digest}"]
    assert persisted.attributes["parameters"]["_cydra_investigation_authority"]["investigation_id"] == "inv-1"


def test_bound_request_rejects_missing_investigation_authorization_before_adapter():
    base = FoundryAuthorization("auth-missing-token")
    ctrl = controller()
    adapter, original = observation(base)
    token = issue_execution_authorization(ctrl, original, base)
    bound = bind_observation_execution(original, token)
    hypothesis = Hypothesis("h-missing", 0.5, {"check": {"NO_COUNTEREXAMPLE": 1.0}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan("check", 1.0, 1.0, "authority-bound"), [hypothesis], bound)

    try:
        orchestrator.execute_external_observation("fake", bound, authorization=base)
    except PermissionError as exc:
        assert "investigation-bound execution" in str(exc)
    else:
        raise AssertionError("bound execution must require its investigation capability")
    assert adapter.calls == 0


def test_stale_investigation_authority_rejects_before_adapter_execution():
    base = FoundryAuthorization("auth-stale")
    ctrl = controller()
    adapter, original = observation(base)
    token = issue_execution_authorization(ctrl, original, base)
    bound = bind_observation_execution(original, token)
    hypothesis = Hypothesis("h-stale", 0.5, {"check": {"NO_COUNTEREXAMPLE": 1.0}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan("check", 1.0, 1.0, "authority-bound"), [hypothesis], bound)

    ctrl.scope = replace(ctrl.scope, target_id="changed-target")
    try:
        orchestrator.execute_external_observation("fake", bound, authorization=token)
    except PermissionError as exc:
        assert "authority changed" in str(exc)
    else:
        raise AssertionError("changed investigation authority must fail closed")
    assert adapter.calls == 0


def test_investigation_budget_exhaustion_between_authorization_and_execution_rejects():
    base = FoundryAuthorization("auth-budget")
    ctrl = controller()
    adapter, original = observation(base)
    token = issue_execution_authorization(ctrl, original, base)
    bound = bind_observation_execution(original, token)
    hypothesis = Hypothesis("h-budget", 0.5, {"check": {"NO_COUNTEREXAMPLE": 1.0}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan("check", 1.0, 1.0, "authority-bound"), [hypothesis], bound)

    ctrl.termination = ctrl.termination.BUDGET_EXHAUSTED
    try:
        orchestrator.execute_external_observation("fake", bound, authorization=token)
    except RuntimeError as exc:
        assert "not active" in str(exc)
    else:
        raise AssertionError("terminated investigation must not execute")
    assert adapter.calls == 0


def test_different_investigation_cannot_rebind_the_authority_token():
    base = FoundryAuthorization("auth-rebind")
    first = controller("inv-first")
    second = controller("inv-second")
    adapter, original = observation(base)
    first_token = issue_execution_authorization(first, original, base)
    bound = bind_observation_execution(original, first_token)
    second_token = issue_execution_authorization(second, original, base)
    hypothesis = Hypothesis("h-rebind", 0.5, {"check": {"NO_COUNTEREXAMPLE": 1.0}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    orchestrator.record_authorized_plan(Plan("check", 1.0, 1.0, "authority-bound"), [hypothesis], bound)

    try:
        orchestrator.execute_external_observation("fake", bound, authorization=second_token)
    except PermissionError as exc:
        assert "authority binding" in str(exc)
    else:
        raise AssertionError("an execution bound to investigation one must not execute under investigation two")
    assert adapter.calls == 0


def test_external_dependency_grant_flows_into_canonical_gateway_execution():
    base = FoundryAuthorization("auth-expansion-e2e")
    now = 100.0
    ctrl = InvestigationController(
        investigation_id="inv-expansion-e2e",
        scope=InvestigationScope("scope-expansion-e2e", allowed_observations=frozenset({"root"})),
        budget=InvestigationBudget(max_observations=2, max_execution_cost=10.0, max_dependency_depth=1),
        lease=InvestigationLease("lease-expansion-e2e", now, 9999999999.0, generation=1),
    )
    candidate = DependencyCandidate("dep:e2e", "contract:A", "contract:B", "call", authorized=True, depth=2)
    grant = DependencyExpansionGrant(
        "grant:e2e", ctrl.authority_fingerprint, frozenset({"dependency_check"}), frozenset({"dep:e2e"}), 2, "authority:e2e"
    )
    ctrl.apply_dependency_expansion([candidate], grant=grant)

    adapter = Adapter()
    request = adapter.build_request(execution_id="exec-dependency", authorization=base)
    dep_observation = Observation(
        "dependency_check", ["NO_COUNTEREXAMPLE", "COUNTEREXAMPLE"], 1.0,
        authorized=True, execution_id=request.execution_id, execution_request=request,
    )
    hypothesis = Hypothesis("h-dependency", 0.5, {"dependency_check": {"NO_COUNTEREXAMPLE": 0.8, "COUNTEREXAMPLE": 0.2}})
    orchestrator = ReasoningOrchestrator()
    orchestrator.register_external_adapter("fake", adapter)
    plan = orchestrator.record_investigation_plan(
        ctrl,
        Plan("dependency_check", 1.0, 1.0, "externally authorized dependency"),
        [hypothesis],
        dep_observation,
        authorization=base,
        dependency_depth=2,
    )
    result = orchestrator.execute_investigation_plan("fake", plan)

    assert result.execution_id == "exec-dependency"
    assert adapter.calls == 1
    assert plan.authorization.canonical_payload()["investigation_id"] == "inv-expansion-e2e"
    assert "dependency_check" in ctrl.scope.allowed_observations

    with __import__("pytest").raises(PermissionError, match="already been consumed"):
        ctrl.apply_dependency_expansion([candidate], grant=grant)
