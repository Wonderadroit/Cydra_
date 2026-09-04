import pytest
from cydra.belief_update import BeliefUpdate
from cydra.belief_update_model import persist_belief_update
from cydra.contradiction_re_evaluation import ContradictionDisposition
from cydra.current_belief_state import apply_belief_update
from cydra.system_model import Node, SystemModel

def test_projects_current_belief_without_deleting_history():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "outcome"))
    update = BeliefUpdate("b:1", "c:1", .5, .75, ContradictionDisposition.SUPPORTED, "e:1", "reason")
    persist_belief_update(model, update, "bu:1")
    current = apply_belief_update(model, update, "bu:1")
    assert current.confidence == .75
    assert model.nodes["bu:1"].attributes["posterior_confidence"] == .75
    assert model.nodes["b:1"].attributes["current_source_update"] == "bu:1"

def test_existing_belief_history_is_retained_on_new_projection():
    model = SystemModel()
    model.add_node(Node("b:1", "belief", "b:1", {"history": [0.4]}))
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "outcome"))
    update = BeliefUpdate("b:1", "c:1", .4, .7, ContradictionDisposition.SUPPORTED, "e:1", "reason")
    persist_belief_update(model, update, "bu:1")
    apply_belief_update(model, update, "bu:1")
    assert model.nodes["b:1"].attributes["history"] == [0.4]

def test_missing_persisted_update_rejected():
    model = SystemModel()
    update = BeliefUpdate("b:1", "c:1", .5, .6, ContradictionDisposition.SUPPORTED, "e:1", "reason")
    with pytest.raises(KeyError):
        apply_belief_update(model, update, "bu:missing")
