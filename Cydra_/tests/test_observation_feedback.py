import pytest

from cydra.hypotheses import Hypothesis, HypothesisState
from cydra.invariants import CandidateVerification, VerificationEvidence, VerificationRole, VerificationState
from cydra.observation_feedback import apply_observation_feedback
from cydra.observation_outcomes import ObservationOutcome


def test_feedback_uses_external_outcome_identity():
    outcome = ObservationOutcome("check", "out-1", "yes", "authorized test", 0.9)
    verification = CandidateVerification(
        "candidate:one",
        VerificationState.SUPPORTED,
        ("out-1",),
        ("out-1",),
        (),
        0.9,
    )
    evidence = [VerificationEvidence("out-1", VerificationRole.SUPPORTS, 0.9, "Observed expected behavior")]
    hypothesis = Hypothesis("hypothesis:one", "candidate claim", 0.5, HypothesisState.UNRESOLVED, {"check": {"yes": 0.9}})

    updated = apply_observation_feedback(outcome, verification, [hypothesis], evidence)

    assert len(updated) == 1
    assert updated[0].hypothesis_id == hypothesis.hypothesis_id
    assert updated[0].belief > hypothesis.belief
    assert updated[0].state is HypothesisState.SUPPORTED


def test_feedback_rejects_unrelated_outcome_identity():
    outcome = ObservationOutcome("check", "out-1", "yes", "authorized test")
    verification = CandidateVerification(
        "candidate:one",
        VerificationState.SUPPORTED,
        ("out-2",),
        ("out-2",),
        (),
        0.9,
    )

    with pytest.raises(ValueError, match="not part of verification"):
        apply_observation_feedback(outcome, verification, [], [])
