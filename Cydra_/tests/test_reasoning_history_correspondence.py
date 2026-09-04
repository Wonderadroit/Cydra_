import pytest

from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_graph import ReasoningGraph


def _hypothesis():
    return Hypothesis(
        name="h1",
        probability=0.5,
        predictions={"yes": {"h1": 1.0}},
    )


def _observation():
    return Observation(
        name="check",
        outcomes=["yes", "no"],
        cost=1.0,
        authorized=True,
    )


def test_latest_audit_event_binds_current_model_state():
    graph = ReasoningGraph()
    graph.record_plan(Plan("check", 0.5, 0.5, "test"), [_hypothesis()], _observation())
    assert graph.verify_history_integrity() == []
    assert graph.verify_state_correspondence() == []

    graph.model.nodes["hypothesis:h1"].attributes["probability"] = 0.99
    errors = graph.verify_state_correspondence()
    assert any("state digest mismatch" in error for error in errors)


def test_state_correspondence_detects_missing_event_references():
    graph = ReasoningGraph()
    graph.record_plan(Plan("check", 0.5, 0.5, "test"), [_hypothesis()], _observation())
    graph.history[-1]["hypotheses"] = ["hypothesis:missing"]
    graph.history[-1]["event_hash"] = graph._audit_digest(graph.history[-1])
    assert any("references missing hypothesis" in error for error in graph.verify_state_correspondence())


def test_state_correspondence_is_checked_during_validation():
    graph = ReasoningGraph()
    graph.record_plan(Plan("check", 0.5, 0.5, "test"), [_hypothesis()], _observation())
    graph.model.nodes["observation:check"].attributes["planned"] = False
    with pytest.raises(ValueError, match="invalid reasoning graph"):
        graph.export_state()
