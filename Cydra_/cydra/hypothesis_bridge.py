"""Explicit boundary between planning and persistent hypothesis representations.

The planner representation is optimized for information-gain planning. The persistent
representation is the auditable belief/state record. Conversion is explicit and lossless
for identity, belief, state, and declared prediction metadata; no missing prediction is
invented during rehydration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from .hypotheses import Hypothesis as PersistentHypothesis, HypothesisState as PersistentHypothesisState
from .planner import Hypothesis as PlanningHypothesis, HypothesisState as PlanningHypothesisState


@dataclass(frozen=True)
class HypothesisBoundaryRecord:
    """Explicit synchronization record across the planning/persistence boundary."""
    hypothesis_id: str
    planning_name: str
    probability: float
    predictions: Dict[str, Dict[str, float]]
    state: PlanningHypothesisState


def planning_to_persistent(hypothesis: PlanningHypothesis) -> PersistentHypothesis:
    """Project a planner hypothesis into the persistent representation.

    Probability becomes persistent belief, while predictions remain explicitly tagged as
    planning metadata. The canonical ID is derived from the planner identity and is not
    inferred from statement text.
    """
    return PersistentHypothesis(
        hypothesis_id=hypothesis.hypothesis_id,
        statement=hypothesis.name,
        belief=hypothesis.probability,
        state=PersistentHypothesisState(hypothesis.state.value),
        planning_predictions={
            observation: dict(outcomes)
            for observation, outcomes in hypothesis.predictions.items()
        },
    )


def planning_set_to_persistent(
    hypotheses: Iterable[PlanningHypothesis],
) -> tuple[PersistentHypothesis, ...]:
    """Project a planning hypothesis set while preserving order and explicit state."""
    return tuple(planning_to_persistent(h) for h in hypotheses)


def persistent_to_planner(
    hypothesis: PersistentHypothesis,
    *,
    predictions: Dict[str, Dict[str, float]] | None = None,
) -> PlanningHypothesis:
    """Rehydrate a planner hypothesis without inventing prediction data.

    If ``predictions`` is omitted, the explicitly persisted planning metadata is used.
    Persistent belief/state are copied directly. The returned planner object is immutable,
    so conversion cannot mutate the persistent record.
    """
    selected = predictions if predictions is not None else hypothesis.planning_predictions
    return PlanningHypothesis(
        hypothesis.name,
        hypothesis.belief,
        {observation: dict(outcomes) for observation, outcomes in selected.items()},
        PlanningHypothesisState(hypothesis.state.value),
    )


def boundary_record(hypothesis: PlanningHypothesis) -> HypothesisBoundaryRecord:
    """Capture the exact planner values crossing the representation boundary."""
    return HypothesisBoundaryRecord(
        hypothesis_id=hypothesis.hypothesis_id,
        planning_name=hypothesis.name,
        probability=hypothesis.probability,
        predictions={
            observation: dict(outcomes)
            for observation, outcomes in hypothesis.predictions.items()
        },
        state=hypothesis.state,
    )
