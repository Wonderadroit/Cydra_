"""Bounded reusable CYDRA knowledge base.

The knowledge base is the reasoning-facing catalog over CYDRA's five reusable
knowledge classes: invariants, hypotheses, observation patterns, dependency
patterns, and budget profiles. It deliberately separates architectural seed
knowledge from finding-derived learning: seeds are useful defaults, but they
are never represented as empirical findings.

Knowledge can rank reasoning candidates, but it can never grant scope, budget,
depth, lease, execution capability, or expansion authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .learning import LearningStore
    from .investigation_profiles import CapabilityProfile


class KnowledgeBaseError(ValueError):
    """Raised when knowledge violates canonical bounds or provenance rules."""


class KnowledgeKind(str, Enum):
    INVARIANT = "invariant"
    HYPOTHESIS = "hypothesis"
    OBSERVATION_PATTERN = "observation_pattern"
    DEPENDENCY_PATTERN = "dependency_pattern"
    BUDGET_PROFILE = "budget_profile"


class KnowledgeOrigin(str, Enum):
    ARCHITECTURAL_SEED = "architectural_seed"
    FINDING_DERIVED = "finding_derived"


@dataclass(frozen=True)
class KnowledgeRecord:
    """One bounded reusable reasoning record with explicit provenance."""

    kind: KnowledgeKind
    key: str
    value: str
    origin: KnowledgeOrigin
    confidence: float = 1.0
    source_finding_id: str | None = None
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.value.strip():
            raise KnowledgeBaseError("knowledge key and value must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise KnowledgeBaseError("knowledge confidence must be between 0 and 1")
        if self.origin == KnowledgeOrigin.FINDING_DERIVED:
            if not self.source_finding_id or not self.source_finding_id.strip():
                raise KnowledgeBaseError("finding-derived knowledge requires source_finding_id")
        elif self.source_finding_id is not None:
            raise KnowledgeBaseError("architectural seed knowledge cannot claim finding provenance")
        if any(not capability.strip() for capability in self.capabilities):
            raise KnowledgeBaseError("knowledge capabilities must be non-empty strings")

    @property
    def knowledge_id(self) -> str:
        payload = {
            "kind": self.kind.value,
            "key": self.key,
            "value": self.value,
            "origin": self.origin.value,
            "confidence": self.confidence,
            "source_finding_id": self.source_finding_id,
            "capabilities": sorted(self.capabilities),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class BudgetProfile:
    """A recommendation, never an authority grant."""

    name: str
    max_observations: int
    max_dependency_depth: int
    economic_budget: float = 0.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise KnowledgeBaseError("budget profile name must not be empty")
        if self.max_observations < 0 or self.max_dependency_depth < 0 or self.economic_budget < 0:
            raise KnowledgeBaseError("budget profile limits must be non-negative")


@dataclass
class KnowledgeBase:
    """Finite catalog that combines safe seeds with finding-derived learning."""

    max_records: int = 2048
    records: dict[str, KnowledgeRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_records < 1:
            raise KnowledgeBaseError("max_records must be positive")

    def add(self, record: KnowledgeRecord) -> str:
        existing = self.records.get(record.knowledge_id)
        if existing is not None:
            if existing != record:
                raise KnowledgeBaseError("knowledge identity collision")
            return record.knowledge_id
        if len(self.records) >= self.max_records:
            raise KnowledgeBaseError("knowledge base capacity exhausted")
        self.records[record.knowledge_id] = record
        return record.knowledge_id

    def add_many(self, records: Iterable[KnowledgeRecord]) -> tuple[str, ...]:
        staged = tuple(records)
        new_ids = {record.knowledge_id for record in staged if record.knowledge_id not in self.records}
        if len(self.records) + len(new_ids) > self.max_records:
            raise KnowledgeBaseError("knowledge base capacity exhausted")
        for record in staged:
            self.add(record)
        return tuple(record.knowledge_id for record in staged)

    def matching(self, kind: KnowledgeKind | str, key: str) -> tuple[KnowledgeRecord, ...]:
        kind = KnowledgeKind(kind)
        return tuple(record for record in self.records.values() if record.kind == kind and record.key == key)

    def for_capability(self, capability: str) -> tuple[KnowledgeRecord, ...]:
        if not capability.strip():
            raise KnowledgeBaseError("capability must not be empty")
        return tuple(record for record in self.records.values() if capability in record.capabilities)

    def for_profile(self, profile: "CapabilityProfile") -> tuple[KnowledgeRecord, ...]:
        """Select knowledge enabled by a reasoning profile; never changes authority."""
        selected = list(self.for_capability(capability.value) for capability in profile.capabilities)
        flattened: dict[str, KnowledgeRecord] = {}
        for records in selected:
            for record in records:
                flattened[record.knowledge_id] = record
        return tuple(flattened.values())

    def budget_profiles(self) -> tuple[BudgetProfile, ...]:
        profiles: list[BudgetProfile] = []
        for record in self.records.values():
            if record.kind != KnowledgeKind.BUDGET_PROFILE:
                continue
            try:
                payload = json.loads(record.value)
                profiles.append(BudgetProfile(**payload))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise KnowledgeBaseError("invalid budget profile record") from exc
        return tuple(profiles)

    def ingest_learning(self, learning_store: "LearningStore") -> tuple[str, ...]:
        """Project canonical finding-derived LearningStore records into the KB."""
        projected: list[KnowledgeRecord] = []
        for record in learning_store.records.values():
            try:
                kind = KnowledgeKind(record.category)
            except ValueError as exc:
                raise KnowledgeBaseError(f"unsupported learning category: {record.category}") from exc
            projected.append(KnowledgeRecord(
                kind=kind, key=record.key, value=record.value,
                origin=KnowledgeOrigin.FINDING_DERIVED,
                confidence=record.confidence, source_finding_id=record.finding_id,
            ))
        return self.add_many(projected)

    def authority_independent_fingerprint(self) -> str:
        payload = [
            {
                "id": record.knowledge_id, "kind": record.kind.value,
                "key": record.key, "value": record.value, "origin": record.origin.value,
                "confidence": record.confidence, "source_finding_id": record.source_finding_id,
                "capabilities": sorted(record.capabilities),
            }
            for record in sorted(self.records.values(), key=lambda item: item.knowledge_id)
        ]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def export(self) -> Mapping[str, object]:
        return {
            "max_records": self.max_records,
            "records": [
                {
                    "id": record.knowledge_id, "kind": record.kind.value,
                    "key": record.key, "value": record.value, "origin": record.origin.value,
                    "confidence": record.confidence, "source_finding_id": record.source_finding_id,
                    "capabilities": sorted(record.capabilities),
                }
                for record in sorted(self.records.values(), key=lambda item: item.knowledge_id)
            ],
            "fingerprint": self.authority_independent_fingerprint(),
        }


def bootstrap_knowledge_base() -> KnowledgeBase:
    """Return the explicit architectural seed catalog discussed for CYDRA."""
    kb = KnowledgeBase()
    seeds = [
        (KnowledgeKind.INVARIANT, "balance_attributable_value", "balance == attributable value", frozenset()),
        (KnowledgeKind.INVARIANT, "owner_caller", "onlyOwner -> caller == owner", frozenset()),
        (KnowledgeKind.INVARIANT, "price_slippage", "price ~= external_market_price +/- slippage", frozenset({"economic"})),
        (KnowledgeKind.INVARIANT, "collateral_debt", "collateral > debt", frozenset({"economic"})),
        (KnowledgeKind.INVARIANT, "flash_loan_price_impact", "flash loan -> price impact <= X%", frozenset({"economic"})),
        (KnowledgeKind.INVARIANT, "multi_contract_consistency", "multi-contract state remains consistent", frozenset({"cross_contract"})),
        (KnowledgeKind.HYPOTHESIS, "reentrancy", "reentrancy via external call", frozenset()),
        (KnowledgeKind.HYPOTHESIS, "access_control", "access control bypass", frozenset()),
        (KnowledgeKind.HYPOTHESIS, "arithmetic", "arithmetic overflow/underflow", frozenset()),
        (KnowledgeKind.HYPOTHESIS, "oracle_manipulation", "price oracle manipulation", frozenset({"economic"})),
        (KnowledgeKind.HYPOTHESIS, "state_desync", "cross-contract state desync", frozenset({"cross_contract"})),
        (KnowledgeKind.HYPOTHESIS, "economic_arbitrage", "economic arbitrage", frozenset({"economic"})),
        (KnowledgeKind.OBSERVATION_PATTERN, "simulate_flash_loan", "simulate flash loan + price change", frozenset({"economic"})),
        (KnowledgeKind.OBSERVATION_PATTERN, "contract_a_b_a", "call contract A -> B -> A", frozenset({"cross_contract"})),
        (KnowledgeKind.OBSERVATION_PATTERN, "multiple_attackers", "simulate with multiple attackers", frozenset({"economic"})),
        (KnowledgeKind.DEPENDENCY_PATTERN, "contract_library", "contract -> library", frozenset({"cross_contract"})),
        (KnowledgeKind.DEPENDENCY_PATTERN, "contract_oracle", "contract -> oracle", frozenset({"cross_contract", "economic"})),
        (KnowledgeKind.DEPENDENCY_PATTERN, "contract_token", "contract -> token", frozenset({"cross_contract", "economic"})),
        (KnowledgeKind.DEPENDENCY_PATTERN, "router_pool", "contract -> router -> pool", frozenset({"cross_contract", "economic"})),
        (KnowledgeKind.DEPENDENCY_PATTERN, "aggregator_pools", "contract -> aggregator -> multiple pools", frozenset({"cross_contract", "economic"})),
    ]
    for kind, key, value, capabilities in seeds:
        kb.add(KnowledgeRecord(kind, key, value, KnowledgeOrigin.ARCHITECTURAL_SEED, capabilities=capabilities))

    budget_profiles = {
        "standard": {"name": "standard", "max_observations": 50, "max_dependency_depth": 3, "economic_budget": 0.0, "rationale": "bounded baseline"},
        "reentrancy": {"name": "reentrancy", "max_observations": 50, "max_dependency_depth": 3, "economic_budget": 0.0, "rationale": "seeded hypothesis heuristic"},
        "access_control": {"name": "access_control", "max_observations": 30, "max_dependency_depth": 2, "economic_budget": 0.0, "rationale": "seeded hypothesis heuristic"},
        "arithmetic": {"name": "arithmetic", "max_observations": 20, "max_dependency_depth": 2, "economic_budget": 0.0, "rationale": "seeded hypothesis heuristic"},
        "economic_attack": {"name": "economic_attack", "max_observations": 200, "max_dependency_depth": 5, "economic_budget": 200.0, "rationale": "bounded economic exploration recommendation"},
        "cross_contract": {"name": "cross_contract", "max_observations": 150, "max_dependency_depth": 4, "economic_budget": 0.0, "rationale": "bounded cross-contract exploration recommendation"},
    }
    for key, payload in budget_profiles.items():
        capability = "economic" if key == "economic_attack" else "cross_contract" if key == "cross_contract" else ""
        kb.add(KnowledgeRecord(
            KnowledgeKind.BUDGET_PROFILE, key,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            KnowledgeOrigin.ARCHITECTURAL_SEED,
            capabilities=frozenset({capability}) if capability else frozenset(),
        ))
    return kb
