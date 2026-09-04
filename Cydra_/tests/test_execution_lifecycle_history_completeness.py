from cydra.execution_lifecycle import validate_execution_lifecycle
from cydra.execution_request import ExecutionRequest
from cydra.system_model import Node, SystemModel


def test_every_canonical_execution_request_requires_audit_history():
    request = ExecutionRequest(
        execution_id="exec-history-gap",
        adapter="fake",
        target="fixture",
        command=("fake", "check"),
        project_fingerprint="project:fixture",
        authorization_id="auth-001",
    )
    model = SystemModel()
    model.add_node(Node(
        f"execution_request:{request.digest}",
        "execution_request",
        request.digest,
        {**request.canonical_payload(), "digest": request.digest, "execution_state": "COMPLETED"},
    ))

    errors = validate_execution_lifecycle(model, [])

    assert any("no persisted lifecycle history" in error for error in errors)


def test_audited_execution_request_still_validates_normally():
    request = ExecutionRequest(
        execution_id="exec-history-valid",
        adapter="fake",
        target="fixture",
        command=("fake", "check"),
        project_fingerprint="project:fixture",
        authorization_id="auth-001",
    )
    request_id = f"execution_request:{request.digest}"
    model = SystemModel()
    model.add_node(Node(
        request_id,
        "execution_request",
        request.digest,
        {**request.canonical_payload(), "digest": request.digest, "execution_state": "RUNNING"},
    ))
    history = [
        {
            "type": "EXECUTION_REQUEST_PERSISTED",
            "execution_request": request_id,
            "execution_id": request.execution_id,
            "digest": request.digest,
        },
        {
            "type": "EXECUTION_STATE_CHANGED",
            "execution_request": request_id,
            "execution_id": request.execution_id,
            "request_digest": request.digest,
            "previous_state": "PERSISTED",
            "state": "RUNNING",
        },
    ]

    assert validate_execution_lifecycle(model, history) == []
