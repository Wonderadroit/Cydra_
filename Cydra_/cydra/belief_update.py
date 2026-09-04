"""Conservative belief updates driven by contradiction re-evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from .contradiction_re_evaluation import ContradictionDisposition

@dataclass(frozen=True)
class BeliefUpdate:
    belief_id: str
    contradiction_id: str
    prior_confidence: float
    posterior_confidence: float
    disposition: ContradictionDisposition
    evidence_id: str
    rationale: str

def update_belief(belief_id: str, contradiction_id: str, prior_confidence: float, disposition: ContradictionDisposition, evidence_id: str, step: float = 0.25) -> BeliefUpdate:
    if not belief_id.strip() or not contradiction_id.strip() or not evidence_id.strip():
        raise ValueError("belief_id, contradiction_id and evidence_id must not be empty")
    if not 0.0 <= prior_confidence <= 1.0:
        raise ValueError("prior_confidence must be between 0 and 1")
    if not 0.0 < step <= 1.0:
        raise ValueError("step must be greater than 0 and at most 1")
    if disposition is ContradictionDisposition.SUPPORTED:
        posterior = prior_confidence + step * (1.0 - prior_confidence)
    elif disposition is ContradictionDisposition.REJECTED:
        posterior = prior_confidence * (1.0 - step)
    else:
        posterior = prior_confidence
    rationale = "belief updated from recorded re-evaluation; uncertainty preserved for inconclusive evidence"
    return BeliefUpdate(belief_id, contradiction_id, prior_confidence, posterior, disposition, evidence_id, rationale)
