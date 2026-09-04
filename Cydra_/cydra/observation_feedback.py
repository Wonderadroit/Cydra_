"""Close the observation -> evidence -> reasoning feedback loop.

This module is deliberately orchestration-only: it consumes an already recorded
observation outcome and derives the verification/belief inputs without executing tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .hypotheses import BeliefUpdate, Hypothesis, update_hypothesis
from .invariants import CandidateVerification, VerificationEvidence
from .observation_outcomes import ObservationOutcome


@dataclass(frozen=True)
class ObservationFeedback:
    observation_id: str
    evidence_ids: tuple[str, ...]
    hypothesis_updates: tuple[BeliefUpdate, ...]


def apply_observation_feedback(
    outcome: ObservationOutcome,
    verification: CandidateVerification,
    hypotheses: Iterable[Hypothesis],
    evidence: Iterable[VerificationEvidence],
) -> tuple[Hypothesis, ...]:
    """Apply an existing observation outcome to hypotheses without executing anything.

    ``ObservationOutcome.outcome_id`` is the stable external outcome identity. The
    verification record carries the same identity in ``evidence_ids``; the graph layer
    maps it to the canonical ``observation_outcome:{outcome_id}`` evidence node.
    """
    items = tuple(evidence)
    evidence_ids = set(verification.evidence_ids)
    if outcome.outcome_id not in evidence_ids:
        raise ValueError("observation outcome evidence is not part of verification")
    updated = []
    for hypothesis in hypotheses:
        new_hypothesis, _ = update_hypothesis(hypothesis, verification, items)
        updated.append(new_hypothesis)
    return tuple(updated)
