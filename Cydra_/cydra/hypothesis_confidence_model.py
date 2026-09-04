"""Persist hypothesis-confidence projections while retaining update history."""
from __future__ import annotations

from .hypothesis_confidence import HypothesisConfidence
from .system_model import Edge, Node, SystemModel


def persist_hypothesis_confidence(
    model: SystemModel,
    projection: HypothesisConfidence,
    record_id: str,
) -> None:
    if not record_id.strip():
        raise ValueError("record_id must not be empty")
    if projection.source_update_id not in model.nodes:
        raise KeyError(f"missing source update: {projection.source_update_id}")
    if record_id in model.nodes:
        raise ValueError(f"confidence projection already exists: {record_id}")

    if projection.hypothesis_id not in model.nodes:
        model.add_node(Node(
            projection.hypothesis_id,
            "hypothesis",
            projection.hypothesis_id,
            {"current_confidence": projection.confidence, "current_confidence_source": record_id},
        ))
    elif model.nodes[projection.hypothesis_id].kind != "hypothesis":
        raise ValueError(f"hypothesis id is not a hypothesis node: {projection.hypothesis_id}")
    else:
        model.update_node_attributes(
            projection.hypothesis_id,
            {"current_confidence": projection.confidence, "current_confidence_source": record_id},
        )

    model.add_node(Node(record_id, "evidence", record_id, {
        "hypothesis_confidence": True,
        "hypothesis_id": projection.hypothesis_id,
        "confidence": projection.confidence,
        "source_update_id": projection.source_update_id,
    }))
    model.add_edge(Edge(record_id, "updates", projection.hypothesis_id))
    model.add_edge(Edge(record_id, "based_on", projection.source_update_id))
