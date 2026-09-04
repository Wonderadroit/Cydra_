"""End-to-end persistent reasoning loop for observed contradiction outcomes."""
from __future__ import annotations
from dataclasses import dataclass
from .belief_update import BeliefUpdate, update_belief
from .belief_update_model import persist_belief_update
from .contradiction_re_evaluation import ReEvaluation, reevaluate_contradiction
from .contradiction_re_evaluation_model import persist_re_evaluation
from .current_belief_state import CurrentBelief, apply_belief_update
from .system_model import SystemModel

@dataclass(frozen=True)
class ReasoningLoopResult:
    re_evaluation: ReEvaluation
    belief_update: BeliefUpdate
    current_belief: CurrentBelief

def run_reasoning_loop(
    model: SystemModel,
    *,
    contradiction_id: str,
    evidence_id: str,
    belief_id: str,
    prior_confidence: float,
    supports_hypothesis: bool | None,
    re_evaluation_id: str,
    belief_update_id: str,
) -> ReasoningLoopResult:
    """Persist each stage in order; fail before mutation when required references are absent."""
    reevaluation = reevaluate_contradiction(
        contradiction_id, evidence_id, supports_hypothesis=supports_hypothesis
    )
    persist_re_evaluation(model, reevaluation, re_evaluation_id)
    belief_update = update_belief(
        belief_id, contradiction_id, prior_confidence,
        reevaluation.disposition, evidence_id,
    )
    persist_belief_update(model, belief_update, belief_update_id)
    current = apply_belief_update(model, belief_update, belief_update_id)
    return ReasoningLoopResult(reevaluation, belief_update, current)
