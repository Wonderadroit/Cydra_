"""Maintain current belief projections without deleting belief history."""
from __future__ import annotations
from dataclasses import dataclass
from .belief_update import BeliefUpdate
from .system_model import Edge, Node, SystemModel

@dataclass(frozen=True)
class CurrentBelief:
    belief_id: str
    confidence: float
    source_update_id: str

def apply_belief_update(model: SystemModel, update: BeliefUpdate, update_id: str) -> CurrentBelief:
    if update_id not in model.nodes:
        raise KeyError(f"missing persisted belief update: {update_id}")
    if update.belief_id in model.nodes and model.nodes[update.belief_id].kind != "belief":
        raise ValueError(f"belief id is not a belief node: {update.belief_id}")
    if update.belief_id not in model.nodes:
        model.add_node(Node(update.belief_id, "belief", update.belief_id, {
            "current_confidence": update.posterior_confidence,
            "current_source_update": update_id,
        }))
    else:
        model.update_node_attributes(update.belief_id, {
            "current_confidence": update.posterior_confidence,
            "current_source_update": update_id,
        })
    model.add_edge(Edge(update_id, "updates", update.belief_id))
    return CurrentBelief(update.belief_id, update.posterior_confidence, update_id)
