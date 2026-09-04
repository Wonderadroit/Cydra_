"""Lifecycle tracking for contradiction-resolution plans and observations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .system_model import Edge, Node, SystemModel


class ResolutionStatus(StrEnum):
    PLANNED = "planned"
    EXECUTED = "executed"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


_ALLOWED = {
    ResolutionStatus.PLANNED: {ResolutionStatus.EXECUTED},
    ResolutionStatus.EXECUTED: {
        ResolutionStatus.SUCCESSFUL,
        ResolutionStatus.FAILED,
        ResolutionStatus.INCONCLUSIVE,
    },
    ResolutionStatus.SUCCESSFUL: set(),
    ResolutionStatus.FAILED: set(),
    ResolutionStatus.INCONCLUSIVE: set(),
}


@dataclass(frozen=True)
class LifecycleTransition:
    record_id: str
    from_status: ResolutionStatus
    to_status: ResolutionStatus
    outcome_id: str | None = None


def transition_resolution(
    model: SystemModel,
    *,
    record_id: str,
    to_status: ResolutionStatus,
    outcome_id: str | None = None,
) -> LifecycleTransition:
    """Advance a persisted resolution plan through an explicit lifecycle.

    This records externally performed execution/results; it never performs the test.
    """
    if record_id not in model.nodes:
        raise KeyError(f"unknown resolution record: {record_id}")
    node = model.nodes[record_id]
    if node.attributes.get("resolution_plan") is not True:
        raise ValueError(f"node is not a resolution plan: {record_id}")
    current = ResolutionStatus(node.attributes.get("status", ResolutionStatus.PLANNED))
    if to_status not in _ALLOWED[current]:
        raise ValueError(f"invalid resolution transition: {current} -> {to_status}")
    if to_status in {
        ResolutionStatus.SUCCESSFUL,
        ResolutionStatus.FAILED,
        ResolutionStatus.INCONCLUSIVE,
    } and not (outcome_id and outcome_id.strip()):
        raise ValueError("terminal result requires outcome_id")
    if to_status == ResolutionStatus.EXECUTED and outcome_id:
        raise ValueError("executed transition cannot carry a terminal outcome")

    attrs = dict(node.attributes)
    attrs["status"] = to_status.value
    if outcome_id:
        attrs["outcome_id"] = outcome_id
        evidence_id = f"observation_outcome:{outcome_id}"
        if evidence_id not in model.nodes:
            raise KeyError(f"unknown observation outcome: {evidence_id}")
        model.add_edge(Edge(record_id, "resulted_in", evidence_id))
    model.nodes[record_id] = Node(node.node_id, node.kind, node.label, attrs)
    return LifecycleTransition(record_id, current, to_status, outcome_id)
