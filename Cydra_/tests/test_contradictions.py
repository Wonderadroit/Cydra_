from cydra.contradictions import detect_model_contradictions, detect_reasoning_contradictions
from cydra.planner import Hypothesis, HypothesisState
from cydra.invariants import CandidateVerification, VerificationState
from cydra.system_model import Node, SystemModel


def test_unrelated_model_states_are_not_a_contradiction():
    model = SystemModel()
    model.add_node(Node("x", "hypothesis", "x", {"state": "supported"}))
    model.add_node(Node("x:contradiction", "evidence", "x contradiction", {"state": "contradicted"}))
    assert detect_model_contradictions(model) == ()


def test_detects_explicit_model_state_conflict_for_same_subject():
    model = SystemModel()
    model.add_node(Node("claim:a", "hypothesis", "claim a", {
        "state": "supported", "subject_id": "subject:a"
    }))
    model.add_node(Node("claim:a:counter", "evidence", "counter evidence", {
        "state": "contradicted", "subject_id": "subject:a"
    }))

    result = detect_model_contradictions(model)
    assert len(result) == 1
    assert result[0].subject_id == "subject:a"
    assert {result[0].left_state, result[0].right_state} == {"supported", "contradicted"}


def test_detects_hypothesis_verification_conflict():
    hypothesis = Hypothesis("h1", 0.8, {}, HypothesisState.SUPPORTED)
    verification = CandidateVerification("hypothesis:h1", VerificationState.CONTRADICTED, ("e1",), (), ("e1",), 0.9)
    result = detect_reasoning_contradictions((hypothesis,), (verification,))
    assert len(result) == 1
    assert result[0].evidence_ids == ("e1",)


def test_unresolved_does_not_count_as_contradiction():
    hypothesis = Hypothesis("h1", 0.5, {}, HypothesisState.SUPPORTED)
    verification = CandidateVerification("hypothesis:h1", VerificationState.UNRESOLVED, (), (), (), 0.0)
    assert detect_reasoning_contradictions((hypothesis,), (verification,)) == ()
