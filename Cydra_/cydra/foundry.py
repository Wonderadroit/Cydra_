"""Authorized external Foundry execution adapter and provenance conversion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
from typing import Mapping, Optional, Sequence

from .evidence import Evidence, EvidenceKind, Provenance
from .execution_request import ExecutionRequest, foundry_request
from .external_execution import ExternalExecutionResult


_INVESTIGATION_BINDING_PARAMETER = "_cydra_investigation_authority"


@dataclass(frozen=True)
class FoundryAuthorization:
    authorization_id: str
    scope_status: str = "AUTHORIZED_EXECUTION"
    authorized: bool = True

    def __post_init__(self) -> None:
        if not self.authorization_id.strip():
            raise ValueError("authorization_id must not be empty")
        if self.scope_status != "AUTHORIZED_EXECUTION":
            raise ValueError("Foundry execution requires AUTHORIZED_EXECUTION scope status")
        if self.authorized is not True:
            raise PermissionError("Foundry execution requires explicit authorization")


@dataclass(frozen=True)
class FoundryResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    project_dir: Optional[str] = None
    project_fingerprint: Optional[str] = None
    forge_version: Optional[str] = None
    authorization_id: Optional[str] = None
    scope_status: Optional[str] = None
    execution_id: Optional[str] = None
    timed_out: bool = False
    request_digest: Optional[str] = None

    @property
    def outcome(self) -> str:
        if self.timed_out:
            return "TIMEOUT"
        return "COUNTEREXAMPLE" if self.returncode != 0 else "NO_COUNTEREXAMPLE"

    @property
    def passed(self) -> bool:
        """Backward-compatible observation status; not proof of security."""
        return self.outcome == "NO_COUNTEREXAMPLE"

    @property
    def counterexample(self) -> bool:
        return self.outcome == "COUNTEREXAMPLE"

    def canonical_payload(self) -> dict[str, object]:
        return {
            "command": list(self.command), "returncode": self.returncode, "stdout": self.stdout,
            "stderr": self.stderr, "project_dir": self.project_dir,
            "project_fingerprint": self.project_fingerprint, "forge_version": self.forge_version,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds, "authorization_id": self.authorization_id,
            "scope_status": self.scope_status, "execution_id": self.execution_id,
            "timed_out": self.timed_out, "request_digest": self.request_digest,
            "outcome": self.outcome,
        }

    @classmethod
    def from_canonical_payload(cls, payload: Mapping[str, object]) -> "FoundryResult":
        if not isinstance(payload, Mapping):
            raise TypeError("Foundry result receipt must be a mapping")
        command = payload.get("command")
        if not isinstance(command, (list, tuple)) or not all(isinstance(item, str) for item in command):
            raise ValueError("Foundry result receipt command is malformed")
        required = ("returncode", "stdout", "stderr", "timed_out", "outcome")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"Foundry result receipt is missing fields: {', '.join(missing)}")
        if not isinstance(payload["returncode"], int) or isinstance(payload["returncode"], bool):
            raise ValueError("Foundry result receipt returncode is malformed")
        for key in ("stdout", "stderr"):
            if not isinstance(payload[key], str):
                raise ValueError(f"Foundry result receipt {key} is malformed")
        if not isinstance(payload["timed_out"], bool):
            raise ValueError("Foundry result receipt timed_out is malformed")
        optional_strings = ("started_at", "finished_at", "project_dir", "project_fingerprint", "forge_version", "authorization_id", "scope_status", "execution_id", "request_digest")
        for key in optional_strings:
            if payload.get(key) is not None and not isinstance(payload[key], str):
                raise ValueError(f"Foundry result receipt {key} is malformed")
        duration = payload.get("duration_seconds")
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float))):
            raise ValueError("Foundry result receipt duration_seconds is malformed")
        result = cls(
            command=tuple(command), returncode=payload["returncode"], stdout=payload["stdout"], stderr=payload["stderr"],
            started_at=payload.get("started_at"), finished_at=payload.get("finished_at"), duration_seconds=duration,
            project_dir=payload.get("project_dir"), project_fingerprint=payload.get("project_fingerprint"),
            forge_version=payload.get("forge_version"), authorization_id=payload.get("authorization_id"),
            scope_status=payload.get("scope_status"), execution_id=payload.get("execution_id"),
            timed_out=payload["timed_out"], request_digest=payload.get("request_digest"),
        )
        if payload["outcome"] != result.outcome:
            raise ValueError("Foundry result receipt outcome is inconsistent with its result fields")
        if dict(result.canonical_payload()) != dict(payload):
            raise ValueError("Foundry result receipt contains unsupported or non-canonical fields")
        return result


class FoundryRunner:
    def __init__(self, project_dir: str):
        self.project_dir = str(Path(project_dir).resolve())
        self._gateway_capability: object | None = None

    def _bind_gateway_capability(self, capability: object) -> None:
        if capability is None:
            raise ValueError("gateway capability must not be None")
        if self._gateway_capability is not None and self._gateway_capability is not capability:
            raise RuntimeError("FoundryRunner is already bound to a different execution gateway")
        self._gateway_capability = capability

    def _require_gateway_capability(self, capability: object | None) -> None:
        if capability is None or capability is not self._gateway_capability:
            raise PermissionError("Foundry execution requires the canonical external execution gateway")

    def project_fingerprint(self) -> str:
        root = Path(self.project_dir)
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in {"out", "cache", ".git", "broadcast"} for part in path.parts):
                continue
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
        return f"foundry-project:{digest.hexdigest()}"

    def forge_version(self) -> Optional[str]:
        try:
            completed = subprocess.run(["forge", "--version"], capture_output=True, text=True, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        output = (completed.stdout or completed.stderr).strip()
        return output or None

    def build_request(self, test_filter: Optional[str] = None, extra_args: Sequence[str] = (), *, authorization: FoundryAuthorization, execution_id: str) -> ExecutionRequest:
        if not execution_id.strip():
            raise ValueError("execution_id must not be empty")
        command = ["forge", "test"]
        if test_filter:
            command += ["--match-test", test_filter]
        command += list(extra_args)
        return foundry_request(execution_id=execution_id, project_dir=self.project_dir, command=command, project_fingerprint=self.project_fingerprint(), authorization_id=authorization.authorization_id, scope_status=authorization.scope_status, test_filter=test_filter, extra_args=extra_args)

    def execute(self, *, request: ExecutionRequest, authorization: FoundryAuthorization, gateway_capability: object) -> FoundryResult:
        self._require_gateway_capability(gateway_capability)
        if request.adapter != "foundry":
            raise ValueError("FoundryRunner cannot execute a non-Foundry request")
        if request.target != self.project_dir:
            raise ValueError("Foundry request target does not match the runner project")
        if request.authorization_id != authorization.authorization_id:
            raise PermissionError("Foundry request authorization identity does not match")
        if request.scope_status != authorization.scope_status:
            raise PermissionError("Foundry request scope does not match authorization")
        parameters = request.canonical_payload()["parameters"]
        if not isinstance(parameters, Mapping):
            raise ValueError("Foundry request parameters are malformed")
        test_filter = parameters.get("test_filter")
        extra_args = tuple(str(arg) for arg in parameters.get("extra_args", ()))
        base_parameters = dict(parameters)
        base_parameters.pop(_INVESTIGATION_BINDING_PARAMETER, None)
        rebuilt = self.build_request(test_filter if test_filter is None or isinstance(test_filter, str) else str(test_filter), extra_args, authorization=authorization, execution_id=request.execution_id)
        if base_parameters != rebuilt.canonical_payload()["parameters"] or rebuilt.command != request.command:
            raise ValueError("Foundry request does not match the runner's canonical execution specification")
        return self._run_canonical_request(request, authorization)

    def run_test(self, test_filter: Optional[str] = None, extra_args: Sequence[str] = (), *, authorization: FoundryAuthorization | None = None, execution_id: str | None = None, _gateway_capability: object | None = None, _request_digest: Optional[str] = None, request_digest: Optional[str] = None) -> FoundryResult:
        if authorization is None or execution_id is None:
            raise PermissionError("Foundry execution requires an explicit authorization context")
        if _request_digest is not None and request_digest is not None and _request_digest != request_digest:
            raise ValueError("Foundry execution request_digest arguments disagree")
        supplied_digest = _request_digest if _request_digest is not None else request_digest
        request = self.build_request(test_filter, extra_args, authorization=authorization, execution_id=execution_id)
        if supplied_digest is not None and request.digest != supplied_digest:
            raise ValueError("Foundry execution request_digest does not match the canonical request")
        self._require_gateway_capability(_gateway_capability)
        return self._run_canonical_request(request, authorization)

    def _run_canonical_request(self, request: ExecutionRequest, authorization: FoundryAuthorization) -> FoundryResult:
        started = datetime.now(timezone.utc)
        try:
            completed = subprocess.run(request.command, cwd=request.target, capture_output=True, text=True, check=False, timeout=300)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            completed = exc
            timed_out = True
        finished = datetime.now(timezone.utc)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = 124 if timed_out else int(completed.returncode)
        return FoundryResult(command=request.command, returncode=returncode, stdout=stdout, stderr=stderr, started_at=started.isoformat(), finished_at=finished.isoformat(), duration_seconds=(finished - started).total_seconds(), project_dir=self.project_dir, project_fingerprint=self.project_fingerprint(), forge_version=self.forge_version(), authorization_id=authorization.authorization_id, scope_status=authorization.scope_status, execution_id=request.execution_id, timed_out=timed_out, request_digest=request.digest)

    def rehydrate_result(self, *, payload: Mapping[str, object], request: ExecutionRequest) -> FoundryResult:
        result = FoundryResult.from_canonical_payload(payload)
        if result.execution_id != request.execution_id or result.request_digest != request.digest:
            raise ValueError("Foundry durable result receipt is not bound to the canonical request")
        return result


def result_to_evidence(result: ExternalExecutionResult, evidence_id: str, *, authorization_id: str | None = None, scope_status: str | None = None) -> Evidence:
    """Convert a validated execution result into provenance-bound reasoning evidence."""
    if not isinstance(result, ExternalExecutionResult):
        raise TypeError("result must implement the CYDRA external execution result contract")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise ValueError("evidence_id must not be empty")
    if not result.execution_id:
        raise PermissionError("external result evidence requires an execution identity")
    resolved_authorization_id = getattr(result, "authorization_id", None) or authorization_id
    resolved_scope_status = getattr(result, "scope_status", None) or scope_status
    if not resolved_authorization_id:
        raise PermissionError("external result evidence requires an authorization identity")
    if resolved_scope_status != "AUTHORIZED_EXECUTION":
        raise PermissionError("external result evidence requires authorized execution scope")
    acquired_at = getattr(result, "finished_at", None) or getattr(result, "started_at", None)
    if acquired_at:
        try:
            timestamp = datetime.fromisoformat(acquired_at)
        except ValueError as exc:
            raise ValueError("execution result evidence timestamp is malformed") from exc
    else:
        timestamp = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("execution result evidence timestamp must be timezone-aware")
    return Evidence(evidence_id=evidence_id, kind=EvidenceKind.TEST_RESULT, value=dict(result.canonical_payload()), provenance=Provenance(source=f"execution:{result.execution_id}", acquired_at=timestamp, collector="external_execution", scope_status=resolved_scope_status, details={"authorization_id": resolved_authorization_id, "execution_id": result.execution_id, "request_digest": result.request_digest or "", "project_fingerprint": getattr(result, "project_fingerprint", None) or ""}), interpretation=f"External execution outcome: {result.outcome}", confidence=1.0)