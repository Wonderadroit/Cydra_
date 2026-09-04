"""Bounded control plane for autonomous CYDRA investigations.

The planner may optimize observations, but it never owns authority. Scope,
budget, dependency depth, and lease state are authoritative inputs to every
planning/execution decision. A target investigation cannot silently turn into
a meta-investigation or extend its own authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Iterable, Mapping, TYPE_CHECKING

from .planner import Observation, Plan, choose_next_observation

if TYPE_CHECKING:
    from .learning import LearningStore


class InvestigationDomain(str, Enum):
    TARGET = "target"
    META = "meta"


class TerminationReason(str, Enum):
    ACTIVE = "ACTIVE"
    HYPOTHESIS_RESOLVED = "HYPOTHESIS_RESOLVED"
    HYPOTHESIS_DISPROVEN = "HYPOTHESIS_DISPROVEN"
    CAUSAL_CHAIN_ESTABLISHED = "CAUSAL_CHAIN_ESTABLISHED"
    CAUSAL_CHAIN_BLOCKED = "CAUSAL_CHAIN_BLOCKED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    DEPTH_LIMIT_REACHED = "DEPTH_LIMIT_REACHED"
    NO_HIGH_VALUE_OBSERVATION = "NO_HIGH_VALUE_OBSERVATION"
    REQUIRED_EVIDENCE_UNAVAILABLE = "REQUIRED_EVIDENCE_UNAVAILABLE"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    SCOPE_EXHAUSTED = "SCOPE_EXHAUSTED"


@dataclass(frozen=True)
class InvestigationScope:
    """Immutable authority envelope for one investigation."""

    scope_id: str
    domain: InvestigationDomain = InvestigationDomain.TARGET
    allowed_observations: frozenset[str] = frozenset()
    target_id: str | None = None
    allow_meta_observations: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope_id, str) or not self.scope_id.strip():
            raise ValueError("scope_id must not be empty")
        if self.target_id is not None and (not isinstance(self.target_id, str) or not self.target_id.strip()):
            raise ValueError("target_id must be non-empty when provided")

    def allows(self, observation: Observation) -> bool:
        if not observation.authorized:
            return False
        if observation.name not in self.allowed_observations:
            return False
        if self.domain == InvestigationDomain.TARGET and observation.domain != InvestigationDomain.TARGET:
            return False
        if self.domain == InvestigationDomain.META and observation.domain != InvestigationDomain.META:
            return False
        if observation.domain == InvestigationDomain.META and not self.allow_meta_observations:
            return False
        if self.target_id is not None and observation.execution_request is not None:
            if observation.execution_request.target != self.target_id:
                return False
        return True


@dataclass(frozen=True)
class InvestigationBudget:
    """Finite resource limits. None are extendable by the planner."""

    max_rounds: int = 10
    max_observations: int = 20
    max_planning_steps: int = 40
    max_hypotheses: int = 20
    max_execution_cost: float = 100.0
    max_dependency_depth: int = 3
    max_branching_factor: int = 8

    def __post_init__(self) -> None:
        for name in (
            "max_rounds",
            "max_observations",
            "max_planning_steps",
            "max_hypotheses",
            "max_dependency_depth",
            "max_branching_factor",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.max_execution_cost < 0:
            raise ValueError("max_execution_cost must be non-negative")


@dataclass(frozen=True)
class InvestigationLease:
    """Time and generation authority issued by an external controller."""

    lease_id: str
    issued_at: float
    expires_at: float
    generation: int = 0

    def __post_init__(self) -> None:
        if not self.lease_id.strip():
            raise ValueError("lease_id must not be empty")
        if self.expires_at < self.issued_at:
            raise ValueError("lease expires before it is issued")
        if self.generation < 0:
            raise ValueError("lease generation must be non-negative")

    def is_active(self, now: float | None = None) -> bool:
        return (time.time() if now is None else now) < self.expires_at


@dataclass
class InvestigationController:
    """Authoritative finite-state controller around planner decisions."""

    investigation_id: str
    scope: InvestigationScope
    budget: InvestigationBudget
    lease: InvestigationLease
    rounds_used: int = 0
    observations_used: int = 0
    planning_steps_used: int = 0
    hypotheses_seen: int = 0
    execution_cost_used: float = 0.0
    dependency_depth: int = 0
    observed_execution_ids: set[str] = field(default_factory=set)
    consumed_expansion_grant_ids: set[str] = field(default_factory=set)
    termination: TerminationReason = TerminationReason.ACTIVE

    def __post_init__(self) -> None:
        if not self.investigation_id.strip():
            raise ValueError("investigation_id must not be empty")
        if self.scope.domain == InvestigationDomain.TARGET and self.scope.allow_meta_observations:
            raise ValueError("target investigations cannot authorize meta observations")
        if any(not grant_id.strip() for grant_id in self.consumed_expansion_grant_ids):
            raise ValueError("consumed expansion grant IDs must be non-empty")
        self._refresh_terminal_state()

    @property
    def active(self) -> bool:
        self._refresh_terminal_state()
        return self.termination == TerminationReason.ACTIVE

    @property
    def remaining_execution_cost(self) -> float:
        return max(0.0, self.budget.max_execution_cost - self.execution_cost_used)

    def _refresh_terminal_state(self) -> None:
        if self.termination != TerminationReason.ACTIVE:
            return
        if not self.lease.is_active():
            self.termination = TerminationReason.LEASE_EXPIRED
        elif self.rounds_used >= self.budget.max_rounds:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
        elif self.observations_used >= self.budget.max_observations:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
        elif self.planning_steps_used >= self.budget.max_planning_steps:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
        elif self.execution_cost_used >= self.budget.max_execution_cost:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
        elif self.dependency_depth > self.budget.max_dependency_depth:
            self.termination = TerminationReason.DEPTH_LIMIT_REACHED

    def require_active(self, *, now: float | None = None) -> None:
        if self.termination == TerminationReason.ACTIVE and not self.lease.is_active(now):
            self.termination = TerminationReason.LEASE_EXPIRED
        if self.termination != TerminationReason.ACTIVE:
            raise RuntimeError(f"investigation is not active: {self.termination.value}")

    def register_hypotheses(self, count: int) -> None:
        if count < 0:
            raise ValueError("hypothesis count must be non-negative")
        self.require_active()
        if self.hypotheses_seen + count > self.budget.max_hypotheses:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
            raise RuntimeError("hypothesis budget exhausted")
        self.hypotheses_seen += count

    def plan(
        self,
        hypotheses,
        observations: Iterable[Observation],
        *,
        learning_store: "LearningStore | None" = None,
    ) -> Plan | None:
        """Spend one planning step and choose only observations inside authority.

        When learning is supplied, the controller itself issues the immutable
        learning context from its live authority envelope and validates that
        context immediately before and after planner selection. Callers cannot
        manufacture authority context or silently replace the learning basis.
        """
        self.require_active()
        candidates = [obs for obs in observations if self.scope.allows(obs)]
        if len(candidates) > self.budget.max_branching_factor:
            candidates = sorted(candidates, key=lambda obs: obs.name)[: self.budget.max_branching_factor]
        if not candidates:
            self.termination = TerminationReason.SCOPE_EXHAUSTED
            return None
        if self.planning_steps_used >= self.budget.max_planning_steps:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
            return None

        learning_context = None
        if learning_store is not None:
            from .learning_authority import issue_learning_context, validate_learning_context

            learning_context = issue_learning_context(self, learning_store)

        self.planning_steps_used += 1
        if learning_context is not None:
            validate_learning_context(self, learning_store, learning_context)
        plan = choose_next_observation(
            hypotheses,
            candidates,
            learning_store=learning_store,
            learning_context=learning_context,
        )
        if learning_context is not None:
            validate_learning_context(self, learning_store, learning_context)
        if plan is None or plan.utility <= 0:
            self.termination = TerminationReason.NO_HIGH_VALUE_OBSERVATION
            return None
        return plan

    def authorize_observation(self, observation: Observation, *, dependency_depth: int = 0) -> None:
        """Authorize one exact observation immediately before execution request creation."""
        self.require_active()
        if not self.scope.allows(observation):
            raise PermissionError("observation is outside the investigation scope")
        if self.scope.target_id is not None:
            request = observation.execution_request
            if request is None:
                raise PermissionError("target-scoped execution requires a canonical execution request")
            if request.target != self.scope.target_id:
                raise PermissionError("observation execution target is outside the investigation target scope")
        if dependency_depth > self.budget.max_dependency_depth:
            self.termination = TerminationReason.DEPTH_LIMIT_REACHED
            raise PermissionError("observation exceeds dependency-depth limit")
        if observation.execution_id in self.observed_execution_ids:
            raise ValueError("observation execution identity has already been authorized")
        if self.observations_used >= self.budget.max_observations:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
            raise PermissionError("observation budget exhausted")
        if self.execution_cost_used + observation.cost > self.budget.max_execution_cost:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
            raise PermissionError("execution-cost budget exhausted")
        self.dependency_depth = max(self.dependency_depth, dependency_depth)
        self.observed_execution_ids.add(observation.execution_id)
        self.observations_used += 1
        self.execution_cost_used += observation.cost

    def apply_dependency_expansion(self, candidates, *, grant) -> None:
        """Consume one external dependency grant and record its lineage locally.

        The expansion helpers remain the authority-validation boundary. This
        controller method makes grant consumption part of the authoritative
        lifecycle, rejects replay, and never executes an observation itself.
        """
        self.require_active()
        if grant.grant_id in self.consumed_expansion_grant_ids:
            raise PermissionError("dependency expansion grant has already been consumed")
        from .investigation_expansion import authorize_dependency_expansion

        authorize_dependency_expansion(self, candidates, grant=grant)
        self.consumed_expansion_grant_ids.add(grant.grant_id)

    def apply_budget_depth_expansion(self, grant) -> None:
        """Consume one external adaptive-budget grant without planner authority."""
        self.require_active()
        if grant.grant_id in self.consumed_expansion_grant_ids:
            raise PermissionError("budget expansion grant has already been consumed")
        from .investigation_expansion import apply_budget_depth_expansion

        apply_budget_depth_expansion(self, grant)
        self.consumed_expansion_grant_ids.add(grant.grant_id)

    def begin_round(self) -> None:
        self.require_active()
        if self.rounds_used >= self.budget.max_rounds:
            self.termination = TerminationReason.BUDGET_EXHAUSTED
            raise RuntimeError("round budget exhausted")
        self.rounds_used += 1

    def terminate(self, reason: TerminationReason) -> None:
        if reason == TerminationReason.ACTIVE:
            raise ValueError("terminal reason must not be ACTIVE")
        if self.termination != TerminationReason.ACTIVE:
            if self.termination != reason:
                raise RuntimeError("investigation already terminated")
            return
        self.termination = reason

    def _authority_payload(self) -> dict[str, object]:
        return {
            "investigation_id": self.investigation_id,
            "scope": {
                "scope_id": self.scope.scope_id,
                "domain": self.scope.domain.value,
                "allowed_observations": sorted(self.scope.allowed_observations),
                "target_id": self.scope.target_id,
                "allow_meta_observations": self.scope.allow_meta_observations,
            },
            "budget": {
                "max_rounds": self.budget.max_rounds,
                "max_observations": self.budget.max_observations,
                "max_planning_steps": self.budget.max_planning_steps,
                "max_hypotheses": self.budget.max_hypotheses,
                "max_execution_cost": self.budget.max_execution_cost,
                "max_dependency_depth": self.budget.max_dependency_depth,
                "max_branching_factor": self.budget.max_branching_factor,
            },
            "lease": {
                "lease_id": self.lease.lease_id,
                "issued_at": self.lease.issued_at,
                "expires_at": self.lease.expires_at,
                "generation": self.lease.generation,
            },
        }

    @property
    def authority_fingerprint(self) -> str:
        payload = json.dumps(self._authority_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def snapshot(self) -> dict[str, object]:
        """Return an audit-friendly state snapshot bound to its authority."""
        self._refresh_terminal_state()
        return {
            **self._authority_payload(),
            "authority_fingerprint": self.authority_fingerprint,
            "usage": {
                "rounds_used": self.rounds_used,
                "observations_used": self.observations_used,
                "planning_steps_used": self.planning_steps_used,
                "hypotheses_seen": self.hypotheses_seen,
                "execution_cost_used": self.execution_cost_used,
                "dependency_depth": self.dependency_depth,
                "observed_execution_ids": sorted(self.observed_execution_ids),
                "consumed_expansion_grant_ids": sorted(self.consumed_expansion_grant_ids),
            },
            "termination": self.termination.value,
        }

    @classmethod
    def from_snapshot(
        cls,
        payload: Mapping[str, object],
        *,
        expected_authority_fingerprint: str,
        now: float | None = None,
    ) -> "InvestigationController":
        """Rehydrate only when an external authority confirms the envelope."""
        if not expected_authority_fingerprint.strip():
            raise ValueError("expected authority fingerprint is required")
        try:
            scope_data = payload["scope"]
            budget_data = payload["budget"]
            lease_data = payload["lease"]
            usage = payload["usage"]
            supplied_fingerprint = str(payload["authority_fingerprint"])
            if not all(isinstance(value, Mapping) for value in (scope_data, budget_data, lease_data, usage)):
                raise ValueError("investigation snapshot sections are malformed")
            scope = InvestigationScope(
                scope_id=str(scope_data["scope_id"]),
                domain=InvestigationDomain(str(scope_data["domain"])),
                allowed_observations=frozenset(str(v) for v in scope_data.get("allowed_observations", [])),
                target_id=scope_data.get("target_id"),
                allow_meta_observations=bool(scope_data.get("allow_meta_observations", False)),
            )
            budget = InvestigationBudget(**{key: budget_data[key] for key in (
                "max_rounds", "max_observations", "max_planning_steps", "max_hypotheses",
                "max_execution_cost", "max_dependency_depth", "max_branching_factor",
            )})
            lease = InvestigationLease(
                lease_id=str(lease_data["lease_id"]),
                issued_at=float(lease_data["issued_at"]),
                expires_at=float(lease_data["expires_at"]),
                generation=int(lease_data.get("generation", 0)),
            )
            termination = TerminationReason(str(payload.get("termination", "ACTIVE")))
            controller = cls(
                investigation_id=str(payload["investigation_id"]),
                scope=scope,
                budget=budget,
                lease=lease,
                rounds_used=int(usage.get("rounds_used", 0)),
                observations_used=int(usage.get("observations_used", 0)),
                planning_steps_used=int(usage.get("planning_steps_used", 0)),
                hypotheses_seen=int(usage.get("hypotheses_seen", 0)),
                execution_cost_used=float(usage.get("execution_cost_used", 0.0)),
                dependency_depth=int(usage.get("dependency_depth", 0)),
                observed_execution_ids=set(str(v) for v in usage.get("observed_execution_ids", [])),
                consumed_expansion_grant_ids=set(str(v) for v in usage.get("consumed_expansion_grant_ids", [])),
                termination=termination,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed investigation snapshot: {exc}") from exc
        if supplied_fingerprint != expected_authority_fingerprint or controller.authority_fingerprint != expected_authority_fingerprint:
            raise ValueError("investigation authority fingerprint mismatch")
        if controller.termination == TerminationReason.ACTIVE and not controller.lease.is_active(now):
            controller.termination = TerminationReason.LEASE_EXPIRED
        return controller
