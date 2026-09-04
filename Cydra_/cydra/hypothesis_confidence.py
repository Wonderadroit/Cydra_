"""Maintain explicit confidence projections for competing hypotheses."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class HypothesisConfidence:
    hypothesis_id: str
    confidence: float
    source_update_id: str

def project_hypothesis_confidence(hypothesis_id: str, confidence: float, source_update_id: str) -> HypothesisConfidence:
    if not hypothesis_id.strip() or not source_update_id.strip():
        raise ValueError("hypothesis_id and source_update_id must not be empty")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return HypothesisConfidence(hypothesis_id, confidence, source_update_id)

def normalize_competing_confidences(confidences: dict[str, float]) -> dict[str, float]:
    if not confidences:
        raise ValueError("at least one hypothesis is required")
    if any(not k.strip() for k in confidences) or any(not 0.0 <= v <= 1.0 for v in confidences.values()):
        raise ValueError("hypothesis identifiers and confidences must be valid")
    total = sum(confidences.values())
    if total <= 0:
        raise ValueError("total confidence must be greater than zero")
    return {k: v / total for k, v in confidences.items()}
