"""Translate verified invariant candidates into explicit, testable hypotheses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .invariants import InvariantCandidate, VerificationState
from .planner import Hypothesis, Observation
from .system_model import Edge, Node, SystemModel


@dataclass(frozen=True)
class InvariantHypothesis:
    hypothesis_id: str
    invariant_id: str
    statement: str
    confidence: float


def _canonical_verified_invariant(model: SystemModel, candidate: InvariantCandidate) -> Node | None:
    node = model.nodes.get(candidate.candidate_id)
    if node is None or node.kind != "invariant" or node.label != candidate.statement: return None
    if node.attributes.get("verification_state") != VerificationState.SUPPORTED.value: return None
    supporting_ids = tuple(node.attributes.get("supporting_evidence_ids", ()))
    if not supporting_ids: return None
    verified_edges = {edge.target for edge in model.edges if edge.source == candidate.candidate_id and edge.relation == "verified_by" and edge.target in model.nodes and model.nodes[edge.target].kind == "evidence"}
    expected_edges = {e if e.startswith("evidence:") else f"evidence:{e}" for e in supporting_ids}
    if not expected_edges.issubset(verified_edges): return None
    return node


def hypotheses_from_verified_invariants(model: SystemModel, candidates: list[InvariantCandidate]) -> list[InvariantHypothesis]:
    results = []
    for candidate in candidates:
        node = _canonical_verified_invariant(model, candidate)
        if node is not None:
            results.append(InvariantHypothesis(f"hypothesis:{candidate.candidate_id}", candidate.candidate_id, f"Violation of invariant: {candidate.statement}", float(node.attributes.get("verification_confidence", candidate.confidence))))
    return results


def planner_hypotheses_from_verified_invariants(model: SystemModel, candidates: list[InvariantCandidate], explicit_hypotheses: Mapping[str, Hypothesis]) -> list[tuple[InvariantHypothesis, Hypothesis]]:
    verified = hypotheses_from_verified_invariants(model, candidates)
    return [(InvariantHypothesis(f"hypothesis:{hypothesis.name}", item.invariant_id, item.statement, item.confidence), hypothesis) for item in verified if (hypothesis := explicit_hypotheses.get(item.invariant_id)) is not None]


def competing_hypotheses_from_candidates(
    candidates: list[InvariantCandidate],
    *,
    max_candidates: int | None = None,
) -> tuple[list[Hypothesis], list[Observation]]:
    """Turn candidate invariants into bounded competing, falsifiable hypotheses.

    A candidate invariant is not treated as a verified fact.  Each candidate
    produces exactly two hypotheses: the invariant holds and the invariant is
    violated.  The paired observation is explicitly bound to both identities,
    so downstream planning can seek an observation that distinguishes them.
    """
    if max_candidates is not None and max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    active = candidates if max_candidates is None else candidates[:max_candidates]
    hypotheses: list[Hypothesis] = []
    observations: list[Observation] = []
    for candidate in active:
        base = candidate.candidate_id
        holds_name = f"invariant-holds:{base}"
        violation_name = f"invariant-violated:{base}"
        observation_name = f"verify-invariant:{base}"
        # Candidate confidence measures evidence quality, not the probability that
        # the invariant is true. Keep the competing hypotheses symmetric so the
        # planner is actually asked to verify the candidate instead of inheriting
        # a truth claim from discovery confidence.
        holds = Hypothesis(
            name=holds_name,
            probability=0.5,
            predictions={observation_name: {
                "INVARIANT_PRESERVED": 0.85,
                "INVARIANT_VIOLATED": 0.10,
                "INCONCLUSIVE": 0.05,
            }},
        )
        violated = Hypothesis(
            name=violation_name,
            probability=0.5,
            predictions={observation_name: {
                "INVARIANT_PRESERVED": 0.10,
                "INVARIANT_VIOLATED": 0.85,
                "INCONCLUSIVE": 0.05,
            }},
        )
        observation = Observation(
            name=observation_name,
            outcomes=["INVARIANT_PRESERVED", "INVARIANT_VIOLATED", "INCONCLUSIVE"],
            cost=1.0,
            authorized=True,
            domain="target",
            discriminates_hypothesis_ids=(holds.hypothesis_id, violated.hypothesis_id),
            target_ids=tuple(
                value for key in (
                    "source_function", "written_state", "predicate_node",
                    "ast_node_id", "precondition_relation",
                )
                for value in (candidate.metadata.get(key),)
                if isinstance(value, str) and value
            ),
            rationale=(
                "Verify the discovered invariant at its compiler-backed source and "
                "state-transition target; discovery confidence describes evidence "
                "quality, not truth."
            ),
        )
        hypotheses.extend((holds, violated))
        observations.append(observation)
    return hypotheses, observations


def persist_invariant_hypotheses(model: SystemModel, hypotheses: list[InvariantHypothesis]) -> None:
    for hypothesis in hypotheses:
        invariant = model.nodes.get(hypothesis.invariant_id)
        if invariant is None or invariant.kind != "invariant": raise KeyError(f"invariant node missing: {hypothesis.invariant_id}")
        if invariant.attributes.get("verification_state") != VerificationState.SUPPORTED.value: raise ValueError("invariant must be explicitly supported before hypothesis bridging")
        expected_statement = f"Violation of invariant: {invariant.label}"
        if hypothesis.statement != expected_statement: raise ValueError("hypothesis statement is not bound to the canonical invariant")
        supporting_ids = tuple(invariant.attributes.get("supporting_evidence_ids", ()))
        if not supporting_ids: raise ValueError("supported invariant is missing supporting evidence IDs")
        verified_edges = {edge.target for edge in model.edges if edge.source == hypothesis.invariant_id and edge.relation == "verified_by"}
        expected_edges = {e if e.startswith("evidence:") else f"evidence:{e}" for e in supporting_ids}
        if not expected_edges.issubset(verified_edges): raise ValueError("supported invariant is missing explicit verification evidence edges")
        node = model.nodes.get(hypothesis.hypothesis_id)
        if node is None:
            model.add_node(Node(hypothesis.hypothesis_id, "hypothesis", hypothesis.statement, {"invariant_id": hypothesis.invariant_id, "confidence": hypothesis.confidence, "provenance": "verified_invariant"}))
        elif node.kind != "hypothesis":
            raise ValueError(f"hypothesis ID conflicts with non-hypothesis node: {hypothesis.hypothesis_id}")
        elif node.label != hypothesis.statement:
            # A planner-synchronized hypothesis already carries its own human
            # statement. It may be enriched by the verified invariant bridge,
            # but an arbitrary pre-existing node must never be overwritten.
            planner_shape = {"probability", "predictions", "state", "subject_id"}
            if not planner_shape.issubset(node.attributes): raise ValueError("existing hypothesis label conflicts with canonical invariant bridge")
            model.update_node_attributes(node.node_id, {"invariant_id": hypothesis.invariant_id, "invariant_statement": hypothesis.statement, "invariant_confidence": hypothesis.confidence, "provenance": "verified_invariant"})
        else:
            model.update_node_attributes(node.node_id, {"invariant_id": hypothesis.invariant_id, "invariant_statement": hypothesis.statement, "invariant_confidence": hypothesis.confidence, "provenance": "verified_invariant"})
        model.add_edge(Edge(hypothesis.invariant_id, "informs", hypothesis.hypothesis_id, {"provenance": "verified_invariant", "rationale": "supported invariant bridge"}))
