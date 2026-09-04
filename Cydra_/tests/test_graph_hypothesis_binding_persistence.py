import copy

import pytest

from cydra.planner import Hypothesis, Observation, choose_next_observation
from cydra.reasoning_graph import ReasoningGraph


def _hypotheses():
    return [
        Hypothesis("primary", 0.5, {"check": {"YES": 0.9, "NO": 0.1}}),
        Hypothesis("alternative", 0.5, {"check": {"YES": 0.1, "NO": 0.9}}),
    ]


def _planned_graph():
    hypotheses = _hypotheses()
    pair = tuple(h.hypothesis_id for h in hypotheses)
    observation = Observation("check", ["YES", "NO"], 1.0, discriminates_hypothesis_ids=pair)
    plan = choose_next_observation(hypotheses, [observation])
    assert plan is not None
    graph = ReasoningGraph()
    observation_id = graph.record_plan(plan, hypotheses, observation)
    return graph, observation_id, pair


def test_graph_persists_exact_discriminating_pair_on_observation_and_audit():
    graph, observation_id, pair = _planned_graph()
    node = graph.model.nodes[observation_id]
    event = graph.history[-1]

    assert node.attributes["discriminates_hypothesis_ids"] == list(pair)
    assert event["discriminates_hypothesis_ids"] == list(pair)
    assert any(
        edge.relation == "competes_with"
        and {edge.source, edge.target} == set(pair)
        for edge in graph.model.edges
    )
    assert graph.validate() == []


def test_graph_round_trip_retains_discriminating_pair():
    graph, observation_id, pair = _planned_graph()
    restored = ReasoningGraph.from_state_dict(graph.export_state())

    assert restored.model.nodes[observation_id].attributes["discriminates_hypothesis_ids"] == list(pair)
    assert restored.history[-1]["discriminates_hypothesis_ids"] == list(pair)
    assert restored.validate() == []


def test_graph_rejects_pair_without_declared_competition():
    graph, _, pair = _planned_graph()
    graph.model.edges = [
        edge for edge in graph.model.edges
        if not (edge.relation == "competes_with" and {edge.source, edge.target} == set(pair))
    ]
    errors = graph.verify_state_correspondence()
    assert any("competing hypothesis" in error for error in errors)


def test_graph_rejects_tampered_pair_binding():
    graph, observation_id, pair = _planned_graph()
    tampered = copy.deepcopy(graph.export_state())
    tampered["model"]["nodes"] = [
        {
            **node,
            "attributes": {
                **node["attributes"],
                "discriminates_hypothesis_ids": [pair[0], "hypothesis:missing"],
            },
        }
        if node["id"] == observation_id
        else node
        for node in tampered["model"]["nodes"]
    ]
    with pytest.raises(ValueError):
        ReasoningGraph.from_state_dict(tampered)


def test_graph_rejects_tampered_audit_pair_binding():
    graph, _, pair = _planned_graph()
    tampered = copy.deepcopy(graph.export_state())
    tampered["history"][-1]["discriminates_hypothesis_ids"] = [pair[0], "hypothesis:missing"]
    with pytest.raises(ValueError):
        ReasoningGraph.from_state_dict(tampered)


def test_ordinary_observation_remains_unbound():
    graph = ReasoningGraph()
    hypotheses = _hypotheses()
    observation = Observation("check", ["YES", "NO"], 1.0)
    plan = choose_next_observation(hypotheses, [observation])
    assert plan is not None
    observation_id = graph.record_plan(plan, hypotheses, observation)
    assert graph.model.nodes[observation_id].attributes.get("discriminates_hypothesis_ids") == []
    assert graph.history[-1]["discriminates_hypothesis_ids"] == []
    assert not any(edge.relation == "competes_with" for edge in graph.model.edges)
    assert graph.validate() == []


def test_record_plan_rejects_plan_observation_binding_mismatch():
    hypotheses = _hypotheses()
    pair = tuple(h.hypothesis_id for h in hypotheses)
    observation = Observation("check", ["YES", "NO"], 1.0, discriminates_hypothesis_ids=pair)
    plan = choose_next_observation(hypotheses, [observation])
    assert plan is not None
    unbound_observation = Observation("check", ["YES", "NO"], 1.0)
    with pytest.raises(ValueError, match="plan hypothesis binding"):
        ReasoningGraph().record_plan(plan, hypotheses, unbound_observation)
