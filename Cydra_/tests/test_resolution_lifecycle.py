from cydra.contradiction_resolution import ResolutionPlan
from cydra.contradiction_resolution_model import ResolutionModelRecord, persist_resolution_plan
from cydra.observation_outcomes import record_observation_outcome
from cydra.resolution_lifecycle import ResolutionStatus, transition_resolution
from cydra.system_model import Node, SystemModel


def _model():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("observation:1", "observation", "check", {"status": "planned"}))
    persist_resolution_plan(model, ResolutionModelRecord(
        "rp:1", "c:1", ResolutionPlan("c:1", "observation:1", 1.0, "distinguish")))
    return model


def test_lifecycle_reaches_successful_with_external_outcome():
    model = _model()
    transition_resolution(model, record_id="rp:1", to_status=ResolutionStatus.EXECUTED)
    record_observation_outcome(model, observation_id="1", outcome_id="o:1", result="supports h1", source="external-test")
    transition_resolution(model, record_id="rp:1", to_status=ResolutionStatus.SUCCESSFUL, outcome_id="o:1")
    assert model.nodes["rp:1"].attributes["status"] == "successful"
    assert model.neighbors("rp:1", "resulted_in") == ["observation_outcome:o:1"]


def test_terminal_state_requires_outcome():
    model = _model()
    transition_resolution(model, record_id="rp:1", to_status=ResolutionStatus.EXECUTED)
    try:
        transition_resolution(model, record_id="rp:1", to_status=ResolutionStatus.FAILED)
    except ValueError:
        pass
    else:
        raise AssertionError("expected outcome requirement")


def test_invalid_transition_does_not_mutate():
    model = _model()
    try:
        transition_resolution(model, record_id="rp:1", to_status=ResolutionStatus.SUCCESSFUL, outcome_id="o:1")
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid transition")
    assert model.nodes["rp:1"].attributes.get("status") is None
