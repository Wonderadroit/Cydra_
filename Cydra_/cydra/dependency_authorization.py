"""Explicit discovery -> request -> approval/denial lifecycle for dependencies.

Dependency discovery is evidence about possible relationships, not permission.
A request records what additional dependency scope is being requested. An
externally issued decision must explicitly approve or deny that request. Only
an approved request may be converted into the existing externally authorized
DependencyExpansionGrant boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from .investigation_expansion import DependencyCandidate, DependencyExpansionGrant


class DependencyAuthorizationError(ValueError):
    """Raised when a dependency authorization lifecycle is invalid."""


class DependencyDecision(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"


@dataclass(frozen=True)
class DependencyExpansionRequest:
    """A request for additional dependency scope; it grants nothing."""

    request_id: str
    investigation_id: str
    parent_authority_fingerprint: str
    dependency_ids: frozenset[str]
    requested_observations: frozenset[str]
    requested_max_depth: int

    def __post_init__(self) -> None:
        for name in ("request_id", "investigation_id", "parent_authority_fingerprint"):
            if not getattr(self, name).strip():
                raise DependencyAuthorizationError(f"{name} must not be empty")
        if not self.dependency_ids:
            raise DependencyAuthorizationError("dependency request must name at least one candidate")
        if self.requested_max_depth < 0:
            raise DependencyAuthorizationError("requested_max_depth must be non-negative")

    @property
    def fingerprint(self) -> str:
        payload = {
            "request_id": self.request_id,
            "investigation_id": self.investigation_id,
            "parent_authority_fingerprint": self.parent_authority_fingerprint,
            "dependency_ids": sorted(self.dependency_ids),
            "requested_observations": sorted(self.requested_observations),
            "requested_max_depth": self.requested_max_depth,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class DependencyAuthorizationDecision:
    """An externally issued approval or denial bound to one exact request."""

    decision_id: str
    request_id: str
    request_fingerprint: str
    decision: DependencyDecision
    authority_id: str
    reason: str
    granted_observations: frozenset[str] = frozenset()
    granted_max_depth: int = 0

    def __post_init__(self) -> None:
        for name in ("decision_id", "request_id", "request_fingerprint", "authority_id", "reason"):
            if not getattr(self, name).strip():
                raise DependencyAuthorizationError(f"{name} must not be empty")
        if self.granted_max_depth < 0:
            raise DependencyAuthorizationError("granted_max_depth must be non-negative")
        if self.decision == DependencyDecision.DENIED and (self.granted_observations or self.granted_max_depth):
            raise DependencyAuthorizationError("denied dependency requests cannot contain grants")

    @property
    def fingerprint(self) -> str:
        payload = {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "decision": self.decision.value,
            "authority_id": self.authority_id,
            "reason": self.reason,
            "granted_observations": sorted(self.granted_observations),
            "granted_max_depth": self.granted_max_depth,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def discover_dependency(candidate: DependencyCandidate) -> DependencyCandidate:
    """Record discovery without changing its authorization status."""
    if candidate.authorized:
        raise DependencyAuthorizationError("discovery must not manufacture authorization")
    return candidate


def create_dependency_request(
    *,
    request_id: str,
    investigation_id: str,
    authority_fingerprint: str,
    candidates: tuple[DependencyCandidate, ...],
    requested_observations: frozenset[str],
    requested_max_depth: int,
) -> DependencyExpansionRequest:
    """Create an explicit request from discovered candidates; no scope changes."""
    if not candidates:
        raise DependencyAuthorizationError("dependency request requires discovered candidates")
    if any(candidate.authorized for candidate in candidates):
        raise DependencyAuthorizationError("requests must start from discovered, not pre-authorized, candidates")
    return DependencyExpansionRequest(
        request_id=request_id,
        investigation_id=investigation_id,
        parent_authority_fingerprint=authority_fingerprint,
        dependency_ids=frozenset(candidate.dependency_id for candidate in candidates),
        requested_observations=requested_observations,
        requested_max_depth=requested_max_depth,
    )


def approve_dependency_request(
    request: DependencyExpansionRequest,
    *,
    decision_id: str,
    authority_id: str,
    reason: str,
    granted_observations: frozenset[str] | None = None,
    granted_max_depth: int | None = None,
) -> DependencyAuthorizationDecision:
    """Issue an external approval decision; callers still need the grant boundary."""
    observations = request.requested_observations if granted_observations is None else granted_observations
    depth = request.requested_max_depth if granted_max_depth is None else granted_max_depth
    if not observations:
        raise DependencyAuthorizationError("approval must authorize at least one observation")
    if depth > request.requested_max_depth:
        raise DependencyAuthorizationError("approval cannot exceed the requested depth")
    return DependencyAuthorizationDecision(
        decision_id, request.request_id, request.fingerprint,
        DependencyDecision.APPROVED, authority_id, reason,
        observations, depth,
    )


def deny_dependency_request(
    request: DependencyExpansionRequest,
    *,
    decision_id: str,
    authority_id: str,
    reason: str,
) -> DependencyAuthorizationDecision:
    return DependencyAuthorizationDecision(
        decision_id, request.request_id, request.fingerprint,
        DependencyDecision.DENIED, authority_id, reason,
    )


def decision_to_grant(
    request: DependencyExpansionRequest,
    decision: DependencyAuthorizationDecision,
) -> DependencyExpansionGrant:
    """Convert only an exact external approval into the existing grant primitive."""
    if decision.decision != DependencyDecision.APPROVED:
        raise PermissionError("denied dependency request cannot become an expansion grant")
    if decision.request_id != request.request_id or decision.request_fingerprint != request.fingerprint:
        raise PermissionError("dependency approval is not bound to the exact request")
    if not decision.granted_observations:
        raise PermissionError("dependency approval contains no granted observations")
    return DependencyExpansionGrant(
        grant_id=decision.decision_id,
        parent_authority_fingerprint=request.parent_authority_fingerprint,
        added_observations=decision.granted_observations,
        dependency_ids=request.dependency_ids,
        max_dependency_depth=decision.granted_max_depth,
        authority_id=decision.authority_id,
    )
