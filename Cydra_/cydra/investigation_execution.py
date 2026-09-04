"""Execution-time binding between investigation authority and external requests.

Planning authority and external execution are separate planes. This module
creates an opaque, live-controller-bound execution authorization and embeds a
canonical snapshot of that authority into the exact execution request.

The request binding is descriptive and tamper-evident; the live controller is
still authoritative at execution time. A stale lease, changed authority
fingerprint, terminated controller, or rebound execution identity therefore
fails closed before an adapter can run. Persisted authority snapshots are
never executable capabilities; recovery must construct a fresh in-memory
capability from a live externally supplied controller and base authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .execution_request import ExecutionRequest
from .planner import Observation


_AUTHORITY_PARAMETER = "_cydra_investigation_authority"


@dataclass(frozen=True)
class InvestigationExecutionAuthorization:
    """Opaque execution capability bound to one live investigation envelope."""

    controller: object
    investigation_id: str
    authority_fingerprint: str
    lease_generation: int
    execution_id: str
    observation_name: str
    authorization_id: str
    scope_status: str = "AUTHORIZED_EXECUTION"
    authorized: bool = True

    def __post_init__(self) -> None:
        for name in (
            "investigation_id",
            "authority_fingerprint",
            "execution_id",
            "observation_name",
            "authorization_id",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.lease_generation < 0:
            raise ValueError("lease_generation must be non-negative")
        if self.scope_status != "AUTHORIZED_EXECUTION":
            raise ValueError("investigation execution requires AUTHORIZED_EXECUTION scope status")
        if self.authorized is not True:
            raise PermissionError("investigation execution requires explicit authorization")

    def validate_live(self) -> None:
        """Re-check the live controller; the snapshot alone never grants authority."""
        controller = self.controller
        require_active = getattr(controller, "require_active", None)
        if not callable(require_active):
            raise PermissionError("execution authorization is not bound to an investigation controller")
        require_active()
        if getattr(controller, "investigation_id", None) != self.investigation_id:
            raise PermissionError("investigation execution authorization identity mismatch")
        if getattr(controller, "authority_fingerprint", None) != self.authority_fingerprint:
            raise PermissionError("investigation authority changed after execution authorization was issued")
        lease = getattr(controller, "lease", None)
        if lease is None or getattr(lease, "generation", None) != self.lease_generation:
            raise PermissionError("investigation lease generation changed after execution authorization was issued")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "investigation_id": self.investigation_id,
            "authority_fingerprint": self.authority_fingerprint,
            "lease_generation": self.lease_generation,
            "execution_id": self.execution_id,
            "observation_name": self.observation_name,
            "authorization_id": self.authorization_id,
            "scope_status": self.scope_status,
        }


def _token_from_persisted_binding(
    controller,
    binding: Mapping[str, object],
    authorization,
) -> InvestigationExecutionAuthorization:
    """Reconstruct a fresh capability from an untrusted persisted snapshot.

    This does not consume investigation budget: the original authorization
    already consumed it. The live controller and external base authorization
    must independently match the persisted binding, and the returned token is
    a new in-memory capability rather than trusted persisted authority.
    """
    required = (
        "investigation_id",
        "authority_fingerprint",
        "lease_generation",
        "execution_id",
        "observation_name",
        "authorization_id",
        "scope_status",
    )
    if any(key not in binding for key in required):
        raise ValueError("persisted investigation authority binding is incomplete")
    controller.require_active()
    if controller.investigation_id != str(binding["investigation_id"]):
        raise PermissionError("persisted investigation authority belongs to a different investigation")
    if controller.authority_fingerprint != str(binding["authority_fingerprint"]):
        raise PermissionError("persisted investigation authority no longer matches live authority")
    if controller.lease.generation != int(binding["lease_generation"]):
        raise PermissionError("persisted investigation lease generation no longer matches live authority")
    if authorization.authorization_id != str(binding["authorization_id"]):
        raise PermissionError("persisted investigation authorization does not match base authorization")
    if authorization.scope_status != str(binding["scope_status"]):
        raise PermissionError("persisted investigation scope status does not match base authorization")
    token = InvestigationExecutionAuthorization(
        controller=controller,
        investigation_id=str(binding["investigation_id"]),
        authority_fingerprint=str(binding["authority_fingerprint"]),
        lease_generation=int(binding["lease_generation"]),
        execution_id=str(binding["execution_id"]),
        observation_name=str(binding["observation_name"]),
        authorization_id=str(binding["authorization_id"]),
        scope_status=str(binding["scope_status"]),
    )
    token.validate_live()
    return token


def issue_execution_authorization(
    controller,
    observation: Observation,
    authorization,
    *,
    dependency_depth: int = 0,
) -> InvestigationExecutionAuthorization:
    """Consume controller authority for one exact observation and bind it."""
    controller.authorize_observation(observation, dependency_depth=dependency_depth)
    token = InvestigationExecutionAuthorization(
        controller=controller,
        investigation_id=controller.investigation_id,
        authority_fingerprint=controller.authority_fingerprint,
        lease_generation=controller.lease.generation,
        execution_id=observation.execution_id,
        observation_name=observation.name,
        authorization_id=authorization.authorization_id,
        scope_status=authorization.scope_status,
    )
    token.validate_live()
    return token


def reissue_execution_authorization(
    controller,
    request: ExecutionRequest,
    authorization,
) -> InvestigationExecutionAuthorization:
    """Issue a fresh execution capability for a recovered persisted request.

    The persisted request is treated as untrusted data. No controller budget is
    consumed because the original authorization is already represented in the
    controller's usage state. A fresh live controller and base authorization
    are mandatory, and all persisted authority fields must match them exactly.
    """
    if not isinstance(request, ExecutionRequest):
        raise TypeError("execution request is not canonical")
    if not isinstance(authorization, object) or not hasattr(authorization, "authorization_id"):
        raise TypeError("base execution authorization is not canonical")
    payload = request.canonical_payload()
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("execution request parameters are malformed")
    binding = parameters.get(_AUTHORITY_PARAMETER)
    if not isinstance(binding, Mapping):
        raise PermissionError("recovery requires a persisted investigation authority binding")
    if str(binding.get("execution_id")) != request.execution_id:
        raise PermissionError("persisted investigation authority execution identity does not match request")
    if str(binding.get("observation_name")) != binding.get("observation_name"):
        raise ValueError("persisted investigation observation identity is malformed")
    return _token_from_persisted_binding(controller, binding, authorization)


def bind_execution_request(request: ExecutionRequest, authorization: InvestigationExecutionAuthorization) -> ExecutionRequest:
    """Return the exact canonical request bound to an investigation authorization."""
    if not isinstance(request, ExecutionRequest):
        raise TypeError("execution request is not canonical")
    if not isinstance(authorization, InvestigationExecutionAuthorization):
        raise TypeError("investigation execution authorization is not canonical")
    authorization.validate_live()
    if request.execution_id != authorization.execution_id:
        raise ValueError("execution request identity does not match investigation authorization")
    authority = authorization.canonical_payload()
    parameters = dict(request.canonical_payload().get("parameters", {}))
    existing = parameters.get(_AUTHORITY_PARAMETER)
    if existing is not None and dict(existing) != authority:
        raise ValueError("execution request already carries a different investigation authority binding")
    parameters[_AUTHORITY_PARAMETER] = authority
    return ExecutionRequest(
        execution_id=request.execution_id,
        adapter=request.adapter,
        target=request.target,
        command=tuple(request.command),
        project_fingerprint=request.project_fingerprint,
        authorization_id=request.authorization_id,
        scope_status=request.scope_status,
        parameters=parameters,
    )


def validate_execution_binding(request: ExecutionRequest, authorization: InvestigationExecutionAuthorization) -> None:
    """Fail closed unless request, token, and live investigation all agree."""
    if not isinstance(request, ExecutionRequest):
        raise TypeError("execution request is not canonical")
    if not isinstance(authorization, InvestigationExecutionAuthorization):
        raise TypeError("investigation execution authorization is not canonical")
    authorization.validate_live()
    payload = request.canonical_payload()
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("execution request parameters are malformed")
    supplied = parameters.get(_AUTHORITY_PARAMETER)
    if not isinstance(supplied, Mapping):
        raise PermissionError("investigation-bound execution requires an authority binding")
    expected = authorization.canonical_payload()
    if dict(supplied) != expected:
        raise PermissionError("execution request investigation authority binding does not match authorization")
    if request.execution_id != authorization.execution_id:
        raise PermissionError("execution request execution identity does not match investigation authorization")


def request_has_investigation_binding(request: ExecutionRequest) -> bool:
    parameters = request.canonical_payload().get("parameters", {})
    return isinstance(parameters, Mapping) and _AUTHORITY_PARAMETER in parameters


def bind_observation_execution(observation: Observation, authorization: InvestigationExecutionAuthorization) -> Observation:
    """Create an immutable observation carrying the newly bound canonical request."""
    bound = bind_execution_request(observation.execution_request, authorization) if observation.execution_request is not None else None
    if bound is None:
        raise ValueError("investigation-bound observation requires a canonical execution request")
    # Execution binding must not erase reasoning semantics. In particular, the
    # invariant bridge attaches the exact competing hypothesis pair and compiler-
    # backed target IDs to the observation. Those fields remain part of the
    # canonical observation identity after authority binding; otherwise a valid
    # invariant-driven plan could execute successfully while its semantic link to
    # the thing being verified disappeared at the execution boundary.
    return Observation(
        name=observation.name,
        outcomes=list(observation.outcomes),
        cost=observation.cost,
        authorized=observation.authorized,
        execution_id=observation.execution_id,
        execution_request_digest=bound.digest,
        execution_request=bound,
        domain=observation.domain,
        discriminates_hypothesis_ids=observation.discriminates_hypothesis_ids,
        target_ids=observation.target_ids,
        rationale=observation.rationale,
    )
