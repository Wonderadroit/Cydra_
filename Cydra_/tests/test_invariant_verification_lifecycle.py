from cydra.invariants import (
    CandidateVerification,
    InvariantCandidate,
    VerificationEvidence,
    VerificationRole,
    VerificationState,
    infer_invariants_from_metadata,
    verify_candidate,
)
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def _candidate(candidate_id="candidate:one"):
    return InvariantCandidate(candidate_id, "system preserves balance", ("ast:42",), 0.8, 1)


def test_metadata_inference_returns_registry():
    registry = infer_invariants_from_metadata([
        {
            "invariant_id": "inv:balance",
            "statement": "balance remains solvent",
            "source_id": "recon:1",
            "confidence": "0.7",
        }
    ])
    invariant = registry.get("inv:balance")
    assert invariant is not None
    assert invariant.status.value == "inferred"
    assert invariant.confidence == 0.7


def test_candidate_verification_rejects_invalid_manual_state():
    try:
        CandidateVerification(
            "candidate:one",
            VerificationState.SUPPORTED,
            ("support",),
            (),
            (),
            0.8,
        )
    except ValueError as exc:
        assert "supporting evidence" in str(exc)
    else:
        assert False


def test_candidate_verification_rejects_out_of_range_confidence():
    try:
        VerificationEvidence("support", VerificationRole.SUPPORTS, 1.1)
    except ValueError as exc:
        assert "confidence" in str(exc)
    else:
        assert False


def test_unresolved_verification_is_preserved_when_candidates_are_rederived():
    graph = ReasoningGraph()
    candidate_id = "candidate:one"
    graph.model.add_node(Node(candidate_id, "invariant", "system preserves balance", {
        "verification_state": "unresolved",
        "status": "unresolved",
        "verified": False,
    }))
    graph.model.add_node(Node("evidence:neutral", "evidence", "inconclusive observation"))

    verification = verify_candidate(
        _candidate(candidate_id),
        [VerificationEvidence("neutral", VerificationRole.NEUTRAL, 0.5, "inconclusive")],
    )
    graph.record_invariant_verification(verification)
    graph.record_invariant_candidates([_candidate(candidate_id)])

    node = graph.model.nodes[candidate_id]
    assert node.attributes["verification_state"] == "unresolved"
    assert node.attributes["status"] == "unresolved"
    assert node.attributes["verified"] is False


def test_verification_state_invariants_are_distinct():
    supported = verify_candidate(
        _candidate("candidate:supported"),
        [VerificationEvidence("s1", VerificationRole.SUPPORTS, 0.9)],
    )
    contradicted = verify_candidate(
        _candidate("candidate:contradicted"),
        [VerificationEvidence("c1", VerificationRole.CONTRADICTS, 0.2)],
    )
    unresolved = verify_candidate(
        _candidate("candidate:unresolved"),
        [VerificationEvidence("n1", VerificationRole.NEUTRAL, 0.9)],
    )

    assert supported.state == VerificationState.SUPPORTED
    assert contradicted.state == VerificationState.CONTRADICTED
    assert unresolved.state == VerificationState.UNRESOLVED
