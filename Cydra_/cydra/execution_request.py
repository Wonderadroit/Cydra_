"""Canonical external-execution request identity and digesting."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Optional, Sequence


_MAPPING_TAG = "__cydra_mapping__"
_SEQUENCE_TAG = "__cydra_sequence__"


def _freeze(value):
    """Recursively freeze JSON-compatible request parameters without ambiguity."""
    if isinstance(value, Mapping):
        items = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("execution request mapping keys must be strings")
            items.append((key, _freeze(item)))
        return (_MAPPING_TAG, tuple(sorted(items)))
    if isinstance(value, (list, tuple)):
        return (_SEQUENCE_TAG, tuple(_freeze(item) for item in value))
    if isinstance(value, float) and not math.isfinite(value):
        raise TypeError("execution request parameters must contain only finite numbers")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"execution request parameters must be JSON-compatible, got {type(value).__name__}")


def _thaw(value):
    if isinstance(value, tuple) and len(value) == 2 and value[0] == _MAPPING_TAG:
        return {key: _thaw(item) for key, item in value[1]}
    if isinstance(value, tuple) and len(value) == 2 and value[0] == _SEQUENCE_TAG:
        return [_thaw(item) for item in value[1]]
    return value


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable specification that an external execution result must match."""

    execution_id: str
    adapter: str
    target: str
    command: tuple[str, ...]
    project_fingerprint: Optional[str]
    authorization_id: str
    scope_status: str = "AUTHORIZED_EXECUTION"
    parameters: Mapping[str, object] = None

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id must not be empty")
        if not self.adapter.strip():
            raise ValueError("adapter must not be empty")
        if not self.target.strip():
            raise ValueError("target must not be empty")
        if not self.command:
            raise ValueError("command must not be empty")
        if not self.authorization_id.strip():
            raise ValueError("authorization_id must not be empty")
        if self.scope_status != "AUTHORIZED_EXECUTION":
            raise ValueError("execution request requires AUTHORIZED_EXECUTION scope status")
        if self.parameters is None:
            object.__setattr__(self, "parameters", {})
        frozen = _freeze(self.parameters)
        object.__setattr__(self, "parameters", frozen)

    def canonical_payload(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "adapter": self.adapter,
            "target": self.target,
            "command": list(self.command),
            "project_fingerprint": self.project_fingerprint,
            "authorization_id": self.authorization_id,
            "scope_status": self.scope_status,
            "parameters": _thaw(self.parameters),
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        return f"execution-request:{sha256(encoded).hexdigest()}"

    @classmethod
    def from_canonical_payload(cls, payload: Mapping[str, object], expected_digest: Optional[str] = None) -> "ExecutionRequest":
        """Reconstruct a persisted request and optionally fail closed on digest tampering."""
        request = cls(
            execution_id=str(payload["execution_id"]),
            adapter=str(payload["adapter"]),
            target=str(payload["target"]),
            command=tuple(str(item) for item in payload["command"]),
            project_fingerprint=payload.get("project_fingerprint"),
            authorization_id=str(payload["authorization_id"]),
            scope_status=str(payload.get("scope_status", "AUTHORIZED_EXECUTION")),
            parameters=dict(payload.get("parameters", {})),
        )
        if expected_digest is not None and request.digest != expected_digest:
            raise ValueError("persisted execution request digest does not match canonical request")
        return request


def foundry_request(
    *,
    execution_id: str,
    project_dir: str,
    command: Sequence[str],
    project_fingerprint: Optional[str],
    authorization_id: str,
    scope_status: str = "AUTHORIZED_EXECUTION",
    test_filter: Optional[str] = None,
    extra_args: Sequence[str] = (),
) -> ExecutionRequest:
    """Build the canonical request identity for a Foundry execution."""
    return ExecutionRequest(
        execution_id=execution_id,
        adapter="foundry",
        target=project_dir,
        command=tuple(command),
        project_fingerprint=project_fingerprint,
        authorization_id=authorization_id,
        scope_status=scope_status,
        parameters={"test_filter": test_filter, "extra_args": list(extra_args)},
    )
