"""Plan the smallest useful observation for resolving contradictions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .test_planning import ObservationOption


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    evidence_ids: tuple[str, ...]
    competing_hypothesis_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionPlan:
    contradiction_id: str
    observation_id: str
    utility: float
    rationale: str


def plan_contradiction_resolution(
    contradiction: Contradiction,
    observations: Iterable[ObservationOption],
) -> tuple[ResolutionPlan, ...]:
    """Rank authorized observations without executing them or resolving the conflict."""
    if not contradiction.contradiction_id.strip():
        raise ValueError("contradiction_id must not be empty")
    if not contradiction.competing_hypothesis_ids:
        raise ValueError("contradiction requires competing hypotheses")
    plans = []
    target_count = len(contradiction.competing_hypothesis_ids)
    for option in observations:
        states = len(set(option.expected_states))
        if states < 2:
            utility = 0.0
        else:
            utility = min(1.0, (states - 1) / target_count) / option.cost
        plans.append(
            ResolutionPlan(
                contradiction.contradiction_id,
                option.observation_id,
                utility,
                "prioritizes distinguishable outcomes per unit cost; no execution or resolution performed",
            )
        )
    return tuple(sorted(plans, key=lambda p: (-p.utility, p.observation_id)))
