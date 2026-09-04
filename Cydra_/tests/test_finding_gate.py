from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding


def test_fully_verified_candidate_is_ready():
    result = evaluate_finding(FindingCandidate(True, False, True, True, True, True))
    assert result.decision == GateDecision.READY


def test_out_of_scope_is_blocked():
    result = evaluate_finding(FindingCandidate(False, False, True, True, True, True))
    assert result.decision == GateDecision.BLOCKED


def test_known_issue_is_blocked():
    result = evaluate_finding(FindingCandidate(True, True, True, True, True, True))
    assert result.decision == GateDecision.BLOCKED


def test_unresolved_hypothesis_is_not_a_finding():
    result = evaluate_finding(FindingCandidate(True, False, True, True, True, True, False))
    assert result.decision == GateDecision.UNRESOLVED


def test_missing_verification_blocks_promotion():
    result = evaluate_finding(FindingCandidate(True, False, True, True, False, True))
    assert result.decision == GateDecision.BLOCKED


def test_missing_evidence_reproducibility_and_impact_are_reported():
    result = evaluate_finding(FindingCandidate(True, False, False, False, True, False))
    assert result.decision == GateDecision.BLOCKED
    assert set(result.reasons) == {"evidence", "reproducibility", "impact assessment"}
