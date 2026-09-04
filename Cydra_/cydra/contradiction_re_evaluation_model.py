"""Persist contradiction re-evaluation results without overwriting evidence or beliefs."""
from __future__ import annotations

from .contradiction_re_evaluation import ReEvaluation
from .system_model import Edge, Node, SystemModel


def persist_re_evaluation(model: SystemModel, result: ReEvaluation, record_id: str) -> None:
    if not record_id.strip():
        raise ValueError("record_id must not be empty")
    if result.contradiction_id not in model.nodes:
        raise KeyError(f"missing contradiction node: {result.contradiction_id}")
    if result.evidence_id not in model.nodes:
        raise KeyError(f"missing evidence node: {result.evidence_id}")
    if record_id in model.nodes:
        raise ValueError(f"re-evaluation already exists: {record_id}")
    model.add_node(Node(record_id, "evidence", record_id, {
        "re_evaluation": True,
        "disposition": result.disposition.value,
        "rationale": result.rationale,
        "source_evidence_id": result.evidence_id,
    }))
    model.add_edge(Edge(result.contradiction_id, "re_evaluated_by", record_id))
    model.add_edge(Edge(record_id, "based_on", result.evidence_id))
