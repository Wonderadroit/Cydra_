"""Trusted recovery boundary for authority-bound investigation executions.

Persisted investigation authority is evidence, not authority. Recovery accepts
only a live controller plus a fresh base execution authorization and derives a
new in-memory execution capability after validating the persisted request
binding against that live authority.
"""
from __future__ import annotations

from typing import Mapping

from .investigation_execution import reissue_execution_authorization
from .planner import Observation
from .reasoning_orchestrator import AuthorizedInvestigationPlan, ReasoningOrchestrator


_INVESTIGATION_BINDING_PARAMETER = "_cydra_investigation_authority"


def _validate_recovered_controller_state(controller) -> None:
    """Reject mutable usage-state tampering not covered by the authority fingerprint."""
    integer_fields = (
        "rounds_used",
        "observations_used",
        "planning_steps_used",
        "hypotheses_seen",
        "dependency_depth",
    )
    for field in integer_fields:
        value = getattr(controller, field, None)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"recovered investigation {field} is invalid")
    execution_cost = getattr(controller, "execution_cost_used", None)
    if isinstance(execution_cost, bool) or not isinstance(execution_cost, (int, float)) or execution_cost < 0:
        raise ValueError("recovered investigation execution_cost_used is invalid")
    observed_ids = getattr(controller, "observed_execution_ids", None)
    if not isinstance(observed_ids, set) or any(not isinstance(value, str) or not value.strip() for value in observed_ids):
        raise ValueError("recovered investigation observed execution identities are invalid")
    if len(observed_ids) != controller.observations_used:
        raise ValueError("recovered investigation observation usage does not match observed execution identities")
    if controller.observations_used > controller.budget.max_observations:
        raise ValueError("recovered investigation observations exceed the persisted budget")
    if controller.rounds_used > controller.budget.max_rounds:
        raise ValueError("recovered investigation rounds exceed the persisted budget")
    if controller.planning_steps_used > controller.budget.max_planning_steps:
        raise ValueError("recovered investigation planning steps exceed the persisted budget")
    if controller.hypotheses_seen > controller.budget.max_hypotheses:
        raise ValueError("recovered investigation hypotheses exceed the persisted budget")
    if controller.execution_cost_used > controller.budget.max_execution_cost:
        raise ValueError("recovered investigation execution cost exceeds the persisted budget")
    if controller.dependency_depth > controller.budget.max_dependency_depth:
        raise ValueError("recovered investigation dependency depth exceeds the persisted budget")


def recover_investigation_plan(
    orchestrator: ReasoningOrchestrator,
    controller,
    observation_id: str,
    *,
    authorization,
) -> AuthorizedInvestigationPlan:
    """Recover a persisted investigation plan without trusting persisted authority.

    No budget is consumed and no external adapter is called. The persisted
    execution request is treated as untrusted input; its authority snapshot
    must match the live controller and fresh base authorization. The returned
    capability is newly constructed in memory and must still pass live checks
    at execution time.
    """
    if not isinstance(orchestrator, ReasoningOrchestrator):
        raise TypeError("orchestrator is not canonical")
    _validate_recovered_controller_state(controller)
    node = orchestrator.model.nodes.get(observation_id)
    if node is None or node.kind != "observation" or node.attributes.get("planned") is not True:
        raise ValueError("recovery requires an existing persisted investigation plan")
    if node.attributes.get("authorized") is not True:
        raise PermissionError("recovery cannot authorize an unauthorized observation")
    execution_id = node.attributes.get("execution_id")
    digest = node.attributes.get("execution_request_digest")
    if not execution_id or not digest:
        raise ValueError("persisted investigation plan has no canonical execution identity")

    request = orchestrator._load_persisted_execution_request(observation_id, digest)
    parameters = request.canonical_payload().get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("persisted execution request parameters are malformed")
    binding = parameters.get(_INVESTIGATION_BINDING_PARAMETER)
    if not isinstance(binding, Mapping):
        raise PermissionError("recovery requires a persisted investigation authority binding")
    if str(binding.get("observation_name")) != node.label:
        raise PermissionError("persisted investigation observation identity does not match the persisted plan")
    if str(binding.get("execution_id")) != str(execution_id):
        raise PermissionError("persisted investigation execution identity does not match the persisted plan")

    capability = reissue_execution_authorization(controller, request, authorization)
    if capability.execution_id != execution_id:
        raise PermissionError("recovered capability execution identity does not match persisted plan")
    if capability.observation_name != node.label:
        raise PermissionError("recovered capability observation identity does not match persisted plan")

    observation = Observation(
        name=node.label,
        outcomes=list(node.attributes.get("outcomes", [])),
        cost=float(node.attributes.get("cost", 0.0)),
        authorized=bool(node.attributes.get("authorized")),
        execution_id=str(execution_id),
        execution_request_digest=request.digest,
        execution_request=request,
        domain=node.attributes.get("domain", "target"),
    )
    if observation.execution_request_digest != digest:
        raise ValueError("recovered observation request digest does not match persisted plan")
    return AuthorizedInvestigationPlan(
        observation_id=observation_id,
        observation=observation,
        authorization=capability,
    )
