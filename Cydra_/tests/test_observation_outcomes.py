import pytest

from cydra.graph_semantics import validate_graph
from cydra.observation_outcomes import record_observation_outcome
from cydra.observation_records import persist_test_plan
from cydra.system_model import Node, SystemModel
from cydra.test_planning import ObservationOption, rank_observations
from cydra.hypotheses import Hypothesis


def _model():
    model = SystemModel()
    model.add_node(Node("h1", "hypothesis", "h1"))
    plans = rank_observations(
        [Hypothesis("h1", "candidate claim")],
        [ObservationOption("obs-1", "check control", ("yes", "no"))],
    )
    persist_test_plan(model, plans[0], hypothesis_ids=["h1"])
    return model


def test_record_outcome_links_evidence_and_completes_plan():
    model = _model()
    outcome = record_observation_outcome(
        model,
        observation_id="obs-1",
        outcome_id="out-1",
        result="control rejected request",
        source="authorized test run",
        confidence=0.9,
        metadata={"request_id": "r-1"},
    )
    assert outcome.outcome_id == "out-1"
    assert model.nodes["observation:obs-1"].attributes["status"] == "completed"
    assert model.nodes["observation:obs-1"].attributes["executed"] is True
    evidence = model.nodes["observation_outcome:out-1"]
    assert evidence.kind == "evidence"
    assert model.neighbors("observation:obs-1", "produced") == ["observation_outcome:out-1"]
    assert validate_graph(model) == []


def test_unknown_plan_is_rejected_without_mutation():
    model = SystemModel()
    with pytest.raises(KeyError):
        record_observation_outcome(model, observation_id="missing", outcome_id="o", result="x", source="test")
    assert model.nodes == {}
    assert model.edges == []


def test_duplicate_outcome_is_rejected():
    model = _model()
    record_observation_outcome(model, observation_id="obs-1", outcome_id="out-1", result="x", source="test")
    with pytest.raises(ValueError):
        record_observation_outcome(model, observation_id="obs-1", outcome_id="out-1", result="y", source="test")


def test_completed_plan_cannot_receive_second_outcome():
    model = _model()
    record_observation_outcome(model, observation_id="obs-1", outcome_id="out-1", result="x", source="test")
    with pytest.raises(ValueError, match="not awaiting"):
        record_observation_outcome(model, observation_id="obs-1", outcome_id="out-2", result="y", source="test")
