from dataclasses import dataclass

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.foundry import FoundryAuthorization
from cydra.investigation_control import (
    InvestigationBudget,
    InvestigationController,
    InvestigationLease,
    InvestigationScope,
    TerminationReason,
)
from cydra.planner import Hypothesis, Observation
from cydra.reasoning_driver import ControllerBoundReasoningDriver, ReasoningInputs
from cydra.reasoning_orchestrator import ReasoningOrchestrator


@dataclass(frozen=True)
class Provider:
    inputs: ReasoningInputs

    def propose(self, model):
        return self.inputs


def controller(*, budget=None):
    return InvestigationController(
        "inv-driver",
        InvestigationScope("scope-driver", allowed_observations=frozenset({"check"})),
        budget or InvestigationBudget(max_rounds=2, max_observations=1, max_planning_steps=2, max_hypotheses=4, max_execution_cost=10.0),
        InvestigationLease("lease-driver", 100.0, 9999999999.0, generation=1),
    )


def inputs():
    authorization = FoundryAuthorization("base-driver")
    request = ExecutionRequest(
        "exec-driver",
        "fake",
        "fixture",
        ("fake", "check"),
        "project:fixture",
        authorization.authorization_id,
    )
    observations = (
        Observation(
            "check",
            ["yes", "no"],
            1.0,
            authorized=True,
            execution_id=request.execution_id,
            execution_request=request,
        ),
    )
    hypotheses = (
        Hypothesis("h1", 0.5, {"check": {"yes": 0.9, "no": 0.1}}),
        Hypothesis("h2", 0.5, {"check": {"yes": 0.1, "no": 0.9}}),
    )
    return authorization, ReasoningInputs(hypotheses, observations)


def test_driver_connects_provider_to_live_controller_without_executing():
    authorization, proposed = inputs()
    orchestrator = ReasoningOrchestrator()
    ctrl = controller()
    driver = ControllerBoundReasoningDriver(orchestrator, ctrl, Provider(proposed))

    result = driver.propose_and_plan(authorization=authorization)

    assert result is not None
    assert result.plan.observation == "check"
    assert result.authorized_plan.authorization.investigation_id == "inv-driver"
    assert ctrl.rounds_used == 1
    assert ctrl.planning_steps_used == 1
    assert ctrl.observations_used == 1
    assert not any(event["type"] == "EXTERNAL_EXECUTION_COMPLETED" for event in orchestrator.graph.history)
    assert orchestrator.model.nodes["observation:check"].attributes["planned"] is True


def test_driver_rejects_provider_output_that_is_not_reasoning_inputs():
    authorization, _ = inputs()
    orchestrator = ReasoningOrchestrator()
    driver = ControllerBoundReasoningDriver(orchestrator, controller(), Provider(None))

    with pytest.raises(TypeError, match="ReasoningInputs"):
        driver.propose_and_plan(authorization=authorization)


def test_driver_does_not_mint_authority_when_controller_is_already_budget_exhausted():
    authorization, proposed = inputs()
    ctrl = controller(budget=InvestigationBudget(
        max_rounds=2,
        max_observations=1,
        max_planning_steps=0,
        max_hypotheses=4,
        max_execution_cost=10.0,
    ))
    orchestrator = ReasoningOrchestrator()
    driver = ControllerBoundReasoningDriver(orchestrator, ctrl, Provider(proposed))

    with pytest.raises(RuntimeError):
        driver.propose_and_plan(authorization=authorization)

    assert ctrl.termination == TerminationReason.BUDGET_EXHAUSTED
    assert orchestrator.model.nodes == {}
    assert orchestrator.graph.history == []
    assert ctrl.observations_used == 0
