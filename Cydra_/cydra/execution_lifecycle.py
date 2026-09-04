"""Validation of durable external-execution lifecycle history.

The execution gateway owns transition enforcement at runtime. This module is the
independent audit-side validator: it reconstructs lifecycle transitions from
persisted reasoning events and compares the reconstructed terminal state with
the canonical execution-request node.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping

_ALLOWED = {
    None: {"PERSISTED"},
    "PERSISTED": {"RUNNING"},
    "RUNNING": {"RESULT_RECORDED", "FAILED", "OUTCOME_UNRECORDED"},
    "RESULT_RECORDED": {"COMPLETED", "OUTCOME_UNRECORDED"},
    "OUTCOME_UNRECORDED": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}
_TERMINAL = {"COMPLETED", "FAILED"}


def validate_execution_lifecycle(model, history) -> list[str]:
    """Return lifecycle correspondence errors without mutating the model/history."""
    errors: list[str] = []
    by_request: dict[str, list[Mapping[str, object]]] = defaultdict(list)

    for index, event in enumerate(history):
        if not isinstance(event, Mapping):
            continue
        event_type = event.get("type")
        request_id = event.get("execution_request")
        if event_type in {
            "EXECUTION_REQUEST_PERSISTED",
            "EXECUTION_STATE_CHANGED",
            "EXECUTION_RESULT_RECORDED",
            "EXTERNAL_EXECUTION_COMPLETED",
        }:
            if not isinstance(request_id, str):
                errors.append(f"execution lifecycle event {index} is missing execution_request")
                continue
            by_request[request_id].append(event)

    canonical_requests = {
        node_id
        for node_id, node in model.nodes.items()
        if getattr(node, "kind", None) == "execution_request"
    }

    # A canonical request with no audit lifecycle is not an auditable execution.
    # This is especially important during fresh-process recovery: trusting only
    # the persisted execution_state would allow a state-only receipt to bypass
    # the audit correspondence boundary.
    for request_id in sorted(canonical_requests - set(by_request)):
        errors.append(f"execution request has no persisted lifecycle history: {request_id}")

    for request_id, events in by_request.items():
        request = model.nodes.get(request_id)
        if request is None or request.kind != "execution_request":
            errors.append(f"execution lifecycle references missing execution request: {request_id}")
            continue

        expected_state = None
        execution_id = request.attributes.get("execution_id")
        digest = request.attributes.get("digest")
        saw_result = False
        saw_terminal = False

        for event in events:
            event_type = event.get("type")
            if event.get("execution_id") != execution_id:
                errors.append(f"execution lifecycle execution identity mismatch: {request_id}")
            if event_type in {"EXECUTION_STATE_CHANGED", "EXECUTION_RESULT_RECORDED"} and event.get("request_digest") not in {None, digest}:
                errors.append(f"execution lifecycle request digest mismatch: {request_id}")

            if event_type == "EXECUTION_REQUEST_PERSISTED":
                if event.get("digest") not in {None, digest}:
                    errors.append(f"execution request persistence digest mismatch: {request_id}")
                if expected_state not in {None, "PERSISTED"}:
                    errors.append(f"execution request persisted after lifecycle advanced: {request_id}")
                expected_state = "PERSISTED"
                continue

            if event_type == "EXECUTION_RESULT_RECORDED":
                if expected_state != "RUNNING":
                    errors.append(f"execution result recorded outside RUNNING state: {request_id}")
                if saw_result:
                    errors.append(f"duplicate execution result receipt event: {request_id}")
                result_id = event.get("execution_result")
                result = model.nodes.get(result_id) if isinstance(result_id, str) else None
                if result is None or result.kind != "execution_result":
                    errors.append(f"execution result event references missing receipt: {request_id}")
                else:
                    if result.attributes.get("execution_id") != execution_id or result.attributes.get("request_digest") != digest:
                        errors.append(f"execution result receipt does not match request: {request_id}")
                    if event.get("fingerprint") not in {None, result.attributes.get("fingerprint")}:
                        errors.append(f"execution result event fingerprint does not match receipt: {request_id}")
                saw_result = True
                continue

            if event_type == "EXECUTION_STATE_CHANGED":
                previous = event.get("previous_state")
                state = event.get("state")
                if previous != expected_state:
                    errors.append(f"execution lifecycle previous state mismatch: {request_id}")
                if state not in _ALLOWED.get(expected_state, set()):
                    errors.append(f"illegal execution lifecycle transition for {request_id}: {expected_state or 'ABSENT'} -> {state}")
                if state == "RESULT_RECORDED" and not saw_result:
                    errors.append(f"execution result state recorded before durable receipt event: {request_id}")
                if state == "COMPLETED" and not saw_result:
                    errors.append(f"execution completed without durable result receipt: {request_id}")
                if expected_state in _TERMINAL:
                    errors.append(f"execution lifecycle advanced after terminal state: {request_id}")
                expected_state = state
                if state in _TERMINAL:
                    saw_terminal = True
                continue

            if event_type == "EXTERNAL_EXECUTION_COMPLETED":
                if expected_state != "COMPLETED":
                    errors.append(f"external completion event does not follow COMPLETED state: {request_id}")
                if not saw_result:
                    errors.append(f"external completion event has no result receipt: {request_id}")
                if saw_terminal is not True or expected_state != "COMPLETED":
                    errors.append(f"external completion event is not terminally anchored: {request_id}")
                continue

        canonical_state = request.attributes.get("execution_state")
        if canonical_state != expected_state:
            errors.append(
                f"canonical execution state disagrees with audit lifecycle for {request_id}: "
                f"canonical={canonical_state!r}, reconstructed={expected_state!r}"
            )

    return errors
