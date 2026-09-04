from dataclasses import dataclass

import pytest

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import ExternalExecutionGateway
from cydra.foundry import FoundryAuthorization


@dataclass(frozen=True)
class Result:
    execution_id: str
    request_digest: str
    outcome: str = "NO_COUNTEREXAMPLE"

    def canonical_payload(self):
        return {"execution_id": self.execution_id, "request_digest": self.request_digest, "outcome": self.outcome}


class Adapter:
    def __init__(self):
        self.calls = 0
        self.gateway_capability = None

    def _bind_gateway_capability(self, capability):
        self.gateway_capability = capability

    def build_request(self, *, execution_id, authorization, command=None):
        return _request()

    def execute(self, *, request, authorization, gateway_capability):
        if gateway_capability is not self.gateway_capability:
            raise PermissionError("invalid gateway capability")
        self.calls += 1
        return Result(request.execution_id, request.digest)

    def rehydrate_result(self, *, payload, request):
        return Result(payload["execution_id"], payload["request_digest"], payload["outcome"])


def _request():
    return ExecutionRequest(
        execution_id="receipt-execution",
        adapter="fake",
        target="fixture",
        command=("fake", "check"),
        project_fingerprint="project:fixture",
        authorization_id="receipt-auth",
    )


def test_result_recording_failure_is_not_misclassified_as_execution_failure():
    request = _request()
    states = {}
    adapter = Adapter()

    def persist_result(request_obj, result):
        raise RuntimeError("receipt store unavailable")

    gateway = ExternalExecutionGateway(
        lambda req: None,
        lambda req, state: states.__setitem__(req.digest, state),
        lambda req: states.get(req.digest),
        persist_result,
    )
    gateway.register("fake", adapter)

    with pytest.raises(RuntimeError, match="durable result recording failed"):
        gateway.execute("fake", request, authorization=FoundryAuthorization("receipt-auth"))

    assert adapter.calls == 1
    assert states[request.digest] == "OUTCOME_UNRECORDED"
    with pytest.raises(RuntimeError, match="OUTCOME_UNRECORDED"):
        gateway.execute("fake", request, authorization=FoundryAuthorization("receipt-auth"))


def test_result_receipt_is_request_bound_before_terminal_state():
    request = _request()
    states = {}
    receipts = {}
    gateway = ExternalExecutionGateway(
        lambda req: None,
        lambda req, state: states.__setitem__(req.digest, state),
        lambda req: states.get(req.digest),
        lambda req, result: receipts.__setitem__(req.digest, result.canonical_payload()),
    )
    gateway.register("fake", Adapter())

    result = gateway.execute("fake", request, authorization=FoundryAuthorization("receipt-auth"))

    assert states[request.digest] == "COMPLETED"
    assert receipts[request.digest]["execution_id"] == request.execution_id
    assert receipts[request.digest]["request_digest"] == request.digest
    assert result.request_digest == request.digest
