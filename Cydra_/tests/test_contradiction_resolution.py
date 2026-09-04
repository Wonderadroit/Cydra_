from cydra.contradiction_resolution import Contradiction, plan_contradiction_resolution
from cydra.test_planning import ObservationOption


def test_prefers_distinguishing_observation_per_cost():
    contradiction = Contradiction("c:1", ("e:1", "e:2"), ("h:1", "h:2"))
    plans = plan_contradiction_resolution(
        contradiction,
        (
            ObservationOption("obs:cheap", "inspect boundary", ("h1", "h2"), 1.0),
            ObservationOption("obs:expensive", "broad trace", ("h1", "h2"), 4.0),
        ),
    )
    assert plans[0].observation_id == "obs:cheap"
    assert plans[0].utility > plans[1].utility


def test_single_outcome_cannot_resolve_contradiction():
    contradiction = Contradiction("c:1", ("e:1", "e:2"), ("h:1", "h:2"))
    plans = plan_contradiction_resolution(
        contradiction,
        (ObservationOption("obs:1", "read declaration", ("same",)),),
    )
    assert plans[0].utility == 0.0


def test_planning_does_not_resolve_or_execute():
    contradiction = Contradiction("c:1", ("e:1", "e:2"), ("h:1", "h:2"))
    plans = plan_contradiction_resolution(
        contradiction,
        (ObservationOption("obs:1", "authorized check", ("support", "contradict")),),
    )
    assert plans[0].observation_id == "obs:1"
    assert "no execution" in plans[0].rationale
