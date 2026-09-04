"""Fresh-process recovery for durable external execution result receipts."""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Mapping, Optional

from .execution_lifecycle import validate_execution_lifecycle
from .planner import Hypothesis, Observation
from .reasoning_graph import GraphUpdate
from .updater import EvidencePolarity

if TYPE_CHECKING:
    from .reasoning_orchestrator import ReasoningOrchestrator


class _RecoveryBoundResult:
    """Adapter-neutral result view carrying authority from the canonical request."""

    def __init__(self, result, request) -> None:
        self._result = result
        self.execution_id = result.execution_id
        self.request_digest = result.request_digest
        self.outcome = result.outcome
        self.authorization_id = request.authorization_id
        self.scope_status = request.scope_status

    def canonical_payload(self):
        return self._result.canonical_payload()


def rehydrate_external_observation_result(
    orchestrator: "ReasoningOrchestrator",
    adapter_name: str,
    observation: Observation,
    hypotheses: list[Hypothesis],
    evidence_id: str,
    *,
    evidence_polarity: Optional[Mapping[str, EvidencePolarity]] = None,
    causal_chain_id: Optional[str] = None,
    terminal_state: str = "COMPLETED",
) -> GraphUpdate:
    """Recover a durable result after process restart without external re-execution."""
    if not isinstance(adapter_name, str) or not adapter_name.strip():
        raise ValueError("adapter name must not be empty")
    observation_id = f"observation:{observation.name}"
    node = orchestrator.model.nodes.get(observation_id)
    if node is None or node.kind != "observation" or not node.attributes.get("planned"):
        raise ValueError("recovery requires an existing persisted observation plan")
    if node.attributes.get("authorized") is not True or not observation.authorized:
        raise ValueError("unauthorized observations cannot be recovered")

    audit_errors = orchestrator.graph.verify_history_integrity()
    if audit_errors:
        raise RuntimeError(f"persisted audit history is invalid: {audit_errors[0]}")
    lifecycle_errors = validate_execution_lifecycle(orchestrator.model, orchestrator.graph.history)
    if lifecycle_errors:
        raise RuntimeError(f"persisted execution lifecycle is invalid: {lifecycle_errors[0]}")

    execution_id = node.attributes.get("execution_id")
    digest = node.attributes.get("execution_request_digest")
    if not execution_id or not digest:
        raise ValueError("recovery requires persisted execution identity and request digest")
    if observation.execution_id != execution_id:
        raise ValueError("observation execution identity does not match the persisted plan")
    if observation.execution_request_digest != digest:
        raise ValueError("observation request digest does not match the persisted plan")

    request = orchestrator._load_persisted_execution_request(observation_id, digest)
    if request.adapter != adapter_name:
        raise ValueError("recovery adapter does not match the persisted execution request")

    result_node_id = f"execution_result:{digest}"
    result_node = orchestrator.model.nodes.get(result_node_id)
    if result_node is None or result_node.kind != "execution_result":
        raise RuntimeError("durable external result receipt is missing from the canonical graph")
    if result_node.attributes.get("execution_id") != execution_id or result_node.attributes.get("request_digest") != digest:
        raise RuntimeError("durable external result receipt identity does not match the persisted request")
    if result_node.attributes.get("adapter") != adapter_name:
        raise RuntimeError("durable external result receipt adapter does not match the requested recovery adapter")
    payload = result_node.attributes.get("payload")
    if not isinstance(payload, Mapping):
        raise RuntimeError("durable external result receipt payload is malformed")
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if result_node.attributes.get("fingerprint") != fingerprint:
        raise RuntimeError("durable external result receipt fingerprint is invalid")

    result = orchestrator.external_gateway.rehydrate_result(adapter_name, request, payload)
    state = orchestrator._get_gateway_execution_state(request)
    if state == "COMPLETED":
        bound_result = _RecoveryBoundResult(result, request)
        return orchestrator.ingest_observation_result(
            bound_result,
            observation,
            hypotheses,
            evidence_id,
            evidence_polarity=evidence_polarity,
            causal_chain_id=causal_chain_id,
        )
    return orchestrator.reconcile_external_observation_result(
        result,
        observation,
        hypotheses,
        evidence_id,
        evidence_polarity=evidence_polarity,
        causal_chain_id=causal_chain_id,
        terminal_state=terminal_state,
    )
