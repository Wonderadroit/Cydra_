import time

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.investigation_control import (
    InvestigationBudget,
    InvestigationController,
    InvestigationDomain,
    InvestigationLease,
    InvestigationScope,
    TerminationReason,
)
from cydra.learning import LearningRecord, LearningStore
from cydra.planner import Hypothesis, Observation


def controller(*, expires_at=None, domain=InvestigationDomain.TARGET, allowed=None, **budget):
    now = time.time()
    if expires_at is None:
        expires_at = now + 1000
    issued_at = now - 1 if expires_at > now else now - 2
    scope = InvestigationScope(
        "scope:1",
        domain=domain,
        allowed_observations=frozenset(allowed or {"read_state", "meta_check"}),
        allow_meta_observations=domain == InvestigationDomain.META,
    )
    return InvestigationController(
        "investigation:1",
        scope,
        InvestigationBudget(**budget),
        InvestigationLease("lease:1", issued_at, expires_at, generation=4),
    )


def hypotheses():
    return [
        Hypothesis("h1", 0.5, {"read_state": {"yes": 0.9, "no": 0.1}}),
        Hypothesis("h2", 0.5, {"read_state": {"yes": 0.1, "no": 0.9}}),
    ]


def learning_store(*records):
    store = LearningStore()
    store.learn_many(tuple(records))
    return store


def test_planner_cannot_select_out_of_scope_or_meta_observation():
    c = controller(allowed={"read_state"})
    observations = [
        Observation("meta_check", ["yes", "no"], 1, domain="meta"),
        Observation("read_state", ["yes", "no"], 1, domain="target"),
    ]
    plan = c.plan(hypotheses(), observations)
    assert plan is not None
    assert plan.observation == "read_state"


def test_controller_issues_authority_bound_learning_context_for_planning():
    c = controller()
    store = learning_store(LearningRecord("finding:1", "observation_pattern", "read_state", "read_state"))
    plan = c.plan(hypotheses(), [Observation("read_state", ["yes", "no"], 1)], learning_store=store)
    assert plan is not None
    assert plan.investigation_id == c.investigation_id
    assert plan.learning_context_fingerprint
    assert plan.learning_ids == (next(iter(store.records)),)
    assert c.planning_steps_used == 1
    assert c.observations_used == 0


def test_controller_learning_cannot_authorize_out_of_scope_observation():
    c = controller(allowed={"read_state"})
    store = learning_store(LearningRecord("finding:1", "observation_pattern", "meta_check", "meta_check"))
    observations = [
        Observation("meta_check", ["yes", "no"], 1, domain="meta"),
        Observation("read_state", ["yes", "no"], 1, domain="target"),
    ]
    plan = c.plan(hypotheses(), observations, learning_store=store)
    assert plan is not None
    assert plan.observation == "read_state"
    assert plan.learning_ids == ()


def test_target_investigation_cannot_authorize_meta_observation():
    c = controller()
    obs = Observation("meta_check", ["yes", "no"], 1, domain="meta")
    with pytest.raises(PermissionError):
        c.authorize_observation(obs)
    assert c.termination == TerminationReason.ACTIVE


def test_meta_investigation_is_separate_domain():
    c = controller(domain=InvestigationDomain.META, allowed={"meta_check"})
    obs = Observation("meta_check", ["yes", "no"], 1, domain="meta")
    c.authorize_observation(obs)
    assert c.observations_used == 1


def test_budget_exhaustion_is_terminal_and_cannot_be_extended():
    c = controller(max_observations=1, max_execution_cost=1)
    obs = Observation("read_state", ["yes", "no"], 1, execution_id="execution:1")
    c.authorize_observation(obs)
    with pytest.raises(PermissionError):
        c.authorize_observation(Observation("read_state", ["yes", "no"], 1, execution_id="execution:2"))
    assert c.termination == TerminationReason.BUDGET_EXHAUSTED
    with pytest.raises(RuntimeError):
        c.require_active()


def test_recursive_dependency_hits_depth_limit():
    c = controller(max_dependency_depth=2)
    obs = Observation("read_state", ["yes", "no"], 1)
    with pytest.raises(PermissionError):
        c.authorize_observation(obs, dependency_depth=3)
    assert c.termination == TerminationReason.DEPTH_LIMIT_REACHED


def test_lease_expiry_is_terminal_before_planning():
    now = time.time()
    c = controller(expires_at=now - 1)
    with pytest.raises(RuntimeError):
        c.require_active(now=now)
    assert c.termination == TerminationReason.LEASE_EXPIRED


def test_snapshot_recovery_never_extends_expired_lease():
    now = time.time()
    c = controller(expires_at=now - 1)
    snapshot = c.snapshot()
    recovered = InvestigationController.from_snapshot(
        snapshot,
        expected_authority_fingerprint=c.authority_fingerprint,
        now=now,
    )
    assert recovered.termination == TerminationReason.LEASE_EXPIRED
    with pytest.raises(RuntimeError):
        recovered.require_active(now=now)


def test_snapshot_tampering_is_rejected_by_external_authority_fingerprint():
    c = controller(max_observations=2, max_execution_cost=5)
    snapshot = c.snapshot()
    snapshot["budget"]["max_observations"] = 999
    snapshot["lease"]["expires_at"] = time.time() + 999999.0
    with pytest.raises(ValueError, match="fingerprint"):
        InvestigationController.from_snapshot(
            snapshot,
            expected_authority_fingerprint=c.authority_fingerprint,
            now=time.time(),
        )


def test_repeated_execution_identity_is_rejected():
    c = controller()
    obs = Observation("read_state", ["yes", "no"], 1, execution_id="execution:same")
    c.authorize_observation(obs)
    with pytest.raises(ValueError):
        c.authorize_observation(obs)


def test_low_information_plan_terminates_without_execution():
    c = controller()
    obs = Observation("read_state", ["yes", "no"], 1)
    hs = [Hypothesis("h1", 1.0, {"read_state": {"yes": 1.0, "no": 0.0}})]
    assert c.plan(hs, [obs]) is None
    assert c.termination == TerminationReason.NO_HIGH_VALUE_OBSERVATION


def test_hypothesis_budget_cannot_be_increased_by_planner():
    c = controller(max_hypotheses=1)
    c.register_hypotheses(1)
    with pytest.raises(RuntimeError):
        c.register_hypotheses(1)
    assert c.termination == TerminationReason.BUDGET_EXHAUSTED


def _targeted_observation(target: str, execution_id: str = "execution:target") -> Observation:
    request = ExecutionRequest(
        execution_id=execution_id,
        adapter="foundry",
        target=target,
        command=("forge", "test"),
        project_fingerprint="project:fingerprint",
        authorization_id="auth:1",
    )
    return Observation(
        "read_state",
        ["yes", "no"],
        1,
        execution_id=execution_id,
        execution_request=request,
    )


def test_target_scoped_authorization_rejects_request_for_different_target():
    c = InvestigationController(
        "investigation:target",
        InvestigationScope("scope:target", allowed_observations=frozenset({"read_state"}), target_id="target:A"),
        InvestigationBudget(),
        InvestigationLease("lease:target", time.time() - 1, time.time() + 1000),
    )
    observation = _targeted_observation("target:B")
    with pytest.raises(PermissionError, match="scope|target"):
        c.authorize_observation(observation)
    assert c.observations_used == 0
    assert not c.observed_execution_ids


def test_target_scoped_authorization_requires_canonical_request():
    c = InvestigationController(
        "investigation:target",
        InvestigationScope("scope:target", allowed_observations=frozenset({"read_state"}), target_id="target:A"),
        InvestigationBudget(),
        InvestigationLease("lease:target", time.time() - 1, time.time() + 1000),
    )
    observation = Observation("read_state", ["yes", "no"], 1, execution_id="execution:no-request")
    with pytest.raises(PermissionError, match="canonical execution request"):
        c.authorize_observation(observation)
    assert c.observations_used == 0


def test_target_scoped_authorization_accepts_exact_request_target():
    c = InvestigationController(
        "investigation:target",
        InvestigationScope("scope:target", allowed_observations=frozenset({"read_state"}), target_id="target:A"),
        InvestigationBudget(),
        InvestigationLease("lease:target", time.time() - 1, time.time() + 1000),
    )
    observation = _targeted_observation("target:A")
    c.authorize_observation(observation)
    assert c.observations_used == 1
    assert observation.execution_id in c.observed_execution_ids
