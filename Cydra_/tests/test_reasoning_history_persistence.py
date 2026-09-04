import copy

import pytest

from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def _graph_with_history():
    graph = ReasoningGraph()
    graph.model.add_node(Node("hypothesis:h1", "hypothesis", "h1", {"probability": 0.5, "predictions": {}, "state": "unresolved", "subject_id": "hypothesis:h1"}))
    graph._event("TEST_HISTORY_EVENT", subject="hypothesis:h1")
    return graph


def test_reasoning_state_round_trip_preserves_history_and_chain():
    original = _graph_with_history()
    state = original.export_state()

    restored = ReasoningGraph.from_state_dict(state)

    assert restored.model.export() == original.model.export()
    assert restored.export_history() == original.export_history()
    assert restored.verify_history_integrity() == []


def test_reasoning_state_rejects_tampered_event_without_recomputing_hash():
    state = _graph_with_history().export_state()
    tampered = copy.deepcopy(state)
    tampered["history"][0]["subject"] = "hypothesis:attacker"

    with pytest.raises(ValueError, match="audit event hash mismatch"):
        ReasoningGraph.from_state_dict(tampered)


def test_reasoning_state_requires_explicit_history():
    state = _graph_with_history().export_state()
    state.pop("history")

    with pytest.raises(ValueError, match="missing audit history"):
        ReasoningGraph.from_state_dict(state)


def test_legacy_model_export_does_not_fabricate_reasoning_history():
    graph = ReasoningGraph()
    graph.model.add_node(Node("hypothesis:h1", "hypothesis", "h1", {"probability": 0.5, "predictions": {}, "state": "unresolved", "subject_id": "hypothesis:h1"}))

    assert graph.model.export()["nodes"]
    assert graph.history == []
