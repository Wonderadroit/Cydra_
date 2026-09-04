from cydra.hypotheses import Hypothesis
from cydra.test_planning import ObservationOption, rank_observations


def test_rank_observations_prefers_information_per_cost():
    hypotheses = (
        Hypothesis("h:1", "deposit writes balance", 0.5),
        Hypothesis("h:2", "withdraw writes balance", 0.5),
    )
    observations = (
        ObservationOption("obs:cheap", "inspect AST write site", ("h1", "h2"), cost=1.0),
        ObservationOption("obs:expensive", "run broad trace", ("h1", "h2"), cost=4.0),
    )
    plans = rank_observations(hypotheses, observations)
    assert plans[0].observation_id == "obs:cheap"
    assert plans[0].utility > plans[1].utility


def test_planner_never_executes_or_changes_belief():
    hypotheses = (Hypothesis("h:1", "deposit writes balance", 0.7),)
    before = hypotheses[0].belief
    plans = rank_observations(
        hypotheses,
        (ObservationOption("obs:1", "observe write trace", ("support", "contradict")),),
    )
    assert plans[0].information_gain >= 0.0
    assert hypotheses[0].belief == before


def test_single_outcome_option_has_no_information_gain():
    hypotheses = (Hypothesis("h:1", "deposit writes balance", 0.7),)
    plans = rank_observations(
        hypotheses,
        (ObservationOption("obs:1", "read static declaration", ("same",)),),
    )
    assert plans[0].information_gain == 0.0
    assert plans[0].utility == 0.0
