"""Re-evaluate a contradiction from externally recorded observation outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContradictionDisposition(str, Enum):
    UNRESOLVED = "unresolved"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ReEvaluation:
    contradiction_id: str
    disposition: ContradictionDisposition
    evidence_id: str
    rationale: str


def reevaluate_contradiction(
    contradiction_id: str,
    evidence_id: str,
    *,
    supports_hypothesis: bool | None,
) -> ReEvaluation:
    """Convert an external outcome into a conservative contradiction disposition."""
    if not contradiction_id.strip() or not evidence_id.strip():
        raise ValueError("contradiction_id and evidence_id must not be empty")
    if supports_hypothesis is True:
        disposition = ContradictionDisposition.SUPPORTED
        rationale = "external evidence supports the selected hypothesis"
    elif supports_hypothesis is False:
        disposition = ContradictionDisposition.REJECTED
        rationale = "external evidence rejects the selected hypothesis"
    else:
        disposition = ContradictionDisposition.INCONCLUSIVE
        rationale = "external evidence does not distinguish the competing hypotheses"
    return ReEvaluation(contradiction_id, disposition, evidence_id, rationale)
