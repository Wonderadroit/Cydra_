import pytest

from cydra.execution_request import ExecutionRequest
from cydra.external_execution import (
    ExternalExecutionAdapter,
    ExternalExecutionResult,
    require_external_execution_contract,
    validate_result_binding,
)
from cydra.foundry import FoundryResult, FoundryRunner


class FakeResult:
    def __init__(self, execution_id, request_digest, outcome="NO_COUNTEREXAMPLE"):
        self.execution_id = execution_id
        self.request_digest = request_digest
        self.outcome = outcome

    def canonical_payload(self):
        return {
            "execution_id": self.execution_id,
            "request_digest": self.request_digest,
            "outcome": self.outcome,
        }


def test_foundry_runner_satisfies_adapter_contract():
    runner = FoundryRunner("tests/fixtures/foundry")
    adapter = require_external_execution_contract(runner)
    assert isinstance(adapter, ExternalExecutionAdapter)
    assert hasattr(adapter, "build_request")
    assert hasattr(adapter, "execute")
    assert hasattr(adapter, "rehydrate_result")


def test_result_satisfies_minimum_external_result_contract():
    result = FakeResult("execution:1", "execution-request:abc")
    assert isinstance(result, ExternalExecutionResult)


def test_result_binding_requires_exact_request_digest_and_identity():
    request = ExecutionRequest(
        execution_id="execution:1",
        adapter="fake",
        target="authorized-target",
        command=("fake", "check"),
        project_fingerprint="project:test",
        authorization_id="auth:1",
    )
    validate_result_binding(FakeResult("execution:1", request.digest), request)

    with pytest.raises(ValueError, match="execution identity"):
        validate_result_binding(FakeResult("execution:2", request.digest), request)

    with pytest.raises(ValueError, match="request digest"):
        validate_result_binding(FakeResult("execution:1", "execution-request:tampered"), request)


def test_missing_result_digest_fails_closed():
    request = ExecutionRequest(
        execution_id="execution:1",
        adapter="fake",
        target="authorized-target",
        command=("fake", "check"),
        project_fingerprint="project:test",
        authorization_id="auth:1",
    )
    with pytest.raises(ValueError, match="missing the execution request digest"):
        validate_result_binding(FakeResult("execution:1", None), request)


def test_foundry_result_is_minimum_external_result_contract():
    result = FoundryResult(
        command=("forge", "test"), returncode=0, stdout="", stderr="",
        execution_id="execution:1", request_digest="execution-request:abc",
    )
    assert isinstance(result, ExternalExecutionResult)
    assert result.outcome == "NO_COUNTEREXAMPLE"


def test_invalid_adapter_is_rejected():
    with pytest.raises(TypeError, match="does not implement"):
        require_external_execution_contract(object())
