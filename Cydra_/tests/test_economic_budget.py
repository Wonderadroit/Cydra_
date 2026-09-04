import pytest

from cydra.economic_model import EconomicModel, EconomicModelError, EconomicState, EconomicTransition


def make_model():
    model = EconomicModel(max_scenario_depth=2, max_scenarios=10, max_economic_budget=2)
    model.add_state(EconomicState("s0", balances={"attacker": 10}))
    model.add_state(EconomicState("s1", balances={"attacker": 20}))
    model.add_transition(EconomicTransition("t1", "s0", "s1", "attacker", value_delta=10))
    return model


def test_economic_budget_is_separate_from_external_execution_cost():
    model = make_model()
    assert model.remaining_economic_budget == 2
    scenario = model.build_scenario(scenario_id="scenario:1", start_state="s0", transition_ids=("t1",), attacker_capital=10)
    assert scenario.simulated is True
    assert model.economic_budget_used == 1
    assert model.remaining_economic_budget == 1


def test_economic_budget_exhaustion_does_not_grant_execution_authority():
    model = make_model()
    model.build_scenario(scenario_id="scenario:1", start_state="s0", transition_ids=("t1",), attacker_capital=10)
    model.build_scenario(scenario_id="scenario:2", start_state="s0", transition_ids=(), attacker_capital=10)
    with pytest.raises(EconomicModelError, match="economic simulation budget exhausted"):
        model.build_scenario(scenario_id="scenario:3", start_state="s0", transition_ids=(), attacker_capital=10)
    assert model.remaining_economic_budget == 0


def test_invalid_scenario_does_not_consume_economic_budget():
    model = make_model()
    with pytest.raises(EconomicModelError, match="transition chain"):
        model.build_scenario(scenario_id="scenario:bad", start_state="s0", transition_ids=("missing",), attacker_capital=10)
    assert model.economic_budget_used == 0


def test_profitable_simulation_remains_simulation_only():
    model = make_model()
    scenario = model.build_scenario(scenario_id="scenario:profit", start_state="s0", transition_ids=("t1",), attacker_capital=10)
    assessment = model.assess_scenario(scenario)
    assert assessment.profitable is True
    assert assessment.simulated_only is True
