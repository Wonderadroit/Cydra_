"""Canonical composition boundary for CYDRA repository audits.

This module deliberately contains orchestration, not a second reasoning engine.
Passive repository intake is owned by ``RepositoryAuditSession`` and security
reasoning is owned by ``ReasoningOrchestrator``. The pipeline only composes those
canonical boundaries and preserves their trust/authority rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional

from .audit_session import AuditSessionResult, RepositoryAuditSession
from .planner import Hypothesis, Observation
from .reasoning_orchestrator import ReasoningOrchestrator, ReasoningPlan
from .system_model import SystemModel


@dataclass(frozen=True)
class CanonicalAuditResult:
    """Output of the passive repository-to-reasoning composition boundary."""

    session: AuditSessionResult
    orchestrator: ReasoningOrchestrator
    plan: Optional[ReasoningPlan]

    @property
    def model(self) -> SystemModel:
        """Return the one canonical model used by both intake and reasoning."""
        return self.orchestrator.model


class CanonicalAuditPipeline:
    """Compose passive intake and reasoning without creating a parallel engine.

    ``RepositoryAuditSession`` remains the only repository/AST intake boundary.
    ``ReasoningOrchestrator`` remains the only reasoning/execution boundary. This
    class never reads files, invokes compilers, executes commands, changes scope,
    or creates authority. External execution remains opt-in through the existing
    orchestrator gateway and investigation authorization APIs.
    """

    def __init__(self, scope_resolver: Callable[[str], object], model: SystemModel | None = None):
        self.model = model or SystemModel()
        self.session = RepositoryAuditSession(scope_resolver)
        self.orchestrator = ReasoningOrchestrator(self.model)

    def ingest(
        self,
        paths: Iterable[str],
        sources: Mapping[str, str],
        solidity_asts: Mapping[str, dict[str, Any]] | None = None,
    ) -> AuditSessionResult:
        """Perform one atomic passive intake into the pipeline's canonical model."""
        result = self.session.scan(
            paths,
            sources,
            solidity_asts=solidity_asts,
            canonical=self.model,
        )
        self.orchestrator.attach_audit_session(result)
        return result

    def plan(
        self,
        hypotheses: Iterable[Hypothesis],
        observations: Iterable[Observation],
        invariant_hypotheses: Optional[Mapping[str, Iterable[str]]] = None,
        verified_invariant_hypotheses: Optional[Mapping[str, Hypothesis]] = None,
    ) -> Optional[ReasoningPlan]:
        """Plan the next authorized observation through the canonical orchestrator."""
        return self.orchestrator.plan_next(
            hypotheses,
            observations,
            invariant_hypotheses=invariant_hypotheses,
            verified_invariant_hypotheses=verified_invariant_hypotheses,
        )

    def run_passive_to_plan(
        self,
        paths: Iterable[str],
        sources: Mapping[str, str],
        hypotheses: Iterable[Hypothesis],
        observations: Iterable[Observation],
        *,
        solidity_asts: Mapping[str, dict[str, Any]] | None = None,
        invariant_hypotheses: Optional[Mapping[str, Iterable[str]]] = None,
        verified_invariant_hypotheses: Optional[Mapping[str, Hypothesis]] = None,
    ) -> CanonicalAuditResult:
        """Run the complete passive-intake → model → planning composition.

        This method intentionally stops at a persisted plan. It does not execute an
        observation or manufacture evidence. Callers must use the existing
        authorization and gateway boundaries for any subsequent external action.
        """
        session = self.ingest(paths, sources, solidity_asts=solidity_asts)
        plan = self.plan(
            hypotheses,
            observations,
            invariant_hypotheses=invariant_hypotheses,
            verified_invariant_hypotheses=verified_invariant_hypotheses,
        )
        return CanonicalAuditResult(session=session, orchestrator=self.orchestrator, plan=plan)
