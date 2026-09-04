"""Controller-bound adapter for CYDRA's autonomous investigation lifecycle.

This module composes existing authority, planning, gateway, evidence, causal,
and finding-promotion boundaries. It deliberately does not implement a second
vulnerability scanner or create authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol, Sequence

from .canonical_pipeline import CanonicalAuditPipeline
from .finding_gate import GateDecision
from .finding_persistence import persist_finding
from .finding_synthesis import ReasoningFindingDraft, synthesize_reasoning_findings
from .investigation_control import InvestigationController, TerminationReason
from .planner import Hypothesis, Observation
from .security_claim_reasoning import SecurityClaimDraftProvider
from .security_reasoning import SecurityReasoningInputs, persist_security_claims
from .updater import EvidencePolarity


class AutonomousTermination(str, Enum):
    CONTROLLER = "CONTROLLER"
    INPUT_UNRESOLVED = "INPUT_UNRESOLVED"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class InvestigationInputs:
    """Candidate reasoning inputs supplied without historical oracle state."""
    hypotheses: tuple[Hypothesis, ...]
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class AutonomousStep:
    step: int
    observation_name: str
    execution_id: str
    outcome: str
    evidence_id: str


@dataclass(frozen=True)
class AutonomousRunResult:
    termination: AutonomousTermination
    controller_reason: TerminationReason
    steps: tuple[AutonomousStep, ...]
    promoted_findings: tuple[str, ...] = ()
    finding_promotion_attempts: tuple[tuple[str, GateDecision, tuple[str, ...]], ...] = ()


class InvestigationInputProvider(Protocol):
    def propose(self, model) -> InvestigationInputs:
        """Derive the next competing hypotheses and candidate observations."""


class ObservationExecutionProvider(Protocol):
    def execution_context(self, observation: Observation) -> tuple[str, object]:
        """Return adapter identity and an already-issued base execution authorization."""


class EvidenceBindingProvider(Protocol):
    def bind(
        self,
        result,
        observation: Observation,
        hypotheses: Sequence[Hypothesis],
    ) -> tuple[str, Mapping[str, EvidencePolarity] | None, str | None]:
        """Bind the external result to canonical evidence and causal metadata."""


class FindingDraftProvider(Protocol):
    def propose(self, model, step: AutonomousStep) -> Sequence[ReasoningFindingDraft]:
        """Emit explicit claims from already-verified canonical reasoning state."""


class AutonomousInvestigationDriver:
    """Drive one bounded investigation through authoritative reasoning/execution.

    Finding promotion uses the evidence-gated security-claim reasoner by default.
    Specialized providers remain injectable, but every draft still passes through
    the normal graph-aware finding gate. This driver never invents vulnerability
    claims or creates execution authority.
    """

    def __init__(
        self,
        pipeline: CanonicalAuditPipeline,
        controller: InvestigationController,
        input_provider: InvestigationInputProvider,
        execution_provider: ObservationExecutionProvider,
        evidence_provider: EvidenceBindingProvider,
        finding_provider: FindingDraftProvider | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.controller = controller
        self.input_provider = input_provider
        self.execution_provider = execution_provider
        self.evidence_provider = evidence_provider
        self.finding_provider = finding_provider or SecurityClaimDraftProvider()

    def _result(self, termination, steps, promoted, attempts):
        return AutonomousRunResult(termination, self.controller.termination, tuple(steps), tuple(promoted), tuple(attempts))

    def _promote_drafts(self, drafts, attempts, promoted):
        if not drafts:
            return
        synthesized = synthesize_reasoning_findings(self.pipeline.orchestrator.graph, drafts)
        from .finding_pipeline import promote_candidate
        for item in synthesized:
            result = promote_candidate(item.candidate, item.finding, self.pipeline.orchestrator.graph)
            attempts.append((item.finding.finding_id, result.decision, tuple(result.reasons)))
            if result.decision == GateDecision.READY:
                persist_finding(self.pipeline.orchestrator.graph, item.finding)
                promoted.append(item.finding.finding_id)

    def run(self) -> AutonomousRunResult:
        steps = []
        promoted = []
        attempts = []
        while self.controller.active:
            try:
                self.controller.begin_round()
                inputs = self.input_provider.propose(self.pipeline.model)
                if not inputs.hypotheses or not inputs.observations:
                    self.controller.terminate(TerminationReason.REQUIRED_EVIDENCE_UNAVAILABLE)
                    return self._result(AutonomousTermination.INPUT_UNRESOLVED, steps, promoted, attempts)
                self.controller.register_hypotheses(len(inputs.hypotheses))
                plan = self.controller.plan(inputs.hypotheses, inputs.observations)
                if plan is None:
                    return self._result(AutonomousTermination.CONTROLLER, steps, promoted, attempts)
                observation = next(item for item in inputs.observations if item.name == plan.observation)
                adapter_name, base_authorization = self.execution_provider.execution_context(observation)
                planned = self.pipeline.orchestrator.record_investigation_plan(
                    self.controller, plan, list(inputs.hypotheses), observation,
                    authorization=base_authorization, dependency_depth=self.controller.dependency_depth,
                )
                if isinstance(inputs, SecurityReasoningInputs):
                    persist_security_claims(self.pipeline.orchestrator.graph, inputs)
                result = self.pipeline.orchestrator.execute_investigation_plan(adapter_name, planned)
                evidence_id, polarity, causal_chain_id = self.evidence_provider.bind(result, planned.observation, inputs.hypotheses)
                finalize = getattr(self.evidence_provider, "finalize", None)
                update = self.pipeline.orchestrator.ingest_observation_result(
                    result, planned.observation, list(inputs.hypotheses), evidence_id,
                    evidence_polarity=polarity,
                    causal_chain_id=None if callable(finalize) else causal_chain_id,
                )
                if callable(finalize):
                    finalize(result, planned.observation, inputs.hypotheses, update)
                step = AutonomousStep(self.controller.rounds_used, planned.observation.name, result.execution_id, result.outcome, evidence_id)
                steps.append(step)
                if self.finding_provider is not None:
                    self._promote_drafts(self.finding_provider.propose(self.pipeline.model, step), attempts, promoted)
            except (PermissionError, RuntimeError, ValueError, KeyError):
                return self._result(AutonomousTermination.CONTROLLER, steps, promoted, attempts)
        return self._result(AutonomousTermination.CONTROLLER, steps, promoted, attempts)
