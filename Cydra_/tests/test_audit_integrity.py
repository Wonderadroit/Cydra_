from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_graph import ReasoningGraph


def _graph_with_history():
    graph = ReasoningGraph()
    hypothesis = Hypothesis("H", 1.0, {"check": {"yes": 1.0}})
    observation = Observation("check", ["yes"], 1.0, True)
    plan = Plan("check", 0.0, 0.0, "explicit audit test")
    graph.record_plan(plan, [hypothesis], observation)
    return graph


def test_audit_events_form_a_hash_chain():
    graph = _graph_with_history()
    assert graph.history
    assert graph.verify_history_integrity() == []
    for index, event in enumerate(graph.history):
        assert event["sequence"] == index
        assert event["event_hash"]
        assert event["previous_hash"] == ("GENESIS" if index == 0 else graph.history[index - 1]["event_hash"])


def test_audit_tampering_is_detected_without_mutation():
    graph = _graph_with_history()
    original_hash = graph.history[0]["event_hash"]
    graph.history[0]["type"] = "TAMPERED"
    errors = graph.verify_history_integrity()
    assert any("hash mismatch" in error for error in errors)
    assert graph.history[0]["type"] == "TAMPERED"
    assert graph.history[0]["event_hash"] == original_hash


def test_audit_reordering_is_detected():
    graph = _graph_with_history()
    graph.add_hypotheses([Hypothesis("H2", 0.5, {"check": {"yes": 0.5}})])
    graph.history[0], graph.history[1] = graph.history[1], graph.history[0]
    errors = graph.verify_history_integrity()
    assert any("sequence mismatch" in error for error in errors)
    assert any("previous-hash mismatch" in error for error in errors)


def test_validate_includes_audit_integrity():
    graph = _graph_with_history()
    assert graph.validate() == []
    graph.history[0]["timestamp"] = -1
    assert any("audit event hash mismatch" in error for error in graph.validate())
