"""Explicit contradiction detection over CYDRA's persistent reasoning model.

Detection is conservative: contradictions are emitted only when the model contains
explicit opposing states attached to the same declared subject, explicit opposing
reasoning states, or explicitly classified support/contradiction evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .planner import Hypothesis, HypothesisState
from .invariants import CandidateVerification, VerificationState
from .system_model import SystemModel


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    subject_id: str
    left_state: str
    right_state: str
    evidence_ids: tuple[str, ...]
    rationale: str


def detect_model_contradictions(model: SystemModel) -> tuple[Contradiction, ...]:
    """Find explicit opposing state claims attached to the same declared subject.

    A node's own ``state`` is not enough to establish a contradiction. Multiple
    independent nodes must explicitly declare the same ``subject_id`` before their
    opposing states are compared. This prevents unrelated nodes from becoming a
    false contradiction merely because they use similar state labels.
    """
    states: dict[str, list[tuple[str, str]]] = {}
    for node in model.nodes.values():
        state = node.attributes.get("state")
        subject_id = node.attributes.get("subject_id")
        if state is None or subject_id is None:
            continue
        states.setdefault(str(subject_id), []).append((str(state), node.node_id))

    findings: list[Contradiction] = []
    opposing_pairs = ({"supported", "contradicted"}, {"asserted", "contradicted"})
    for subject_id, values in states.items():
        by_state: dict[str, list[str]] = {}
        for state, node_id in values:
            by_state.setdefault(state, []).append(node_id)
        unique = sorted(by_state)
        for index, left in enumerate(unique):
            for right in unique[index + 1:]:
                if {left, right} not in opposing_pairs:
                    continue
                cid = f"contradiction:{subject_id}:{left}:{right}"
                findings.append(Contradiction(
                    cid,
                    subject_id,
                    left,
                    right,
                    (),
                    "explicit opposing states coexist for the same declared subject",
                ))
    return tuple(sorted(findings, key=lambda c: c.contradiction_id))


def detect_reasoning_contradictions(
    hypotheses: Iterable[Hypothesis], verifications: Iterable[CandidateVerification]
) -> tuple[Contradiction, ...]:
    """Detect explicit disagreement between hypothesis and candidate verification state."""
    by_id = {h.hypothesis_id: h for h in hypotheses}
    findings: list[Contradiction] = []
    for verification in verifications:
        hypothesis = by_id.get(verification.candidate_id)
        if hypothesis is None:
            continue
        conflict = (
            hypothesis.state == HypothesisState.SUPPORTED and verification.state == VerificationState.CONTRADICTED
        ) or (
            hypothesis.state == HypothesisState.CONTRADICTED and verification.state == VerificationState.SUPPORTED
        )
        if conflict:
            findings.append(Contradiction(
                f"contradiction:{hypothesis.hypothesis_id}:{verification.candidate_id}",
                hypothesis.hypothesis_id,
                hypothesis.state.value,
                verification.state.value,
                verification.evidence_ids,
                "hypothesis state conflicts with explicit candidate verification",
            ))
    return tuple(sorted(findings, key=lambda c: c.contradiction_id))
