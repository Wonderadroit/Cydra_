"""Persist a normalized competing-hypothesis confidence snapshot."""
from __future__ import annotations
from .hypothesis_confidence import normalize_competing_confidences
from .system_model import Edge, Node, SystemModel

def persist_hypothesis_set(model: SystemModel, confidences: dict[str, float], source_update_id: str, record_id: str) -> dict[str, float]:
    if not source_update_id.strip() or not record_id.strip():
        raise ValueError("source_update_id and record_id must not be empty")
    if source_update_id not in model.nodes:
        raise KeyError(f"missing source update: {source_update_id}")
    if record_id in model.nodes:
        raise ValueError(f"hypothesis set already exists: {record_id}")
    normalized = normalize_competing_confidences(confidences)
    for hypothesis_id in normalized:
        if hypothesis_id in model.nodes and model.nodes[hypothesis_id].kind != "hypothesis":
            raise ValueError(f"hypothesis id is not a hypothesis node: {hypothesis_id}")
        if hypothesis_id not in model.nodes:
            model.add_node(Node(hypothesis_id, "hypothesis", hypothesis_id, {}))
    model.add_node(Node(record_id, "evidence", record_id, {
        "hypothesis_set": True,
        "source_update_id": source_update_id,
        "confidences": normalized,
    }))
    model.add_edge(Edge(record_id, "based_on", source_update_id))
    for hypothesis_id, confidence in normalized.items():
        model.add_edge(Edge(record_id, "assigns_confidence", hypothesis_id, {"confidence": confidence}))
    return normalized
