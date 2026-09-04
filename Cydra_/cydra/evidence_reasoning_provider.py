"""Conservative repository-evidence reasoning input provider.

This module converts already canonical, evidence-backed relationships into
*reasoning proposals*. It deliberately does not label vulnerabilities or
create authority. A proposal must still pass the existing controller and
planner before it can become an authorized observation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .invariants import InvariantCandidate
from .invariant_hypothesis_bridge import competing_hypotheses_from_candidates
from .planner import Hypothesis, Observation
from .reasoning_driver import ReasoningInputProvider, ReasoningInputs
from .security_reasoning import SecurityReasoningInputs, security_reasoning_inputs
from .system_model import Edge, SystemModel


@dataclass(frozen=True)
class EvidenceReasoningPolicy:
    """Bounded policy for deriving proposals from canonical evidence only."""

    max_hypotheses: int = 32
    max_observations: int = 32
    minimum_confidence: float = 0.50
    max_security_claims: int = 16

    def __post_init__(self) -> None:
        if self.max_hypotheses < 1 or self.max_observations < 1 or self.max_security_claims < 1:
            raise ValueError("proposal limits must be positive")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")


def _evidence_edges(model: SystemModel, minimum_confidence: float) -> tuple[Edge, ...]:
    return tuple(
        edge for edge in sorted(model.edges, key=lambda e: (e.source, e.relation, e.target))
        if edge.attributes.get("evidence_backed") is True
        and edge.attributes.get("candidate") is True
        and float(edge.attributes.get("confidence", 0.0)) >= minimum_confidence
    )


def _hypothesis_for_edge(edge: Edge) -> Hypothesis:
    """Create a falsifiable relationship hypothesis, not a vulnerability claim."""
    name = f"relationship:{edge.source}:{edge.relation}:{edge.target}"
    observation = f"verify:{edge.source}:{edge.relation}:{edge.target}"
    return Hypothesis(
        name=name,
        probability=min(1.0, max(0.0, float(edge.attributes.get("confidence", 0.0)))),
        predictions={observation: {"CONFIRMED": 0.85, "REFUTED": 0.15}},
    )


def _observation_for_edge(edge: Edge) -> Observation:
    observation = f"verify:{edge.source}:{edge.relation}:{edge.target}"
    return Observation(
        name=observation,
        outcomes=["CONFIRMED", "REFUTED"],
        cost=1.0,
        authorized=True,
        domain="target",
    )


class CanonicalEvidenceReasoningProvider:
    """Turn canonical evidence into bounded falsifiable reasoning proposals.

    The provider first derives security hypotheses from multi-edge semantic interactions,
    then fills the remaining budget with relationship hypotheses. A competing security
    hypothesis is an atomic pair, so it is emitted only when both hypothesis slots and
    an observation slot are available. It never consults benchmark truth, labels a
    historical issue, assigns finding severity, or creates execution authority.
    """

    def __init__(self, policy: EvidenceReasoningPolicy | None = None) -> None:
        self.policy = policy or EvidenceReasoningPolicy()

    def propose(self, model: SystemModel) -> ReasoningInputs:
        if not isinstance(model, SystemModel):
            raise TypeError("reasoning provider requires the canonical SystemModel")

        security_budget = min(
            self.policy.max_security_claims,
            self.policy.max_hypotheses // 2,
            self.policy.max_observations,
        )
        security = (
            security_reasoning_inputs(model, max_claims=security_budget)
            if security_budget > 0
            else SecurityReasoningInputs((), (), ())
        )
        hypotheses: list[Hypothesis] = list(security.hypotheses)
        observations: list[Observation] = list(security.observations)
        claims = list(security.security_claims)
        seen: set[str] = {hypothesis.name for hypothesis in hypotheses}

        if len(hypotheses) < self.policy.max_hypotheses and len(observations) < self.policy.max_observations:
            edges = _evidence_edges(model, self.policy.minimum_confidence)
            for edge in edges:
                hypothesis = _hypothesis_for_edge(edge)
                observation = _observation_for_edge(edge)
                if hypothesis.name in seen:
                    continue
                seen.add(hypothesis.name)
                hypotheses.append(hypothesis)
                observations.append(observation)
                if len(hypotheses) >= self.policy.max_hypotheses or len(observations) >= self.policy.max_observations:
                    break

        if claims:
            return SecurityReasoningInputs(tuple(hypotheses), tuple(observations), tuple(claims))
        return ReasoningInputs.from_sequences(hypotheses, observations)


def proposals_from_invariant_candidates(
    candidates: Iterable[InvariantCandidate],
    *,
    policy: EvidenceReasoningPolicy | None = None,
) -> ReasoningInputs:
    """Adapt candidates into bounded, explicitly competing reasoning inputs.

    Candidates are not verified facts. Each admitted candidate consumes an atomic
    pair of hypotheses (holds/violated) and one discriminating observation. The
    pair is kept intact so a budget can never silently discard its complement.
    """
    active = policy or EvidenceReasoningPolicy()
    eligible = [
        candidate for candidate in candidates
        if candidate.confidence >= active.minimum_confidence
    ]
    max_candidates = min(
        len(eligible),
        active.max_hypotheses // 2,
        active.max_observations,
    )
    if max_candidates <= 0:
        return ReasoningInputs.from_sequences([], [])
    hypotheses, observations = competing_hypotheses_from_candidates(
        eligible[:max_candidates],
    )
    return ReasoningInputs.from_sequences(hypotheses, observations)
