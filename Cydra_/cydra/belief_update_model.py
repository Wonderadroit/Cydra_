"""Persist belief updates as append-only evidence in the system model."""
from __future__ import annotations
from .belief_update import BeliefUpdate
from .system_model import Edge, Node, SystemModel

def persist_belief_update(model: SystemModel, update: BeliefUpdate, record_id: str) -> None:
    if not record_id.strip():
        raise ValueError("record_id must not be empty")
    if update.contradiction_id not in model.nodes:
        raise KeyError(f"missing contradiction node: {update.contradiction_id}")
    if update.evidence_id not in model.nodes:
        raise KeyError(f"missing evidence node: {update.evidence_id}")
    if record_id in model.nodes:
        raise ValueError(f"belief update already exists: {record_id}")
    model.add_node(Node(record_id, "evidence", record_id, {
        "belief_update": True,
        "belief_id": update.belief_id,
        "prior_confidence": update.prior_confidence,
        "posterior_confidence": update.posterior_confidence,
        "disposition": update.disposition.value,
        "rationale": update.rationale,
    }))
    model.add_edge(Edge(update.contradiction_id, "updated_by", record_id))
    model.add_edge(Edge(record_id, "based_on", update.evidence_id))
