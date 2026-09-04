"""Externally authorized expansion of CYDRA investigation authority.

Complexity can justify requesting more authority, but it can never grant it.
Dependency discovery is deliberately split into three states:

* an already-authorized dependency can be used without expansion;
* an out-of-scope dependency needed only for contextual understanding does not
  create an authority request;
* an out-of-scope dependency that must be actively investigated requires an
  explicit external expansion decision.

This module models dependency-scope expansion and adaptive budget/depth as
explicit grants issued outside the planner. Grants are bound to the current
authority fingerprint and therefore cannot self-approve or be replayed after
another authority change.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from .investigation_control import InvestigationBudget, InvestigationController, InvestigationScope


class DependencyNeed(str, Enum):
    """Why CYDRA is referring to a discovered dependency."""

    CONTEXT_ONLY = "CONTEXT_ONLY"
    ACTIVE_INVESTIGATION = "ACTIVE_INVESTIGATION"


@dataclass(frozen=True)
class DependencyCandidate:
    """A discovered dependency and the intended use of that dependency."""

    dependency_id: str
    source_target_id: str
    dependency_target_id: str
    kind: str
    authorized: bool = False
    depth: int = 0
    need: DependencyNeed = DependencyNeed.ACTIVE_INVESTIGATION

    def __post_init__(self) -> None:
        for name in ("dependency_id", "source_target_id", "dependency_target_id", "kind"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.depth < 0:
            raise ValueError("dependency depth must be non-negative")
        if not isinstance(self.need, DependencyNeed):
            raise ValueError("dependency need must be CONTEXT_ONLY or ACTIVE_INVESTIGATION")

    @property
    def requires_scope_expansion(self) -> bool:
        """Return whether this dependency crosses authority for active testing."""
        return not self.authorized and self.need == DependencyNeed.ACTIVE_INVESTIGATION

    @property
    def can_be_used_without_expansion(self) -> bool:
        """Return whether the dependency may be referenced without a new grant."""
        return self.authorized or self.need == DependencyNeed.CONTEXT_ONLY


def dependency_requires_expansion(candidate: DependencyCandidate) -> bool:
    """Classify the authority boundary without mutating controller state.

    Being out of scope is not sufficient by itself to request authority. The
    dependency must also be needed for active investigation. This keeps normal
    dependency/context reasoning from becoming an implicit scope expansion.
    """
    return candidate.requires_scope_expansion


class DependencyDecision(str, Enum):
    """External disposition of a discovered dependency-expansion request."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"


@dataclass(frozen=True)
class DependencyExpansionRequest:
    """A request for authority, never authority itself."""

    request_id: str
    parent_authority_fingerprint: str
    dependency_ids: frozenset[str]
    requested_observations: frozenset[str]
    requested_max_dependency_depth: int

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.parent_authority_fingerprint.strip():
            raise ValueError("request identity and parent authority fingerprint are required")
        if not self.dependency_ids:
            raise ValueError("dependency expansion request must identify candidates")
        if self.requested_max_dependency_depth < 0:
            raise ValueError("requested dependency depth must be non-negative")

    @property
    def fingerprint(self) -> str:
        payload = {
            "request_id": self.request_id,
            "parent_authority_fingerprint": self.parent_authority_fingerprint,
            "dependency_ids": sorted(self.dependency_ids),
            "requested_observations": sorted(self.requested_observations),
            "requested_max_dependency_depth": self.requested_max_dependency_depth,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class DependencyExpansionDecision:
    """An externally issued approve/deny decision bound to one exact request."""

    decision_id: str
    request_fingerprint: str
    decision: DependencyDecision
    authority_id: str
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.request_fingerprint.strip() or not self.authority_id.strip():
            raise ValueError("decision identity, request fingerprint, and authority identity are required")
        if not isinstance(self.decision, DependencyDecision):
            raise ValueError("decision must be APPROVED or DENIED")

    @property
    def fingerprint(self) -> str:
        payload = {
            "decision_id": self.decision_id,
            "request_fingerprint": self.request_fingerprint,
            "decision": self.decision.value,
            "authority_id": self.authority_id,
            "reason": self.reason,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class DependencyExpansionGrant:
    """An externally issued, single-parent dependency-scope authorization."""

    grant_id: str
    parent_authority_fingerprint: str
    added_observations: frozenset[str]
    dependency_ids: frozenset[str]
    max_dependency_depth: int
    authority_id: str

    def __post_init__(self) -> None:
        if not self.grant_id.strip() or not self.authority_id.strip():
            raise ValueError("grant_id and authority_id must not be empty")
        if not self.parent_authority_fingerprint.strip():
            raise ValueError("parent authority fingerprint is required")
        if self.max_dependency_depth < 0:
            raise ValueError("max_dependency_depth must be non-negative")

    @property
    def fingerprint(self) -> str:
        payload = {
            "grant_id": self.grant_id,
            "parent_authority_fingerprint": self.parent_authority_fingerprint,
            "added_observations": sorted(self.added_observations),
            "dependency_ids": sorted(self.dependency_ids),
            "max_dependency_depth": self.max_dependency_depth,
            "authority_id": self.authority_id,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class BudgetDepthExpansionGrant:
    """An externally issued increase bounded by an absolute ceiling."""

    grant_id: str
    parent_authority_fingerprint: str
    authority_id: str
    additional_rounds: int = 0
    additional_observations: int = 0
    additional_planning_steps: int = 0
    additional_hypotheses: int = 0
    additional_execution_cost: float = 0.0
    additional_dependency_depth: int = 0
    additional_branching_factor: int = 0
    ceiling_rounds: int | None = None
    ceiling_observations: int | None = None
    ceiling_planning_steps: int | None = None
    ceiling_hypotheses: int | None = None
    ceiling_execution_cost: float | None = None
    ceiling_dependency_depth: int | None = None
    ceiling_branching_factor: int | None = None

    def __post_init__(self) -> None:
        if not self.grant_id.strip() or not self.authority_id.strip() or not self.parent_authority_fingerprint.strip():
            raise ValueError("grant identity, authority identity, and parent fingerprint are required")
        for name in (
            "additional_rounds", "additional_observations", "additional_planning_steps",
            "additional_hypotheses", "additional_dependency_depth", "additional_branching_factor",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.additional_execution_cost < 0:
            raise ValueError("additional_execution_cost must be non-negative")
        for name in (
            "ceiling_rounds", "ceiling_observations", "ceiling_planning_steps",
            "ceiling_hypotheses", "ceiling_dependency_depth", "ceiling_branching_factor",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.ceiling_execution_cost is not None and self.ceiling_execution_cost < 0:
            raise ValueError("ceiling_execution_cost must be non-negative")


def build_dependency_expansion_request(
    controller: InvestigationController,
    candidates: Iterable[DependencyCandidate],
    *,
    request_id: str,
    dependency_ids: frozenset[str],
    requested_observations: frozenset[str],
    requested_max_dependency_depth: int,
) -> DependencyExpansionRequest:
    """Create a request only for dependencies requiring active expansion."""
    controller.require_active()
    candidate_map = {candidate.dependency_id: candidate for candidate in candidates}
    if not dependency_ids or any(candidate_id not in candidate_map for candidate_id in dependency_ids):
        raise PermissionError("dependency expansion request references an unknown dependency candidate")
    selected = [candidate_map[candidate_id] for candidate_id in dependency_ids]
    if any(candidate.authorized for candidate in selected):
        raise PermissionError("dependency expansion request must not include an already-authorized dependency")
    if any(candidate.need == DependencyNeed.CONTEXT_ONLY for candidate in selected):
        raise PermissionError("context-only dependency does not require scope expansion")
    if not all(candidate.requires_scope_expansion for candidate in selected):
        raise PermissionError("dependency expansion request contains a dependency that does not require expansion")
    return DependencyExpansionRequest(
        request_id=request_id,
        parent_authority_fingerprint=controller.authority_fingerprint,
        dependency_ids=dependency_ids,
        requested_observations=requested_observations,
        requested_max_dependency_depth=requested_max_dependency_depth,
    )


def apply_dependency_decision(
    controller: InvestigationController,
    request: DependencyExpansionRequest,
    decision: DependencyExpansionDecision,
    *,
    candidates: Iterable[DependencyCandidate],
    grant: DependencyExpansionGrant | None = None,
) -> None:
    """Apply an external decision; only APPROVED requests may become grants."""
    controller.require_active()
    if request.parent_authority_fingerprint != controller.authority_fingerprint:
        raise PermissionError("dependency decision is stale for the current authority")
    if decision.request_fingerprint != request.fingerprint:
        raise PermissionError("dependency decision is not bound to the exact expansion request")
    if decision.decision == DependencyDecision.DENIED:
        if grant is not None:
            raise PermissionError("denied dependency request cannot carry an expansion grant")
        return
    if grant is None:
        raise PermissionError("approved dependency request requires an externally issued grant")
    if grant.authority_id != decision.authority_id:
        raise PermissionError("dependency grant authority does not match the decision authority")
    if grant.parent_authority_fingerprint != request.parent_authority_fingerprint:
        raise PermissionError("dependency grant is not bound to the request authority")
    if grant.dependency_ids != request.dependency_ids:
        raise PermissionError("dependency grant does not match the approved dependency set")
    if grant.added_observations != request.requested_observations:
        raise PermissionError("dependency grant does not match the approved observation set")
    if grant.max_dependency_depth != request.requested_max_dependency_depth:
        raise PermissionError("dependency grant does not match the approved dependency depth")
    controller.apply_dependency_expansion(candidates, grant=grant)


def authorize_dependency_expansion(
    controller: InvestigationController,
    candidates: Iterable[DependencyCandidate],
    *,
    grant: DependencyExpansionGrant,
) -> None:
    """Apply only an externally authorized dependency grant to the live controller."""
    controller.require_active()
    if grant.parent_authority_fingerprint != controller.authority_fingerprint:
        raise PermissionError("dependency expansion grant is stale for the current authority")
    candidate_map = {candidate.dependency_id: candidate for candidate in candidates}
    selected = [candidate_map[candidate_id] for candidate_id in grant.dependency_ids if candidate_id in candidate_map]
    if len(selected) != len(grant.dependency_ids):
        raise PermissionError("dependency expansion grant references an unknown dependency candidate")
    if any(not candidate.authorized for candidate in selected):
        raise PermissionError("dependency expansion cannot self-authorize an unauthorized dependency")
    if any(candidate.depth > grant.max_dependency_depth for candidate in selected):
        raise PermissionError("dependency expansion exceeds the externally granted depth")
    if not selected and not grant.added_observations:
        raise PermissionError("dependency expansion grant contains no authorized expansion")
    new_scope = InvestigationScope(
        scope_id=controller.scope.scope_id,
        domain=controller.scope.domain,
        allowed_observations=controller.scope.allowed_observations | grant.added_observations,
        target_id=controller.scope.target_id,
        allow_meta_observations=controller.scope.allow_meta_observations,
    )
    controller.scope = new_scope
    controller.budget = InvestigationBudget(
        max_rounds=controller.budget.max_rounds,
        max_observations=controller.budget.max_observations,
        max_planning_steps=controller.budget.max_planning_steps,
        max_hypotheses=controller.budget.max_hypotheses,
        max_execution_cost=controller.budget.max_execution_cost,
        max_dependency_depth=max(controller.budget.max_dependency_depth, grant.max_dependency_depth),
        max_branching_factor=controller.budget.max_branching_factor,
    )


def apply_budget_depth_expansion(controller: InvestigationController, grant: BudgetDepthExpansionGrant) -> None:
    """Apply an externally issued budget/depth increase without planner authority."""
    controller.require_active()
    if grant.parent_authority_fingerprint != controller.authority_fingerprint:
        raise PermissionError("budget expansion grant is stale for the current authority")
    current = controller.budget
    values = {
        "max_rounds": current.max_rounds + grant.additional_rounds,
        "max_observations": current.max_observations + grant.additional_observations,
        "max_planning_steps": current.max_planning_steps + grant.additional_planning_steps,
        "max_hypotheses": current.max_hypotheses + grant.additional_hypotheses,
        "max_execution_cost": current.max_execution_cost + grant.additional_execution_cost,
        "max_dependency_depth": current.max_dependency_depth + grant.additional_dependency_depth,
        "max_branching_factor": current.max_branching_factor + grant.additional_branching_factor,
    }
    ceilings = {
        "max_rounds": grant.ceiling_rounds,
        "max_observations": grant.ceiling_observations,
        "max_planning_steps": grant.ceiling_planning_steps,
        "max_hypotheses": grant.ceiling_hypotheses,
        "max_execution_cost": grant.ceiling_execution_cost,
        "max_dependency_depth": grant.ceiling_dependency_depth,
        "max_branching_factor": grant.ceiling_branching_factor,
    }
    for name, ceiling in ceilings.items():
        if ceiling is not None and values[name] > ceiling:
            raise PermissionError(f"budget expansion exceeds absolute authority ceiling: {name}")
    controller.budget = InvestigationBudget(**values)
