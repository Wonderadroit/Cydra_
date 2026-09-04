import pytest

from cydra.economic_model import (
    EconomicModel,
    EconomicModelError,
    EconomicState,
    EconomicTransition,
)


def model():
    m = EconomicModel(max_states=3, max_transitions=3, max_scenario_depth=2, max_scenarios=2, max_attacker_capital=100)
    m.add_state(EconomicState("s0", balances={"attacker": 10}, prices={"TOKEN": 1}))
    m.add_state(EconomicState("s1", balances={"attacker": 15}, prices={"TOKEN": 1.5}))
    m.add_state(EconomicState("s2", balances={"attacker": 20}, prices={"TOKEN": 2}))
    m.add_transition(EconomicTransition("t0", "s0", "s1", "attacker", value_delta=5, fee=1, slippage=0.5))
    m.add_transition(EconomicTransition("t1", "s1", "s2", "attacker", value_delta=5, fee=1))
    return m


def test_economic_model_is_deterministic_and_bounded():
    m = model()
    scenario = m.build_scenario(
        scenario_id="scenario:1",
        start_state="s0",
        transition_ids=("t0", "t1"),
        attacker_capital=10,
    )
    assert m.scenario_net_value_delta(scenario) == pytest.approx(7.5)
    assert m.is_simulated_only(scenario) is True


def test_scenario_depth_is_hard_bounded():
    m = model()
    with pytest.raises(EconomicModelError, match="depth"):
        m.build_scenario(
            scenario_id="scenario:deep",
            start_state="s0",
            transition_ids=("t0", "t1", "t0"),
            attacker_capital=10,
        )


def test_attacker_capital_is_authority_bounded():
    m = model()
    with pytest.raises(EconomicModelError, match="capital"):
        m.build_scenario(
            scenario_id="scenario:capital",
            start_state="s0",
            transition_ids=(),
            attacker_capital=101,
        )


def test_simulated_profit_never_becomes_external_execution_evidence():
    m = model()
    scenario = m.build_scenario(
        scenario_id="scenario:profit",
        start_state="s0",
        transition_ids=("t0",),
        attacker_capital=10,
    )
    assert m.scenario_net_value_delta(scenario) == pytest.approx(3.5)
    assert scenario.simulated is True
    assert m.is_simulated_only(scenario) is True


def test_state_identity_collision_is_rejected_without_replacement():
    m = model()
    with pytest.raises(EconomicModelError, match="identity collision"):
        m.add_state(EconomicState("s0", balances={"attacker": 999}))
    assert m.states["s0"].balances["attacker"] == 10


def test_economic_assessment_is_a_bounded_simulation_signal():
    m = model()
    scenario = m.build_scenario(
        scenario_id="scenario:assessment",
        start_state="s0",
        transition_ids=("t0", "t1"),
        attacker_capital=10,
    )
    assessment = m.assess_scenario(scenario)
    assert assessment.profitable is True
    assert assessment.net_value_delta == pytest.approx(7.5)
    assert assessment.capital_efficiency == pytest.approx(0.75)
    assert assessment.simulated_only is True


def test_economic_assessment_requires_canonical_scenario():
    m = model()
    with pytest.raises(EconomicModelError, match="canonical"):
        m.assess_scenario(
            type("Scenario", (), {
                "scenario_id": "scenario:missing",
                "attacker_capital": 10,
                "transition_ids": (),
                "simulated": True,
            })()
        )
