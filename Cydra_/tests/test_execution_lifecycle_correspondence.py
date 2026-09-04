import hashlib
import json

from cydra.execution_lifecycle import validate_execution_lifecycle
from cydra.execution_request import ExecutionRequest
from cydra.system_model import Node, SystemModel


def _request():
    return ExecutionRequest(
        execution_id="lifecycle-exec-001",
        adapter="foundry",
        target="/fixture",
        command=("forge", "test"),
        project_fingerprint="project:fixture",
        authorization_id="auth-001",
        scope_status="AUTHORIZED_EXECUTION",
    )


def _receipt(request):
    payload = {
        "execution_id": request.execution_id,
        "request_digest": request.digest,
        "outcome": "NO_COUNTEREXAMPLE",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return Node(
        f"execution_result:{request.digest}",
        "execution_result",
        request.digest,
        {
            "execution_id": request.execution_id,
            "request_digest": request.digest,
            "adapter": request.adapter,
            "payload": payload,
            "fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
        },
    )


def _model(request, state="COMPLETED", include_receipt=True):
    model = SystemModel()
    request_id = f"execution_request:{request.digest}"
    model.add_node(Node(request_id, "execution_request", request.digest, {
        **request.canonical_payload(), "digest": request.digest, "execution_state": state,
    }))
    if include_receipt:
        model.add_node(_receipt(request))
    return model, request_id


def _history(request, request_id, terminal="COMPLETED", include_result=True):
    events = [
        {"type": "EXECUTION_REQUEST_PERSISTED", "execution_request": request_id, "execution_id": request.execution_id},
        {"type": "EXECUTION_STATE_CHANGED", "execution_request": request_id, "execution_id": request.execution_id, "previous_state": "PERSISTED", "state": "RUNNING"},
    ]
    if include_result:
        events.append({
            "type": "EXECUTION_RESULT_RECORDED", "execution_request": request_id,
            "execution_result": f"execution_result:{request.digest}",
            "execution_id": request.execution_id, "request_digest": request.digest,
        })
        events.append({
            "type": "EXECUTION_STATE_CHANGED", "execution_request": request_id,
            "execution_id": request.execution_id, "previous_state": "RUNNING",
            "state": "RESULT_RECORDED", "request_digest": request.digest,
        })
    events.append({
        "type": "EXECUTION_STATE_CHANGED", "execution_request": request_id,
        "execution_id": request.execution_id,
        "previous_state": "RESULT_RECORDED" if include_result else "RUNNING",
        "state": terminal, "request_digest": request.digest,
    })
    if terminal == "COMPLETED":
        events.append({
            "type": "EXTERNAL_EXECUTION_COMPLETED", "execution_request": request_id,
            "execution_id": request.execution_id,
        })
    return events


def test_valid_completed_lifecycle_corresponds_to_canonical_state():
    request = _request()
    model, request_id = _model(request)
    assert validate_execution_lifecycle(model, _history(request, request_id)) == []


def test_valid_failed_lifecycle_corresponds_to_canonical_state():
    request = _request()
    model, request_id = _model(request, state="FAILED", include_receipt=False)
    assert validate_execution_lifecycle(model, _history(request, request_id, terminal="FAILED", include_result=False)) == []


def test_reordered_state_transition_is_rejected():
    request = _request()
    model, request_id = _model(request)
    history = _history(request, request_id)
    history[2], history[3] = history[3], history[2]
    errors = validate_execution_lifecycle(model, history)
    assert any(
        "result state recorded before durable receipt" in error
        or "result recorded outside RUNNING" in error
        or "execution result recorded outside RUNNING" in error
        for error in errors
    ), errors


def test_result_event_after_result_state_is_required():
    request = _request()
    model, request_id = _model(request)
    history = _history(request, request_id)
    result_event = history.pop(2)
    history.insert(4, result_event)
    errors = validate_execution_lifecycle(model, history)
    assert any("result state recorded before durable receipt" in error or "outside RUNNING" in error for error in errors)


def test_completed_state_without_result_receipt_event_is_rejected():
    request = _request()
    model, request_id = _model(request)
    history = _history(request, request_id, include_result=False)
    errors = validate_execution_lifecycle(model, history)
    assert any("completed without durable result receipt" in error for error in errors)


def test_canonical_state_substitution_is_rejected():
    request = _request()
    model, request_id = _model(request)
    model.nodes[request_id] = Node(
        request_id, "execution_request", request.digest,
        {**request.canonical_payload(), "digest": request.digest, "execution_state": "RUNNING"},
    )
    errors = validate_execution_lifecycle(model, _history(request, request_id))
    assert any("canonical execution state disagrees" in error for error in errors)


def test_result_receipt_substitution_is_rejected():
    request = _request()
    model, request_id = _model(request)
    receipt_id = f"execution_result:{request.digest}"
    model.nodes[receipt_id] = Node(receipt_id, "execution_result", request.digest, {
        "execution_id": "different-execution",
        "request_digest": request.digest,
        "adapter": request.adapter,
        "payload": {},
        "fingerprint": "tampered",
    })
    errors = validate_execution_lifecycle(model, _history(request, request_id))
    assert any("receipt does not match request" in error for error in errors)


def test_result_event_fingerprint_must_match_receipt_when_present():
    request = _request()
    model, request_id = _model(request)
    history = _history(request, request_id)
    history[2]["fingerprint"] = "tampered"
    errors = validate_execution_lifecycle(model, history)
    assert any("event fingerprint does not match receipt" in error for error in errors)
