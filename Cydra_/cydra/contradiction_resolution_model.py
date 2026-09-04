"""Persist contradiction-resolution plans in the persistent system model."""
from __future__ import annotations

from dataclasses import dataclass
from .system_model import Edge, Node, SystemModel
from .contradiction_resolution import ResolutionPlan

@dataclass(frozen=True)
class ResolutionModelRecord:
    record_id: str
    contradiction_id: str
    plan: ResolutionPlan


def persist_resolution_plan(model: SystemModel, record: ResolutionModelRecord) -> None:
    """Persist a resolution plan and provenance links without executing it."""
    if record.record_id in model.nodes:
        raise ValueError(f"resolution record already exists: {record.record_id}")
    if record.contradiction_id not in model.nodes:
        raise KeyError(f"missing contradiction node: {record.contradiction_id}")
    if record.plan.observation_id not in model.nodes:
        raise KeyError(f"missing observation node: {record.plan.observation_id}")
    model.add_node(Node(record.record_id, "evidence", record.record_id, {
        "resolution_plan": True,
        "contradiction_id": record.contradiction_id,
        "utility": record.plan.utility,
        "rationale": record.plan.rationale,
        "executed": False,
    }))
    model.add_edge(Edge(record.contradiction_id, "has_resolution_plan", record.record_id))
    model.add_edge(Edge(record.record_id, "selects_observation", record.plan.observation_id))
