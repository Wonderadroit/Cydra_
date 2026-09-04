from cydra.hypothesis_bridge import (
    boundary_record,
    planning_to_persistent,
    planning_set_to_persistent,
    persistent_to_planner,
)
from cydra.planner import Hypothesis as PlanningHypothesis, HypothesisState as PlanningHypothesisState
from cydra.hypotheses import Hypothesis as PersistentHypothesis, HypothesisState as PersistentHypothesisState


def test_planning_hypothesis_projects_identity_probability_state_and_predictions():
    planning = PlanningHypothesis(
        "reentrancy",
        0.8,
        {"trace": {"blocked": 0.9}},
        PlanningHypothesisState.SUPPORTED,
    )
    persistent = planning_to_persistent(planning)
    assert isinstance(persistent, PersistentHypothesis)
    assert persistent.hypothesis_id == "hypothesis:reentrancy"
    assert persistent.statement == "reentrancy"
    assert persistent.belief == 0.8
    assert persistent.state == PersistentHypothesisState.SUPPORTED
    assert persistent.planning_predictions == {"trace": {"blocked": 0.9}}


def test_planning_set_preserves_order():
    planning = [
        PlanningHypothesis("a", 0.2, {}),
        PlanningHypothesis("b", 0.7, {}),
    ]
    persistent = planning_set_to_persistent(planning)
    assert [h.statement for h in persistent] == ["a", "b"]


def test_persistent_to_planner_preserves_explicit_state_and_predictions():
    persistent = PersistentHypothesis(
        "hypothesis:a",
        "a",
        0.6,
        PersistentHypothesisState.CONTRADICTED,
        {"trace": {"blocked": 0.2}},
    )
    planning = persistent_to_planner(persistent)
    assert planning.hypothesis_id == "hypothesis:a"
    assert planning.name == "a"
    assert planning.probability == 0.6
    assert planning.state == PlanningHypothesisState.CONTRADICTED
    assert planning.predictions == {"trace": {"blocked": 0.2}}


def test_persistent_to_planner_does_not_invent_predictions():
    persistent = PersistentHypothesis("hypothesis:a", "a", 0.6)
    planning = persistent_to_planner(persistent)
    assert planning.predictions == {}


def test_explicit_prediction_override_is_not_persisted_back():
    persistent = PersistentHypothesis("hypothesis:a", "a", 0.6, PersistentHypothesisState.UNRESOLVED)
    planning = persistent_to_planner(persistent, predictions={"trace": {"open": 0.8}})
    assert planning.predictions == {"trace": {"open": 0.8}}
    assert persistent.planning_predictions == {}


def test_boundary_record_preserves_planner_values_without_mutation():
    planning = PlanningHypothesis("a", 0.4, {"trace": {"open": 0.7}})
    record = boundary_record(planning)
    assert record.hypothesis_id == "hypothesis:a"
    assert record.probability == 0.4
    assert record.predictions == {"trace": {"open": 0.7}}
    assert record.state == PlanningHypothesisState.UNRESOLVED
    assert planning.predictions == {"trace": {"open": 0.7}}
