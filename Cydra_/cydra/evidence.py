"""Evidence and provenance primitives for CYDRA."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    DOCUMENT = "document"
    SOURCE_CODE = "source_code"
    RECON = "recon"
    TEST_RESULT = "test_result"


@dataclass(frozen=True)
class Provenance:
    source: str
    acquired_at: datetime
    collector: str
    scope_status: str
    details: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.acquired_at.tzinfo is None:
            raise ValueError("acquired_at must be timezone-aware")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.collector.strip():
            raise ValueError("collector must not be empty")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: EvidenceKind
    value: Any
    provenance: Provenance
    interpretation: str | None = None
    confidence: float = 1.0
    contradicted_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


class EvidenceStore:
    """Append-only evidence registry for the reasoning layer."""

    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    def add(self, evidence: Evidence) -> None:
        if evidence.evidence_id in self._items:
            raise ValueError(f"duplicate evidence: {evidence.evidence_id}")
        self._items[evidence.evidence_id] = evidence

    def get(self, evidence_id: str) -> Evidence | None:
        return self._items.get(evidence_id)

    def all(self) -> tuple[Evidence, ...]:
        return tuple(self._items.values())

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
