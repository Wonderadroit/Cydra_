"""Controller-bound adapter for turning repository reasoning inputs into one plan.

The driver deliberately contains no vulnerability heuristics and no authority
minting. A reasoning provider proposes hypotheses and observations from the
canonical model; the live InvestigationController decides whether the chosen
observation is allowed, and the ReasoningOrchestrator performs the canonical
plan/execution binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .investigation_control import InvestigationController
from .planner import Hypothesis, Observation, Plan
from .reasoning_orchestrator import AuthorizedInvestigationPlan, ReasoningOrchestrator
from .system_model import SystemModel


@dataclass(frozen=True)
class ReasoningInputs:
    """Provider output. It contains proposals, never an execution capability."""

    hypotheses: tuple[Hypothesis, ...]
    observations: tuple[Observation, ...]

    @classmethod
    def from_sequences(
        cls,
        hypotheses: Sequence[Hypothesis],
        observations: Sequence[Observation],
    ) -> "ReasoningInputs":
        return cls(tuple(hypotheses), tuple(observations))


class ReasoningInputProvider(Protocol):
    """Pure reasoning boundary supplied by a model, rules engine, or adapter."""

    def propose(self, model: SystemModel) -> ReasoningInputs:
        """Derive bounded reasoning proposals from canonical state only."""
        ...


@dataclass(frozen=True)
class DriverPlan:
    """One controller-authorized plan ready for the existing execution path."""

    inputs: ReasoningInputs
    plan: Plan
    authorized_plan: AuthorizedInvestigationPlan


class ControllerBoundReasoningDriver:
    """Connect provider proposals to the existing controller and orchestrator.

    This is intentionally a thin adapter. In particular, it does not:
    - infer vulnerability findings,
    - create or widen scope,
    - create execution authorizations itself,
    - bypass the ExternalExecutionGateway, or
    - treat persisted authority as executable.
    """

    def __init__(
        self,
        orchestrator: ReasoningOrchestrator,
        controller: InvestigationController,
        provider: ReasoningInputProvider,
    ) -> None:
        self.orchestrator = orchestrator
        self.controller = controller
        self.provider = provider

    def propose_and_plan(self, *, authorization, dependency_depth: int = 0) -> DriverPlan | None:
        self.controller.require_active()
        self.controller.begin_round()
        inputs = self.provider.propose(self.orchestrator.model)
        if not isinstance(inputs, ReasoningInputs):
            raise TypeError("reasoning provider must return ReasoningInputs")
        self.controller.register_hypotheses(len(inputs.hypotheses))
        plan = self.controller.plan(list(inputs.hypotheses), list(inputs.observations))
        if plan is None:
            return None
        selected = next(
            (observation for observation in inputs.observations if observation.name == plan.observation),
            None,
        )
        if selected is None:
            raise RuntimeError("controller selected an observation absent from provider inputs")
        authorized_plan = self.orchestrator.record_investigation_plan(
            self.controller,
            plan,
            list(inputs.hypotheses),
            selected,
            authorization=authorization,
            dependency_depth=dependency_depth,
        )
        return DriverPlan(inputs=inputs, plan=plan, authorized_plan=authorized_plan)
