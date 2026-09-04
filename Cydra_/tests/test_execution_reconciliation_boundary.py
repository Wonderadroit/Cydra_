from dataclasses import dataclass

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionGateway


@dataclass(frozen=True)
class Result:
    execution_id: str
    request_digest: str
    outcome: str

    def canonical_payload(self):
        return {
            "execution_id": self.execution_id,
            "request_digest": self.request_digest,
            "outcome": self.outcome,
        }


def _request():
    return ExecutionRequest(
        execution_id="exec-reconcile",
        adapter="fake",
        target="fixture",
        command=("fake", "check"),
        project_fingerprint="project:fixture",
        authorization_id="auth-001",
    )


def test_gateway_reconciliation_persists_result_before_terminal_state():
    request = _request()
    result = Result(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")
    states = {request.digest: "OUTCOME_UNRECORDED"}
    receipts = {}

    def persist_result(req, value):
        receipts[req.digest] = value.canonical_payload()

    gateway = ExternalExecutionGateway(
        get_execution_state=lambda req: states.get(req.digest),
        set_execution_state=lambda req, state: states.__setitem__(req.digest, state),
        persist_result=persist_result,
    )

    gateway.reconcile_result(request, result)

    assert receipts[request.digest] == result.canonical_payload()
    assert states[request.digest] == "COMPLETED"


def test_gateway_reconciliation_fails_closed_when_receipt_persistence_fails():
    request = _request()
    result = Result(request.execution_id, request.digest, "NO_COUNTEREXAMPLE")
    states = {request.digest: "OUTCOME_UNRECORDED"}

    def persist_result(req, value):
        raise RuntimeError("receipt store unavailable")

    gateway = ExternalExecutionGateway(
        get_execution_state=lambda req: states.get(req.digest),
        set_execution_state=lambda req, state: states.__setitem__(req.digest, state),
        persist_result=persist_result,
    )

    with pytest.raises(RuntimeError, match="could not be durably reconciled"):
        gateway.reconcile_result(request, result)

    assert states[request.digest] == "OUTCOME_UNRECORDED"
