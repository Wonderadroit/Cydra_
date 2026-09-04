from cydra.invariants import (
    CandidateVerification,
    InvariantCandidate,
    VerificationEvidence,
    VerificationRole,
    VerificationState,
    verify_candidate,
)


def candidate():
    return InvariantCandidate("candidate:1", "function writes balance", ("ast:30",), 0.9, 1)


def test_supporting_evidence_marks_candidate_supported():
    result = verify_candidate(candidate(), [
        VerificationEvidence("test:1", VerificationRole.SUPPORTS, 0.8, "observed write")
    ])
    assert isinstance(result, CandidateVerification)
    assert result.state == VerificationState.SUPPORTED
    assert result.supporting_ids == ("test:1",)
    assert result.contradicting_ids == ()
    assert result.confidence == 0.8


def test_contradiction_dominates_support():
    result = verify_candidate(candidate(), [
        VerificationEvidence("test:support", VerificationRole.SUPPORTS, 0.9),
        VerificationEvidence("test:contra", VerificationRole.CONTRADICTS, 0.7),
    ])
    assert result.state == VerificationState.CONTRADICTED
    assert result.supporting_ids == ("test:support",)
    assert result.contradicting_ids == ("test:contra",)


def test_no_relevant_evidence_remains_unresolved():
    result = verify_candidate(candidate(), [
        VerificationEvidence("test:neutral", VerificationRole.NEUTRAL, 1.0)
    ])
    assert result.state == VerificationState.UNRESOLVED
    assert result.confidence == 0.0


def test_verification_does_not_promote_candidate_to_invariant():
    result = verify_candidate(candidate(), [
        VerificationEvidence("test:1", VerificationRole.SUPPORTS, 1.0)
    ])
    assert result.state == VerificationState.SUPPORTED
    assert result.candidate_id == "candidate:1"
