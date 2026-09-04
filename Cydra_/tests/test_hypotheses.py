from cydra.hypotheses import Hypothesis, HypothesisState, update_hypothesis
from cydra.invariants import CandidateVerification, VerificationEvidence, VerificationRole, VerificationState


def verification(state, *evidence_ids):
    return CandidateVerification("candidate:1", state, evidence_ids, evidence_ids if state == VerificationState.SUPPORTED else (), evidence_ids if state == VerificationState.CONTRADICTED else (), 0.8)


def test_support_increases_belief_without_certainty():
    h = Hypothesis("h:1", "balance is written by deposit", 0.4)
    evidence = [VerificationEvidence("obs:1", VerificationRole.SUPPORTS, 0.8)]
    updated, audit = update_hypothesis(h, verification(VerificationState.SUPPORTED, "obs:1"), evidence)
    assert updated.belief > h.belief
    assert updated.belief < 1.0
    assert updated.state == HypothesisState.SUPPORTED
    assert audit.prior_belief == 0.4
    assert audit.evidence_ids == ("obs:1",)


def test_contradiction_decreases_belief():
    h = Hypothesis("h:1", "balance is written by deposit", 0.8)
    evidence = [VerificationEvidence("obs:2", VerificationRole.CONTRADICTS, 0.9)]
    updated, _ = update_hypothesis(h, verification(VerificationState.CONTRADICTED, "obs:2"), evidence)
    assert updated.belief < h.belief
    assert updated.belief > 0.0
    assert updated.state == HypothesisState.CONTRADICTED


def test_unresolved_preserves_belief():
    h = Hypothesis("h:1", "balance is written by deposit", 0.6)
    evidence = [VerificationEvidence("obs:3", VerificationRole.NEUTRAL, 1.0)]
    updated, audit = update_hypothesis(h, verification(VerificationState.UNRESOLVED, "obs:3"), evidence)
    assert updated.belief == h.belief
    assert updated.state == HypothesisState.UNRESOLVED
    assert "unchanged" in audit.rationale


def test_update_never_promotes_to_invariant():
    h = Hypothesis("h:1", "balance is written by deposit", 0.99)
    evidence = [VerificationEvidence("obs:4", VerificationRole.SUPPORTS, 1.0)]
    updated, _ = update_hypothesis(h, verification(VerificationState.SUPPORTED, "obs:4"), evidence)
    assert isinstance(updated, Hypothesis)
    assert updated.belief < 1.0
