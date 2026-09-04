from cydra.graph_semantics import validate_graph
from cydra.reasoning_graph import ReasoningGraph
from cydra.planner import Hypothesis, Observation, Plan
from cydra.updater import update_hypotheses


def test_v1_17_end_to_end_reasoning_graph():
    hypotheses = [
        Hypothesis("h1", 0.5, {"o1": {"supports": 1.0, "contradicts": 0.0}}),
        Hypothesis("h2", 0.5, {"o1": {"supports": 0.0, "contradicts": 1.0}}),
    ]
    observation = Observation("o1", ["supports", "contradicts"], 1.0, True)
    plan = Plan(observation, 0.5, 0.5, "distinguishes the competing hypotheses")

    graph = ReasoningGraph()
    observation_id = graph.record_plan(plan, hypotheses, observation)
    result = update_hypotheses(hypotheses, observation.name, "supports", evidence_strength=0.5)
    update = graph.record_update(result, observation_id)

    assert observation_id == "observation:o1"
    assert len(update.belief_node_ids) == 2
    assert graph.validate() == []
    assert validate_graph(graph.model) == []

    edges = graph.model.edges
    assert any(e.source == "hypothesis:h1" and e.relation == "tested_by" and e.target == observation_id for e in edges)
    assert any(e.source == observation_id and e.relation == "updates" and e.target in update.belief_node_ids for e in edges)
    assert any(e.source == "hypothesis:h1" and e.relation == "updated_to" and e.target in update.belief_node_ids for e in edges)


def test_v1_17_rejects_unauthorized_plan():
    observation = Observation("unauthorized", ["blocked"], 1.0, False)
    plan = Plan(observation, 0.1, 0.1, "must not execute")
    graph = ReasoningGraph()

    try:
        graph.record_plan(plan, [], observation)
    except ValueError as exc:
        assert "unauthorized" in str(exc)
    else:
        raise AssertionError("unauthorized observations must be rejected")
