"""Record outcomes of planned observations as auditable model evidence.

Execution happens outside CYDRA. This module ingests an externally observed result,
links it to the original plan, and preserves the provenance needed for later
verification and hypothesis updating.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .system_model import Edge, Node, SystemModel


@dataclass(frozen=True)
class ObservationOutcome:
    observation_id: str
    outcome_id: str
    result: str
    source: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        for value, name in ((self.observation_id, "observation_id"), (self.outcome_id, "outcome_id"), (self.result, "result"), (self.source, "source")):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


def record_observation_outcome(
    model: SystemModel,
    *,
    observation_id: str,
    outcome_id: str,
    result: str,
    source: str,
    confidence: float = 1.0,
    metadata: Mapping[str, object] | None = None,
) -> ObservationOutcome:
    """Ingest an externally produced observation outcome without executing anything."""
    node_id = f"observation:{observation_id}"
    if node_id not in model.nodes:
        raise KeyError(f"unknown observation plan: {node_id}")
    planned = model.nodes[node_id]
    if planned.kind != "observation":
        raise ValueError(f"model node is not an observation: {node_id}")
    if planned.attributes.get("status") != "planned":
        raise ValueError(f"observation is not awaiting an outcome: {node_id}")
    if not result.strip() or not source.strip() or not outcome_id.strip():
        raise ValueError("outcome_id, result, and source must not be empty")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    evidence_node_id = f"observation_outcome:{outcome_id}"
    if evidence_node_id in model.nodes:
        raise ValueError(f"observation outcome already exists: {evidence_node_id}")

    attributes = {
        "observation_id": observation_id,
        "result": result,
        "source": source,
        "confidence": confidence,
        "metadata": dict(metadata or {}),
    }
    model.add_node(Node(evidence_node_id, "evidence", result, attributes))
    model.add_edge(Edge(node_id, "produced", evidence_node_id, {"executed_externally": True}))

    updated_attributes = dict(planned.attributes)
    updated_attributes.update({"status": "completed", "executed": True, "outcome_id": outcome_id})
    model.nodes[node_id] = Node(planned.node_id, planned.kind, planned.label, updated_attributes)

    return ObservationOutcome(observation_id, outcome_id, result, source, confidence)
