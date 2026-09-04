import pytest

from cydra.graph_semantics import validate_semantics
from cydra.planner import Hypothesis, Observation, choose_next_observation, information_gain
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Edge, Node, SystemModel


def _hypotheses():
    return [
        Hypothesis("primary", 0.5, {"check": {"YES": 0.9, "NO": 0.1}}),
        Hypothesis("alternative", 0.5, {"check": {"YES": 0.1, "NO": 0.9}}),
    ]


def test_discriminating_observation_requires_exactly_two_distinct_ids():
    with pytest.raises(ValueError):
        Observation("check", ["YES", "NO"], 1.0, discriminates_hypothesis_ids=("hypothesis:primary",))
    with pytest.raises(ValueError):
        Observation("check", ["YES", "NO"], 1.0, discriminates_hypothesis_ids=("hypothesis:primary", "hypothesis:primary"))


def test_discriminating_observation_must_reference_supplied_hypotheses():
    observation = Observation(
        "check", ["YES", "NO"], 1.0,
        discriminates_hypothesis_ids=("hypothesis:primary", "hypothesis:missing"),
    )
    with pytest.raises(ValueError, match="unknown hypotheses"):
        choose_next_observation(_hypotheses(), [observation])


def test_high_information_observation_without_pair_binding_remains_ordinary():
    observation = Observation("check", ["YES", "NO"], 1.0)
    plan = choose_next_observation(_hypotheses(), [observation])
    assert plan is not None
    assert plan.discriminates_hypothesis_ids == ()
    assert "competing hypothesis pair" not in plan.rationale


def test_planner_preserves_exact_pair_binding_without_changing_information_gain():
    pair = ("hypothesis:primary", "hypothesis:alternative")
    ordinary = Observation("check", ["YES", "NO"], 1.0)
    bound = Observation("check", ["YES", "NO"], 1.0, discriminates_hypothesis_ids=pair)

    ordinary_gain = information_gain(_hypotheses(), ordinary)
    bound_gain = information_gain(_hypotheses(), bound)
    plan = choose_next_observation(_hypotheses(), [bound])

    assert bound_gain == ordinary_gain
    assert plan is not None
    assert plan.expected_information_gain == round(bound_gain, 6)
    assert plan.discriminates_hypothesis_ids == pair
    assert "competing hypothesis pair" in plan.rationale


def test_canonical_graph_can_validate_competing_hypothesis_pair():
    model = SystemModel()
    model.add_node(Node("hypothesis:primary", "hypothesis", "primary"))
    model.add_node(Node("hypothesis:alternative", "hypothesis", "alternative"))
    model.add_edge(Edge("hypothesis:primary", "competes_with", "hypothesis:alternative"))
    assert validate_semantics(model) == []


def test_plan_and_observation_retain_pair_binding_across_planning_boundary():
    graph = ReasoningGraph()
    hypotheses = _hypotheses()
    pair = tuple(h.hypothesis_id for h in hypotheses)
    observation = Observation("check", ["YES", "NO"], 1.0, discriminates_hypothesis_ids=pair)
    plan = choose_next_observation(hypotheses, [observation])
    assert plan is not None
    observation_id = graph.record_plan(plan, hypotheses, observation)
    node = graph.model.nodes[observation_id]
    assert observation.hypothesis_pair == pair
    assert plan.discriminates_hypothesis_ids == pair
    assert node.attributes["planned"] is True


def test_bound_information_gain_ignores_unrelated_hypotheses():
    pair = _hypotheses()
    unrelated = Hypothesis(
        "unrelated",
        0.99,
        {"other": {"YES": 0.5, "NO": 0.5}},
    )
    observation = Observation(
        "check", ["YES", "NO"], 1.0,
        discriminates_hypothesis_ids=tuple(h.hypothesis_id for h in pair),
    )
    pair_gain = information_gain(pair, observation)
    expanded_gain = information_gain(pair + [unrelated], observation)
    assert expanded_gain == pair_gain


def test_equal_value_observations_are_selected_deterministically():
    hypotheses = [
        Hypothesis(
            "primary", 0.5,
            {
                "verify:z": {"YES": 0.9, "NO": 0.1},
                "verify:a": {"YES": 0.9, "NO": 0.1},
            },
        ),
        Hypothesis(
            "alternative", 0.5,
            {
                "verify:z": {"YES": 0.1, "NO": 0.9},
                "verify:a": {"YES": 0.1, "NO": 0.9},
            },
        ),
    ]
    observations = [
        Observation("verify:z", ["YES", "NO"], 1.0),
        Observation("verify:a", ["YES", "NO"], 1.0),
    ]
    first = choose_next_observation(hypotheses, observations)
    second = choose_next_observation(hypotheses, list(reversed(observations)))
    assert first is not None and second is not None
    assert first.observation == second.observation == "verify:a"
