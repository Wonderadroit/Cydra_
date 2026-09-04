"""Bounded persistent learning extracted from verified CYDRA investigations.

Learning is derived from canonical findings, not arbitrary caller labels. The
learning store improves future reasoning inside an externally issued authority
envelope; it can never create or enlarge that envelope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .finding import Finding


class LearningError(ValueError):
    """Raised when persisted learning violates canonical bounds."""


@dataclass(frozen=True)
class LearningLimits:
    max_invariants: int = 256
    max_hypotheses: int = 256
    max_observation_patterns: int = 512
    max_dependency_patterns: int = 512
    max_budget_heuristics: int = 256

    def __post_init__(self) -> None:
        for name in (
            "max_invariants", "max_hypotheses", "max_observation_patterns",
            "max_dependency_patterns", "max_budget_heuristics",
        ):
            if getattr(self, name) < 1:
                raise LearningError(f"{name} must be positive")


@dataclass(frozen=True)
class LearningRecord:
    """One finding-derived learning contribution with explicit provenance."""

    finding_id: str
    category: str
    key: str
    value: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        for name in ("finding_id", "category", "key", "value"):
            if not getattr(self, name).strip():
                raise LearningError(f"{name} must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise LearningError("confidence must be between 0 and 1")
        if self.category not in LearningStore.CATEGORIES:
            raise LearningError(f"unsupported learning category: {self.category}")

    @property
    def learning_id(self) -> str:
        payload = {
            "finding_id": self.finding_id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class FindingLearningContribution:
    """Explicit, provenance-bound learning supplied for one verified finding."""

    invariant: str
    hypothesis: str
    observation_pattern: str
    dependency_pattern: str
    budget_heuristic: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "invariant", "hypothesis", "observation_pattern",
            "dependency_pattern", "budget_heuristic",
        ):
            if not getattr(self, name).strip():
                raise LearningError(f"{name} contribution must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise LearningError("confidence must be between 0 and 1")

    def records_for(self, finding_id: str) -> tuple[LearningRecord, ...]:
        if not isinstance(finding_id, str) or not finding_id.strip():
            raise LearningError("finding_id must not be empty")
        values = (
            ("invariant", self.invariant), ("hypothesis", self.hypothesis),
            ("observation_pattern", self.observation_pattern),
            ("dependency_pattern", self.dependency_pattern),
            ("budget_heuristic", self.budget_heuristic),
        )
        return tuple(
            LearningRecord(finding_id=finding_id, category=category, key=value, value=value, confidence=self.confidence)
            for category, value in values
        )


@dataclass
class LearningStore:
    """Finite canonical store for reusable investigation knowledge."""

    CATEGORIES = frozenset({"invariant", "hypothesis", "observation_pattern", "dependency_pattern", "budget_heuristic"})
    limits: LearningLimits = field(default_factory=LearningLimits)
    records: dict[str, LearningRecord] = field(default_factory=dict)

    def _validate_batch(self, records: tuple[LearningRecord, ...]) -> None:
        category_limits = {
            "invariant": self.limits.max_invariants,
            "hypothesis": self.limits.max_hypotheses,
            "observation_pattern": self.limits.max_observation_patterns,
            "dependency_pattern": self.limits.max_dependency_patterns,
            "budget_heuristic": self.limits.max_budget_heuristics,
        }
        staged: dict[str, LearningRecord] = {}
        category_additions: dict[str, int] = {}
        for record in records:
            existing = self.records.get(record.learning_id)
            if existing is not None:
                if existing != record:
                    raise LearningError("learning identity collision")
                continue
            previous = staged.get(record.learning_id)
            if previous is not None:
                if previous != record:
                    raise LearningError("learning identity collision")
                # The exact same new record appears more than once in this
                # batch. It will occupy one store slot, so it must count once.
                continue
            staged[record.learning_id] = record
            category_additions[record.category] = category_additions.get(record.category, 0) + 1

        for category, additions in category_additions.items():
            current = sum(1 for item in self.records.values() if item.category == category)
            if current + additions > category_limits[category]:
                raise LearningError(f"{category} learning budget exhausted")

    def learn_many(self, records: tuple[LearningRecord, ...]) -> tuple[str, ...]:
        """Atomically persist a batch; failed validation leaves the store unchanged."""
        self._validate_batch(records)
        ids: list[str] = []
        for record in records:
            if record.learning_id not in self.records:
                self.records[record.learning_id] = record
            ids.append(record.learning_id)
        return tuple(ids)

    def learn(self, record: LearningRecord) -> str:
        return self.learn_many((record,))[0]

    def learn_verified_finding(self, finding: "Finding", contribution: FindingLearningContribution) -> tuple[str, ...]:
        if not getattr(finding, "finding_id", "").strip():
            raise LearningError("verified finding requires a canonical finding ID")
        records = contribution.records_for(finding.finding_id)
        return self.learn_many(records)

    def learn_from_finding(
        self, *, finding_id: str, invariant: str | None = None, hypothesis: str | None = None,
        observation_pattern: str | None = None, dependency_pattern: str | None = None,
        budget_heuristic: str | None = None,
    ) -> tuple[str, ...]:
        values = (
            ("invariant", invariant), ("hypothesis", hypothesis),
            ("observation_pattern", observation_pattern),
            ("dependency_pattern", dependency_pattern), ("budget_heuristic", budget_heuristic),
        )
        records = tuple(
            LearningRecord(finding_id, category, value, value)
            for category, value in values if value is not None
        )
        return self.learn_many(records)

    def apply_candidates(self, category: str, key: str) -> tuple[LearningRecord, ...]:
        if category not in self.CATEGORIES:
            raise LearningError(f"unsupported learning category: {category}")
        return tuple(record for record in self.records.values() if record.category == category and record.key == key)

    def authority_independent_fingerprint(self) -> str:
        payload = [
            {"id": record.learning_id, "finding_id": record.finding_id, "category": record.category,
             "key": record.key, "value": record.value, "confidence": record.confidence}
            for record in sorted(self.records.values(), key=lambda item: item.learning_id)
        ]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def export(self) -> Mapping[str, object]:
        return {
            "limits": {
                "max_invariants": self.limits.max_invariants, "max_hypotheses": self.limits.max_hypotheses,
                "max_observation_patterns": self.limits.max_observation_patterns,
                "max_dependency_patterns": self.limits.max_dependency_patterns,
                "max_budget_heuristics": self.limits.max_budget_heuristics,
            },
            "records": [
                {"finding_id": record.finding_id, "category": record.category, "key": record.key,
                 "value": record.value, "confidence": record.confidence}
                for record in sorted(self.records.values(), key=lambda item: item.learning_id)
            ],
            "fingerprint": self.authority_independent_fingerprint(),
        }
