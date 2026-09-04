"""Persist auditable observation plans in the SystemModel.

Planning remains separate from execution: this module records what was selected,
why it was selected, and which uncertainty it was intended to reduce.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .system_model import Edge, Node, SystemModel
from .test_planning import TestPlan


@dataclass(frozen=True)
class ObservationRecord:
    observation_id: str
    description: str
    information_gain: float
    cost: float
    utility: float
    rationale: str
    hypothesis_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()


def persist_test_plan(
    model: SystemModel,
    plan: TestPlan,
    *,
    hypothesis_ids: Iterable[str] = (),
    candidate_ids: Iterable[str] = (),
) -> ObservationRecord:
    """Persist a selected test plan without executing or predicting its outcome."""
    hypotheses = tuple(sorted(set(hypothesis_ids)))
    candidates = tuple(sorted(set(candidate_ids)))
    missing = [ref for ref in (*hypotheses, *candidates) if ref not in model.nodes]
    if missing:
        raise KeyError(f"missing model node(s): {', '.join(missing)}")

    node_id = f"observation:{plan.observation_id}"
    if node_id in model.nodes:
        raise ValueError(f"observation plan already exists: {node_id}")

    attributes = {
        "status": "planned",
        "description": plan.description,
        "information_gain": plan.information_gain,
        "cost": plan.cost,
        "utility": plan.utility,
        "rationale": plan.rationale,
        "hypothesis_ids": list(hypotheses),
        "candidate_ids": list(candidates),
        "executed": False,
    }
    model.add_node(Node(node_id, "observation", plan.description, attributes))

    for hypothesis_id in hypotheses:
        model.add_edge(Edge(node_id, "tests", hypothesis_id, {"planned": True}))
    for candidate_id in candidates:
        model.add_edge(Edge(node_id, "targets", candidate_id, {"planned": True}))

    return ObservationRecord(
        plan.observation_id,
        plan.description,
        plan.information_gain,
        plan.cost,
        plan.utility,
        plan.rationale,
        hypotheses,
        candidates,
    )
