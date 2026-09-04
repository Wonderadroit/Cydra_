"""Bounded oracle-free replay adapter for historical reasoning backtests.

The replay adapter is deliberately separate from CYDRA's reasoning engine. A
benchmark supplies an explicit verifier for one selected observation; the adapter
only turns that verifier result into the canonical external-execution contract so
CYDRA can ingest it through the same request, receipt, provenance, and hypothesis
update boundaries used by live execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .execution_request import ExecutionRequest
from .planner import Observation
from .updater import EvidencePolarity


@dataclass(frozen=True)
class ReplayAuthorization:
    """Explicit authorization envelope for one local historical replay."""

    authorization_id: str
    scope_status: str = "AUTHORIZED_EXECUTION"
    authorized: bool = True

    def __post_init__(self) -> None:
        if not self.authorization_id.strip():
            raise ValueError("authorization_id must not be empty")
        if self.scope_status != "AUTHORIZED_EXECUTION":
            raise ValueError("historical replay requires AUTHORIZED_EXECUTION scope status")
        if self.authorized is not True:
            raise PermissionError("historical replay requires explicit authorization")


@dataclass(frozen=True)
class ReplayObservationResult:
    """Verifier output with caller-declared evidentiary polarity."""

    outcome: str
    evidence_polarity: Mapping[str, EvidencePolarity]
    details: Mapping[str, object] = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, str) or not self.outcome.strip():
            raise ValueError("replay outcome must be a non-empty string")
        for hypothesis_id, polarity in self.evidence_polarity.items():
            if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
                raise ValueError("replay evidence polarity requires non-empty hypothesis IDs")
            if not isinstance(polarity, EvidencePolarity):
                raise ValueError("replay evidence polarity values must be EvidencePolarity")
        if self.details is not None and not isinstance(self.details, Mapping):
            raise TypeError("replay details must be a mapping")


ReplayVerifier = Callable[[Observation, Path], ReplayObservationResult]


@dataclass(frozen=True)
class BenchmarkReplayResult:
    execution_id: str
    request_digest: str
    outcome: str
    evidence_polarity: Mapping[str, EvidencePolarity]
    verifier_details: Mapping[str, object]
    receipt_digest: str

    def __post_init__(self) -> None:
        if not self.execution_id.strip() or not self.request_digest.strip():
            raise ValueError("replay result requires execution identity and request digest")
        if not self.outcome.strip():
            raise ValueError("replay result outcome must not be empty")
        if not self.receipt_digest.strip():
            raise ValueError("replay result requires a receipt digest")
        for hypothesis_id, polarity in self.evidence_polarity.items():
            if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
                raise ValueError("replay result evidence polarity requires hypothesis IDs")
            if not isinstance(polarity, EvidencePolarity):
                raise ValueError("replay result evidence polarity values must be EvidencePolarity")

    def _payload_without_receipt_digest(self) -> Mapping[str, object]:
        return {
            "execution_id": self.execution_id,
            "request_digest": self.request_digest,
            "outcome": self.outcome,
            "evidence_polarity": {key: value.value for key, value in sorted(self.evidence_polarity.items())},
            "verifier_details": dict(self.verifier_details),
        }

    def canonical_payload(self) -> Mapping[str, object]:
        return {
            **self._payload_without_receipt_digest(),
            "receipt_digest": self.receipt_digest,
        }

    @staticmethod
    def compute_receipt_digest(payload: Mapping[str, object]) -> str:
        encoded = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def polarity(self) -> dict[str, EvidencePolarity]:
        return dict(self.evidence_polarity)


class BenchmarkReplayAdapter:
    """Adapt an explicitly supplied historical verifier to the execution gateway."""

    def __init__(self, root: str | Path, verifier: ReplayVerifier):
        self.root = Path(root).resolve()
        if not callable(verifier):
            raise TypeError("historical replay requires an explicit verifier")
        self.verifier = verifier
        self._gateway_capability: object | None = None

    def _bind_gateway_capability(self, capability: object) -> None:
        if capability is None:
            raise ValueError("gateway capability must not be None")
        if self._gateway_capability is not None and self._gateway_capability is not capability:
            raise RuntimeError("replay adapter is already bound to a different execution gateway")
        self._gateway_capability = capability

    def _require_gateway_capability(self, capability: object) -> None:
        if capability is None or capability is not self._gateway_capability:
            raise PermissionError("historical replay requires the canonical external execution gateway")

    def build_request(
        self,
        *,
        observation: Observation,
        authorization: ReplayAuthorization,
        command: Sequence[str] | None = None,
    ) -> ExecutionRequest:
        if not observation.name.strip():
            raise ValueError("replay observation name must not be empty")
        command_tuple = tuple(command or ("cydra-replay", observation.name))
        if len(command_tuple) != 2 or command_tuple[0] != "cydra-replay" or not command_tuple[1].strip():
            raise ValueError("replay request command must identify exactly one observation")
        if command_tuple[1] != observation.name:
            raise ValueError("replay request command does not match the planned observation")
        return ExecutionRequest(
            execution_id=observation.execution_id,
            adapter="benchmark_replay",
            target=str(self.root),
            command=command_tuple,
            project_fingerprint=None,
            authorization_id=authorization.authorization_id,
            scope_status=authorization.scope_status,
            parameters={
                "observation_name": observation.name,
                "observation_outcomes": list(observation.outcomes),
                "observation_cost": observation.cost,
                "observation_authorized": observation.authorized,
                "observation_domain": observation.domain,
                "discriminates_hypothesis_ids": list(observation.discriminates_hypothesis_ids),
            },
        )

    def execute(
        self,
        *,
        request: ExecutionRequest,
        authorization: ReplayAuthorization,
        gateway_capability: object,
    ) -> BenchmarkReplayResult:
        self._require_gateway_capability(gateway_capability)
        if request.adapter != "benchmark_replay":
            raise ValueError("replay adapter cannot execute a non-replay request")
        if request.target != str(self.root):
            raise ValueError("replay request target does not match the materialized benchmark root")
        if request.authorization_id != authorization.authorization_id or request.scope_status != authorization.scope_status:
            raise PermissionError("replay request authorization does not match")
        parameters = request.canonical_payload()["parameters"]
        if not isinstance(parameters, Mapping):
            raise ValueError("replay request parameters are malformed")
        observation_name = parameters.get("observation_name")
        outcomes = parameters.get("observation_outcomes")
        cost = parameters.get("observation_cost")
        authorized = parameters.get("observation_authorized")
        domain = parameters.get("observation_domain")
        discriminates = parameters.get("discriminates_hypothesis_ids")
        if (
            not isinstance(observation_name, str)
            or not observation_name.strip()
            or not isinstance(outcomes, list)
            or not all(isinstance(item, str) for item in outcomes)
            or not isinstance(cost, (int, float))
            or isinstance(cost, bool)
            or not isinstance(authorized, bool)
            or not isinstance(domain, str)
            or not isinstance(discriminates, list)
            or not all(isinstance(item, str) for item in discriminates)
        ):
            raise ValueError("replay request observation semantics are malformed")
        command = request.command
        if len(command) != 2 or command[0] != "cydra-replay" or command[1] != observation_name:
            raise ValueError("replay request command does not match its observation identity")
        observation = Observation(
            observation_name,
            outcomes,
            float(cost),
            authorized=authorized,
            execution_id=request.execution_id,
            domain=domain,
            discriminates_hypothesis_ids=tuple(discriminates),
        )
        result = self.verifier(observation, self.root)
        if not isinstance(result, ReplayObservationResult):
            raise TypeError("historical replay verifier must return ReplayObservationResult")
        payload = {
            "execution_id": request.execution_id,
            "request_digest": request.digest,
            "outcome": result.outcome,
            "evidence_polarity": {key: value.value for key, value in sorted(result.evidence_polarity.items())},
            "verifier_details": {"observation_name": observation.name, **dict(result.details or {})},
        }
        receipt_digest = BenchmarkReplayResult.compute_receipt_digest(payload)
        return BenchmarkReplayResult(
            execution_id=request.execution_id,
            request_digest=request.digest,
            outcome=result.outcome,
            evidence_polarity=result.evidence_polarity,
            verifier_details=payload["verifier_details"],
            receipt_digest=receipt_digest,
        )

    def rehydrate_result(self, *, payload: Mapping[str, object], request: ExecutionRequest) -> BenchmarkReplayResult:
        if not isinstance(payload, Mapping):
            raise TypeError("replay result receipt must be a mapping")
        if payload.get("execution_id") != request.execution_id or payload.get("request_digest") != request.digest:
            raise ValueError("replay result receipt is not bound to the canonical request")
        outcome = payload.get("outcome")
        polarity_data = payload.get("evidence_polarity")
        details = payload.get("verifier_details")
        supplied_receipt_digest = payload.get("receipt_digest")
        if (
            not isinstance(outcome, str)
            or not outcome.strip()
            or not isinstance(polarity_data, Mapping)
            or not isinstance(details, Mapping)
            or not isinstance(supplied_receipt_digest, str)
            or not supplied_receipt_digest.strip()
        ):
            raise ValueError("replay result receipt is malformed")
        receipt_payload = {
            "execution_id": request.execution_id,
            "request_digest": request.digest,
            "outcome": outcome,
            "evidence_polarity": dict(polarity_data),
            "verifier_details": dict(details),
        }
        expected_receipt_digest = BenchmarkReplayResult.compute_receipt_digest(receipt_payload)
        if supplied_receipt_digest != expected_receipt_digest:
            raise ValueError("replay result receipt canonical digest does not match its payload")
        try:
            polarity = {str(key): EvidencePolarity(str(value)) for key, value in polarity_data.items()}
        except ValueError as exc:
            raise ValueError("replay result receipt contains invalid evidence polarity") from exc
        result = BenchmarkReplayResult(
            request.execution_id,
            request.digest,
            outcome,
            polarity,
            dict(details),
            supplied_receipt_digest,
        )
        if dict(result.canonical_payload()) != dict(payload):
            raise ValueError("replay result receipt contains unsupported or non-canonical fields")
        return result
