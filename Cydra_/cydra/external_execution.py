"""Adapter-neutral contract and gateway for authorized external execution.

CYDRA plans and reasons; concrete adapters execute outside the reasoning engine.
The gateway owns the shared request/result integrity boundary so adapters cannot
bypass authorization, identity, or exact-request validation. A durable result
receipt is required before an execution becomes terminal, closing the crash
window between external completion and reasoning ingestion.
"""
from __future__ import annotations

from typing import Callable, Mapping, Protocol, runtime_checkable

from .execution_request import ExecutionRequest


EXECUTION_STATES = frozenset({
    "PERSISTED", "RUNNING", "RESULT_RECORDED", "COMPLETED", "FAILED", "OUTCOME_UNRECORDED",
})
_ALLOWED_TRANSITIONS = {
    None: frozenset({"PERSISTED"}),
    "PERSISTED": frozenset({"RUNNING"}),
    "RUNNING": frozenset({"RESULT_RECORDED", "FAILED", "OUTCOME_UNRECORDED"}),
    "RESULT_RECORDED": frozenset({"COMPLETED", "OUTCOME_UNRECORDED"}),
    "COMPLETED": frozenset(),
    "FAILED": frozenset(),
    "OUTCOME_UNRECORDED": frozenset({"COMPLETED", "FAILED"}),
}
_TERMINAL_STATES = frozenset({"COMPLETED", "FAILED"})


@runtime_checkable
class ExternalExecutionResult(Protocol):
    execution_id: str
    request_digest: str | None
    outcome: str

    def canonical_payload(self) -> Mapping[str, object]:
        ...


@runtime_checkable
class ExternalExecutionAdapter(Protocol):
    def build_request(self, *, execution_id: str, authorization, command=None) -> ExecutionRequest:
        ...

    def _bind_gateway_capability(self, capability: object) -> None:
        ...

    def execute(self, *, request: ExecutionRequest, authorization, gateway_capability: object) -> ExternalExecutionResult:
        ...

    def rehydrate_result(self, *, payload: Mapping[str, object], request: ExecutionRequest) -> ExternalExecutionResult:
        ...


def validate_result_binding(result: ExternalExecutionResult, request: ExecutionRequest) -> None:
    """Fail closed unless an external result is structurally valid and request-bound."""
    if not isinstance(result, ExternalExecutionResult):
        raise TypeError("external result does not implement the CYDRA result contract")
    if not isinstance(request, ExecutionRequest):
        raise TypeError("execution request is not a canonical ExecutionRequest")
    if not result.execution_id or result.execution_id != request.execution_id:
        raise ValueError("external result execution identity does not match the execution request")
    if not result.request_digest:
        raise ValueError("external result is missing the execution request digest")
    if result.request_digest != request.digest:
        raise ValueError("external result request digest does not match the execution request")
    if not isinstance(result.outcome, str) or not result.outcome.strip():
        raise ValueError("external result outcome must be a non-empty string")
    payload = result.canonical_payload()
    if not isinstance(payload, Mapping):
        raise TypeError("external result canonical payload must be a mapping")
    if payload.get("execution_id") != result.execution_id or payload.get("request_digest") != result.request_digest:
        raise ValueError("external result canonical payload identity does not match its result identity")
    if payload.get("outcome") != result.outcome:
        raise ValueError("external result canonical payload outcome does not match its result outcome")


def require_external_execution_contract(adapter: object) -> ExternalExecutionAdapter:
    if not isinstance(adapter, ExternalExecutionAdapter):
        raise TypeError("external adapter does not implement the CYDRA execution contract")
    return adapter


class ExternalExecutionGateway:
    """Canonical gateway with durable, fail-closed execution lifecycle semantics."""

    def __init__(self, persist_request: Callable[[ExecutionRequest], object] | None = None, set_execution_state: Callable[[ExecutionRequest, str], object] | None = None, get_execution_state: Callable[[ExecutionRequest], str | None] | None = None, persist_result: Callable[[ExecutionRequest, ExternalExecutionResult], object] | None = None):
        self._adapters: dict[str, ExternalExecutionAdapter] = {}
        self._persist_request = persist_request
        self._set_execution_state = set_execution_state
        self._get_execution_state = get_execution_state
        self._persist_result = persist_result
        self._executed_digests: set[str] = set()
        self._local_states: dict[str, str] = {}
        self._execution_capabilities: dict[str, object] = {}

    def register(self, name: str, adapter: object) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("adapter name must not be empty")
        if name in self._adapters:
            raise ValueError(f"external adapter is already registered: {name}")
        canonical = require_external_execution_contract(adapter)
        capability = object()
        canonical._bind_gateway_capability(capability)
        self._execution_capabilities[name] = capability
        self._adapters[name] = canonical

    def adapter(self, name: str) -> ExternalExecutionAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise KeyError(f"external adapter is not registered: {name}") from exc

    def _current_state(self, request: ExecutionRequest) -> str | None:
        persisted = self._get_execution_state(request) if self._get_execution_state is not None else None
        return persisted if persisted is not None else self._local_states.get(request.digest)

    def _state(self, request: ExecutionRequest, state: str) -> None:
        if state not in EXECUTION_STATES:
            raise ValueError(f"unsupported external execution state: {state}")
        current = self._current_state(request)
        if state not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
            raise RuntimeError(f"invalid external execution lifecycle transition: {current or 'ABSENT'} -> {state}")
        if self._set_execution_state is not None:
            self._set_execution_state(request, state)
        self._local_states[request.digest] = state

    def _mark_failure(self, request: ExecutionRequest) -> None:
        try:
            self._state(request, "FAILED")
        except Exception:
            self._local_states[request.digest] = "FAILED"

    def _mark_outcome_unrecorded(self, request: ExecutionRequest) -> None:
        try:
            self._state(request, "OUTCOME_UNRECORDED")
        except Exception:
            self._local_states[request.digest] = "OUTCOME_UNRECORDED"

    def execute(self, name: str, request: ExecutionRequest, *, authorization, investigation_authorization=None) -> ExternalExecutionResult:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("execution request is not a canonical ExecutionRequest")
        if authorization is None:
            raise PermissionError("external execution requires an explicit authorization context")
        if getattr(authorization, "authorization_id", None) != request.authorization_id:
            raise PermissionError("authorization identity does not match the execution request")
        if getattr(authorization, "scope_status", None) != request.scope_status:
            raise PermissionError("authorization scope does not match the execution request")
        if getattr(authorization, "authorized", False) is not True:
            raise PermissionError("external execution requires explicit authorization")
        if request.adapter != name:
            raise ValueError("execution request adapter does not match the registered adapter")

        from .investigation_execution import InvestigationExecutionAuthorization, request_has_investigation_binding, validate_execution_binding
        if investigation_authorization is None and isinstance(authorization, InvestigationExecutionAuthorization):
            investigation_authorization = authorization
        if request_has_investigation_binding(request):
            if investigation_authorization is None:
                raise PermissionError("investigation-bound execution requires an investigation authorization")
            validate_execution_binding(request, investigation_authorization)
            if getattr(investigation_authorization, "authorization_id", None) != request.authorization_id:
                raise PermissionError("investigation authorization does not match execution authorization")

        if request.digest in self._executed_digests:
            raise RuntimeError("external execution request has already been executed")
        current = self._current_state(request)
        if current in {"RUNNING", "RESULT_RECORDED", "COMPLETED", "FAILED", "OUTCOME_UNRECORDED"}:
            raise RuntimeError(f"external execution request is already terminal or in-flight: {current}")

        adapter = self.adapter(name)
        if self._persist_request is None or self._persist_result is None:
            raise RuntimeError("canonical external execution gateway requires request and result persistence")

        self._persist_request(request)
        current = self._current_state(request)
        if current is None:
            self._state(request, "PERSISTED")
        elif current != "PERSISTED":
            raise RuntimeError("persisted execution request has an invalid lifecycle state")
        self._state(request, "RUNNING")

        try:
            result = adapter.execute(request=request, authorization=authorization, gateway_capability=self._execution_capabilities[name])
        except Exception:
            self._mark_failure(request)
            raise

        try:
            validate_result_binding(result, request)
        except Exception:
            self._mark_outcome_unrecorded(request)
            raise

        try:
            self._persist_result(request, result)
            self._state(request, "RESULT_RECORDED")
        except Exception as result_recording_error:
            self._mark_outcome_unrecorded(request)
            raise RuntimeError("external execution produced a result but durable result recording failed") from result_recording_error

        try:
            self._state(request, "COMPLETED")
        except Exception as completion_error:
            self._mark_outcome_unrecorded(request)
            raise RuntimeError("external execution succeeded but completion state could not be durably recorded") from completion_error
        # A digest becomes a replay barrier only after the terminal state itself
        # is durably recorded. If completion persistence failed, recovery must be
        # able to reconcile the durable receipt instead of being blocked as a
        # same-process replay.
        self._executed_digests.add(request.digest)
        return result

    def rehydrate_result(self, name: str, request: ExecutionRequest, payload: Mapping[str, object]) -> ExternalExecutionResult:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("execution request is not a canonical ExecutionRequest")
        if not isinstance(payload, Mapping):
            raise TypeError("durable execution result receipt must be a mapping")
        adapter = self.adapter(name)
        if request.adapter != name:
            raise ValueError("execution request adapter does not match the registered adapter")
        current = self._current_state(request)
        if current not in {"RESULT_RECORDED", "COMPLETED", "OUTCOME_UNRECORDED"}:
            raise RuntimeError(f"result rehydration requires a recorded external result, found {current or 'ABSENT'}")
        result = adapter.rehydrate_result(payload=payload, request=request)
        validate_result_binding(result, request)
        canonical = result.canonical_payload()
        if dict(canonical) != dict(payload):
            raise ValueError("rehydrated result does not exactly match the durable receipt payload")
        return result

    def reconcile_result(self, request: ExecutionRequest, result: ExternalExecutionResult, *, terminal_state: str = "COMPLETED") -> None:
        if terminal_state not in _TERMINAL_STATES:
            raise ValueError("reconciliation requires terminal_state COMPLETED or FAILED")
        validate_result_binding(result, request)
        current = self._current_state(request)
        if current not in {"OUTCOME_UNRECORDED", "RESULT_RECORDED"}:
            raise RuntimeError(f"execution reconciliation requires OUTCOME_UNRECORDED or RESULT_RECORDED state, found {current or 'ABSENT'}")
        if self._persist_result is None:
            raise RuntimeError("execution reconciliation requires durable result persistence")
        try:
            self._persist_result(request, result)
        except Exception as receipt_error:
            self._mark_outcome_unrecorded(request)
            raise RuntimeError("external execution result could not be durably reconciled") from receipt_error
        self._state(request, terminal_state)
        self._executed_digests.add(request.digest)

    @property
    def registered_adapters(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
