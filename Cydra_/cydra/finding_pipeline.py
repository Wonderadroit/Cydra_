from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .finding import Finding
from .finding_gate import FindingCandidate, GateDecision, evaluate_finding, evaluate_finding_graph
from .learning import FindingLearningContribution, LearningError, LearningStore
from .learning_persistence import persist_verified_finding_learning


@dataclass(frozen=True)
class FindingPipelineResult:
    decision: GateDecision
    finding: Finding | None
    reasons: tuple[str, ...] = ()
    learning_ids: tuple[str, ...] = ()


def promote_candidate(
    candidate: FindingCandidate,
    finding: Finding,
    graph=None,
    *,
    learning_store: Optional[LearningStore] = None,
    learning: Optional[FindingLearningContribution] = None,
) -> FindingPipelineResult:
    """Promote a verified finding and commit its explicit learning when requested.

    In the canonical graph path, learning is persisted only after the finding gate and
    is bound to the persisted finding node. Without a graph, the bounded LearningStore
    remains available for callers that own persistence outside the reasoning graph.
    """
    result = evaluate_finding_graph(graph, candidate, finding) if graph is not None else evaluate_finding(candidate)
    if result.decision != GateDecision.READY:
        return FindingPipelineResult(result.decision, None, tuple(result.reasons))

    if learning_store is None and learning is not None:
        return FindingPipelineResult(
            GateDecision.BLOCKED,
            None,
            ("learning contribution requires a learning store",),
        )
    if learning_store is not None and learning is None:
        return FindingPipelineResult(
            GateDecision.BLOCKED,
            None,
            ("verified finding requires explicit learning contributions",),
        )

    learning_ids: tuple[str, ...] = ()
    if learning_store is not None and learning is not None:
        try:
            if graph is not None:
                learning_ids = persist_verified_finding_learning(graph, learning_store, finding, learning)
            else:
                learning_ids = learning_store.learn_verified_finding(finding, learning)
        except (LearningError, KeyError, TypeError, ValueError) as exc:
            return FindingPipelineResult(
                GateDecision.BLOCKED,
                None,
                (f"finding learning persistence failed: {exc}",),
            )

    return FindingPipelineResult(GateDecision.READY, finding, learning_ids=learning_ids)


def promote_verified_candidate(
    candidate: FindingCandidate,
    finding: Finding,
    learning_store: LearningStore,
    learning: FindingLearningContribution,
    graph=None,
) -> FindingPipelineResult:
    """Canonical lifecycle entry point: verified finding plus required learning."""
    return promote_candidate(
        candidate,
        finding,
        graph,
        learning_store=learning_store,
        learning=learning,
    )
