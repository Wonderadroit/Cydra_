from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional

from .planner import Hypothesis


class EvidencePolarity(str, Enum):
    """Explicit evidentiary relationship between an observation and a hypothesis."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class UpdateResult:
    hypotheses: List[Hypothesis]
    observed_outcome: str
    evidence_strength: float
    status: str
    explanation: str
    evidence_polarity: Dict[str, EvidencePolarity] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.evidence_strength <= 1.0:
            raise ValueError("evidence_strength must be between 0 and 1")
        hypothesis_names = {h.name for h in self.hypotheses}
        for name, polarity in self.evidence_polarity.items():
            if name not in hypothesis_names:
                raise ValueError(f"evidence polarity references unknown hypothesis: {name}")
            if not isinstance(polarity, EvidencePolarity):
                raise ValueError("evidence polarity values must be EvidencePolarity")


def _normalize(values: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, v) for v in values.values())
    if total <= 0:
        return {k: 0.0 for k in values}
    return {k: max(0.0, v) / total for k, v in values.items()}


def _copy_hypothesis(hypothesis: Hypothesis, probability: Optional[float] = None) -> Hypothesis:
    return Hypothesis(
        hypothesis.name,
        hypothesis.probability if probability is None else probability,
        {name: dict(outcomes) for name, outcomes in hypothesis.predictions.items()},
        hypothesis.state,
    )


def update_hypotheses(
    hypotheses: List[Hypothesis],
    observation_name: str,
    observed_outcome: str,
    evidence_strength: float = 1.0,
    evidence_polarity: Optional[Mapping[str, EvidencePolarity]] = None,
) -> UpdateResult:
    """Update beliefs from declared likelihoods without inventing evidentiary polarity.

    ``evidence_polarity`` is optional and must be explicitly supplied by the caller.
    Likelihoods, posterior ranking, or hypothesis state are never used to infer whether
    an observation supports or contradicts a hypothesis.
    """
    polarity = dict(evidence_polarity or {})
    if not hypotheses:
        return UpdateResult([], observed_outcome, evidence_strength, "INSUFFICIENT_EVIDENCE", "No hypotheses available.", polarity)

    strength = min(1.0, max(0.0, evidence_strength))
    raw = {}
    unknown = False
    for h in hypotheses:
        pred = h.predictions.get(observation_name, {})
        likelihood = pred.get(observed_outcome)
        if likelihood is None:
            unknown = True
            likelihood = 1.0
        likelihood = 1.0 + strength * (max(0.0, likelihood) - 1.0)
        raw[h.name] = max(0.0, h.probability) * likelihood

    if unknown:
        updated = [_copy_hypothesis(h) for h in hypotheses]
        return UpdateResult(
            updated,
            observed_outcome,
            strength,
            "PARTIAL_UPDATE",
            "At least one hypothesis lacked a prediction; no probability was changed because missing knowledge is not evidence.",
            polarity,
        )

    posterior = _normalize(raw)
    updated = [_copy_hypothesis(h, posterior[h.name]) for h in hypotheses]

    if len(updated) == 1:
        status = "UPDATED"
        explanation = "Posterior updated from the observed outcome."
    else:
        ranked = sorted(updated, key=lambda x: x.probability, reverse=True)
        status = "STRONGLY_SUPPORTED" if ranked[0].probability >= 0.9 else "UPDATED"
        explanation = "Posterior probabilities were updated using the observed outcome and declared likelihoods. Evidentiary polarity remains explicit and caller-supplied."
    return UpdateResult(updated, observed_outcome, strength, status, explanation, polarity)
