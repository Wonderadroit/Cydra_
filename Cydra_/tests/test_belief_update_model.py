import pytest
from cydra.belief_update import BeliefUpdate
from cydra.belief_update_model import persist_belief_update
from cydra.contradiction_re_evaluation import ContradictionDisposition
from cydra.system_model import Node, SystemModel

def test_persists_belief_update_with_provenance():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "outcome"))
    update = BeliefUpdate("b:1", "c:1", .5, .75, ContradictionDisposition.SUPPORTED, "e:1", "reason")
    persist_belief_update(model, update, "bu:1")
    attrs = model.nodes["bu:1"].attributes
    assert attrs["prior_confidence"] == .5
    assert attrs["posterior_confidence"] == .75
    assert model.neighbors("c:1", "updated_by") == ["bu:1"]
    assert model.neighbors("bu:1", "based_on") == ["e:1"]

def test_missing_evidence_does_not_mutate():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    update = BeliefUpdate("b:1", "c:1", .5, .5, ContradictionDisposition.INCONCLUSIVE, "e:x", "reason")
    with pytest.raises(KeyError):
        persist_belief_update(model, update, "bu:1")
    assert "bu:1" not in model.nodes

def test_duplicate_record_rejected():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "outcome"))
    update = BeliefUpdate("b:1", "c:1", .5, .5, ContradictionDisposition.INCONCLUSIVE, "e:1", "reason")
    persist_belief_update(model, update, "bu:1")
    with pytest.raises(ValueError):
        persist_belief_update(model, update, "bu:1")
