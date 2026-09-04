from cydra.contradiction_resolution import ResolutionPlan
from cydra.contradiction_resolution_model import ResolutionModelRecord, persist_resolution_plan
from cydra.system_model import Node, SystemModel


def test_persists_resolution_plan_with_provenance():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("obs:1", "observation", "authorized check"))
    plan = ResolutionPlan("c:1", "obs:1", 0.8, "distinguishes competing hypotheses")
    persist_resolution_plan(model, ResolutionModelRecord("rp:1", "c:1", plan))
    assert model.nodes["rp:1"].attributes["executed"] is False
    assert model.neighbors("c:1", "has_resolution_plan") == ["rp:1"]
    assert model.neighbors("rp:1", "selects_observation") == ["obs:1"]


def test_rejects_missing_references_without_mutation():
    model = SystemModel()
    plan = ResolutionPlan("c:1", "obs:1", 0.8, "reason")
    try:
        persist_resolution_plan(model, ResolutionModelRecord("rp:1", "c:1", plan))
    except KeyError:
        pass
    else:
        raise AssertionError("expected missing contradiction to fail")
    assert model.nodes == {}
    assert model.edges == []


def test_rejects_duplicate_record():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("obs:1", "observation", "check"))
    record = ResolutionModelRecord("rp:1", "c:1", ResolutionPlan("c:1", "obs:1", 1.0, "reason"))
    persist_resolution_plan(model, record)
    try:
        persist_resolution_plan(model, record)
    except ValueError:
        pass
    else:
        raise AssertionError("expected duplicate record to fail")
