from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING
import math
import uuid

from .execution_request import ExecutionRequest
from .hypotheses import HypothesisState

if TYPE_CHECKING:
    from .knowledge_base import KnowledgeBase
    from .learning import LearningStore


@dataclass(frozen=True)
class LearningContext:
    """Immutable context binding reusable learning to one issued investigation envelope."""

    investigation_id: str
    authority_fingerprint: str
    lease_generation: int
    learning_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("investigation_id", "authority_fingerprint", "learning_fingerprint"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.lease_generation < 0:
            raise ValueError("lease_generation must be non-negative")

    def validate_store(self, learning_store: "LearningStore") -> None:
        if learning_store.authority_independent_fingerprint() != self.learning_fingerprint:
            raise RuntimeError("learning store changed after the investigation learning context was issued")


@dataclass(frozen=True)
class KnowledgeContext:
    """Immutable snapshot binding the reasoning knowledge basis to authority."""

    investigation_id: str
    authority_fingerprint: str
    lease_generation: int
    knowledge_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("investigation_id", "authority_fingerprint", "knowledge_fingerprint"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.lease_generation < 0:
            raise ValueError("lease_generation must be non-negative")

    def validate_store(self, knowledge_base: "KnowledgeBase") -> None:
        if knowledge_base.authority_independent_fingerprint() != self.knowledge_fingerprint:
            raise RuntimeError("knowledge base changed after the investigation knowledge context was issued")


@dataclass(frozen=True)
class Hypothesis:
    name: str
    probability: float
    predictions: Dict[str, Dict[str, float]]
    state: HypothesisState = HypothesisState.UNRESOLVED

    @property
    def hypothesis_id(self) -> str:
        return f"hypothesis:{self.name}"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0 and 1")


@dataclass(frozen=True)
class Observation:
    name: str
    outcomes: List[str]
    cost: float
    authorized: bool = True
    execution_id: str = ""
    execution_request_digest: str = ""
    execution_request: Optional[ExecutionRequest] = None
    domain: str = "target"
    discriminates_hypothesis_ids: tuple[str, ...] = ()
    target_ids: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.execution_id and not self.execution_id.strip():
            raise ValueError("execution_id must not be whitespace")
        if self.execution_request_digest and not self.execution_request_digest.strip():
            raise ValueError("execution_request_digest must not be whitespace")
        if self.domain not in {"target", "meta"}:
            raise ValueError("observation domain must be 'target' or 'meta'")
        pair = tuple(self.discriminates_hypothesis_ids)
        if len(pair) not in {0, 2}:
            raise ValueError("discriminating observation must bind exactly two hypothesis IDs")
        if len(pair) == 2 and (not all(isinstance(item, str) and item.strip() for item in pair) or pair[0] == pair[1]):
            raise ValueError("discriminating observation requires two distinct non-empty hypothesis IDs")
        object.__setattr__(self, "discriminates_hypothesis_ids", pair)
        targets = tuple(self.target_ids)
        if any(not isinstance(item, str) or not item.strip() for item in targets):
            raise ValueError("observation target IDs must be non-empty strings")
        object.__setattr__(self, "target_ids", targets)
        if not self.execution_id:
            object.__setattr__(self, "execution_id", f"execution:{uuid.uuid4()}")
        if self.execution_request is not None:
            if self.execution_request.execution_id != self.execution_id:
                raise ValueError("execution request identity does not match observation execution_id")
            if self.execution_request_digest and self.execution_request.digest != self.execution_request_digest:
                raise ValueError("execution request digest does not match execution_request")
            if not self.execution_request_digest:
                object.__setattr__(self, "execution_request_digest", self.execution_request.digest)

    @property
    def planned_execution_id(self) -> str:
        return self.execution_id

    @property
    def planned_request_digest(self) -> str:
        return self.execution_request_digest

    @property
    def hypothesis_pair(self) -> tuple[str, ...]:
        """Exact canonical hypothesis identities this observation is intended to discriminate."""
        return self.discriminates_hypothesis_ids


@dataclass(frozen=True)
class Plan:
    observation: str
    expected_information_gain: float
    utility: float
    rationale: str
    learning_ids: tuple[str, ...] = ()
    learning_context_fingerprint: str = ""
    investigation_id: str = ""
    knowledge_ids: tuple[str, ...] = ()
    knowledge_context_fingerprint: str = ""
    discriminates_hypothesis_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.observation, Observation):
            object.__setattr__(self, "observation", self.observation.name)
        elif not isinstance(self.observation, str) or not self.observation.strip():
            raise ValueError("observation must be a non-empty observation name")
        pair = tuple(self.discriminates_hypothesis_ids)
        if len(pair) not in {0, 2}:
            raise ValueError("plan hypothesis binding must contain exactly two hypothesis IDs")
        if len(pair) == 2 and (not all(isinstance(item, str) and item.strip() for item in pair) or pair[0] == pair[1]):
            raise ValueError("plan hypothesis binding requires two distinct non-empty hypothesis IDs")
        object.__setattr__(self, "discriminates_hypothesis_ids", pair)


def _entropy(probs):
    return -sum(p * math.log2(p) for p in probs if p > 0)


def _normalize(hypotheses):
    total = sum(max(0.0, h.probability) for h in hypotheses)
    if total <= 0:
        return {h.name: 0.0 for h in hypotheses}
    return {h.name: max(0.0, h.probability) / total for h in hypotheses}


def information_gain(hypotheses: List[Hypothesis], observation: Observation) -> Optional[float]:
    if not hypotheses or not observation.authorized or observation.cost <= 0:
        return None

    # A semantically bound observation is intended to distinguish an exact
    # hypothesis set, not every unrelated hypothesis currently in the round.
    # Restricting the entropy calculation to that explicit pair prevents
    # unrelated reasoning proposals from diluting the value of an invariant
    # verification check. The pair has already been validated by the caller.
    if observation.discriminates_hypothesis_ids:
        bound = set(observation.discriminates_hypothesis_ids)
        hypotheses = [h for h in hypotheses if h.hypothesis_id in bound]
        if len(hypotheses) != len(bound):
            return None

    priors = _normalize(hypotheses)
    prior_h = _entropy(priors.values())
    expected = 0.0
    known = False
    for outcome in observation.outcomes:
        likelihoods = {}
        for h in hypotheses:
            pred = h.predictions.get(observation.name, {})
            if outcome in pred:
                likelihoods[h.name] = max(0.0, pred[outcome])
        if not likelihoods:
            continue
        known = True
        p_out = sum(priors[h.name] * likelihoods.get(h.name, 0.0) for h in hypotheses)
        if p_out <= 0:
            continue
        posterior = {n: (priors[n] * likelihoods.get(n, 0.0)) / p_out for n in priors}
        expected += p_out * _entropy(posterior.values())
    if not known:
        return None
    return max(0.0, prior_h - expected)


def _learning_for_observation(observation: Observation, learning_store: Optional["LearningStore"]):
    if learning_store is None:
        return ()
    return learning_store.apply_candidates("observation_pattern", observation.name)


def _knowledge_for_observation(observation: Observation, knowledge_base: Optional["KnowledgeBase"]):
    if knowledge_base is None:
        return ()
    return knowledge_base.matching("observation_pattern", observation.name)


def _validate_hypothesis_binding(hypotheses: List[Hypothesis], observation: Observation) -> None:
    pair = observation.discriminates_hypothesis_ids
    if not pair:
        return
    supplied = {hypothesis.hypothesis_id for hypothesis in hypotheses}
    missing = sorted(set(pair) - supplied)
    if missing:
        raise ValueError(f"discriminating observation references unknown hypotheses: {missing}")


def choose_next_observation(
    hypotheses: List[Hypothesis],
    observations: List[Observation],
    learning_store: Optional["LearningStore"] = None,
    learning_context: Optional[LearningContext] = None,
    knowledge_base: Optional["KnowledgeBase"] = None,
    knowledge_context: Optional[KnowledgeContext] = None,
) -> Optional[Plan]:
    if learning_store is not None and learning_context is None:
        raise ValueError("learning-aware planning requires an immutable investigation context")
    if learning_context is not None:
        if learning_store is None:
            raise ValueError("learning context requires a learning store")
        learning_context.validate_store(learning_store)
    if knowledge_base is not None and knowledge_context is None:
        raise ValueError("knowledge-aware planning requires an immutable knowledge context")
    if knowledge_context is not None:
        if knowledge_base is None:
            raise ValueError("knowledge context requires a knowledge base")
        knowledge_context.validate_store(knowledge_base)

    candidates = []
    for obs in observations:
        _validate_hypothesis_binding(hypotheses, obs)
        gain = information_gain(hypotheses, obs)
        if gain is None:
            continue
        learning = _learning_for_observation(obs, learning_store)
        knowledge = _knowledge_for_observation(obs, knowledge_base)
        learning_bonus = min(0.25, 0.05 * len(learning))
        knowledge_bonus = min(0.20, 0.04 * len(knowledge))
        candidates.append(((gain / obs.cost) + learning_bonus + knowledge_bonus, gain, obs, learning, knowledge))
    if not candidates:
        return None
    # Use a deterministic total ordering so equal-value observations do not
    # depend on provider iteration order. This is especially important for
    # reproducible invariant-driven investigations.
    utility, gain, obs, learning, knowledge = sorted(
        candidates,
        key=lambda x: (-x[0], -x[1], x[2].name),
    )[0]
    rationale = "Selected by expected information gain per unit cost among authorized observations."
    if obs.discriminates_hypothesis_ids:
        rationale += " Explicitly bound to the supplied competing hypothesis pair."
    if learning:
        rationale += " Reused bounded finding-derived observation learning without changing authority."
    if knowledge:
        rationale += " Applied bounded knowledge-base pattern relevance without changing authority."
    return Plan(
        obs.name,
        round(gain, 6),
        round(utility, 6),
        rationale,
        learning_ids=tuple(record.learning_id for record in learning),
        learning_context_fingerprint=learning_context.learning_fingerprint if learning_context else "",
        investigation_id=learning_context.investigation_id if learning_context else "",
        knowledge_ids=tuple(record.knowledge_id for record in knowledge),
        knowledge_context_fingerprint=knowledge_context.knowledge_fingerprint if knowledge_context else "",
        discriminates_hypothesis_ids=obs.discriminates_hypothesis_ids,
    )
