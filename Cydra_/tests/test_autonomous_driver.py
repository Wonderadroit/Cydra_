import time

from cydra.autonomous_driver import (
    AutonomousInvestigationDriver,
    AutonomousTermination,
    InvestigationInputs,
)
from cydra.canonical_pipeline import CanonicalAuditPipeline
from cydra.investigation_control import (
    InvestigationBudget,
    InvestigationController,
    InvestigationDomain,
    InvestigationLease,
    InvestigationScope,
    TerminationReason,
)


class EmptyInputs:
    def propose(self, model):
        return InvestigationInputs((), ())


class NeverExecution:
    def execution_context(self, observation):
        raise AssertionError("execution must not be requested without inputs")


class NeverEvidence:
    def bind(self, result, observation, hypotheses):
        raise AssertionError("evidence binding must not run without execution")


def _controller():
    return InvestigationController(
        investigation_id="INV-DRIVER-1",
        scope=InvestigationScope(
            scope_id="scope-1",
            domain=InvestigationDomain.TARGET,
            allowed_observations=frozenset({"probe"}),
        ),
        budget=InvestigationBudget(max_rounds=3, max_hypotheses=3),
        lease=InvestigationLease(
            lease_id="lease-1",
            issued_at=time.time() - 1,
            expires_at=time.time() + 60,
            generation=0,
        ),
    )


def test_driver_stops_inside_controller_when_required_inputs_are_unavailable():
    pipeline = CanonicalAuditPipeline(lambda path: "IN_SCOPE")
    controller = _controller()
    driver = AutonomousInvestigationDriver(
        pipeline,
        controller,
        EmptyInputs(),
        NeverExecution(),
        NeverEvidence(),
    )

    result = driver.run()

    assert result.termination == AutonomousTermination.INPUT_UNRESOLVED
    assert result.controller_reason == TerminationReason.REQUIRED_EVIDENCE_UNAVAILABLE
    assert result.steps == ()
    assert controller.rounds_used == 1
    assert controller.observations_used == 0


def test_driver_does_not_run_when_controller_is_already_terminal():
    pipeline = CanonicalAuditPipeline(lambda path: "IN_SCOPE")
    controller = _controller()
    controller.terminate(TerminationReason.REQUIRED_EVIDENCE_UNAVAILABLE)
    driver = AutonomousInvestigationDriver(
        pipeline,
        controller,
        EmptyInputs(),
        NeverExecution(),
        NeverEvidence(),
    )

    result = driver.run()

    assert result.termination == AutonomousTermination.CONTROLLER
    assert result.controller_reason == TerminationReason.REQUIRED_EVIDENCE_UNAVAILABLE
    assert result.steps == ()
    assert controller.rounds_used == 0
