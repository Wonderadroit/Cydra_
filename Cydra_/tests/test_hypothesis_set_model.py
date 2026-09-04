import pytest
from cydra.hypothesis_set_model import persist_hypothesis_set
from cydra.system_model import Node, SystemModel

def test_persists_normalized_competing_hypotheses():
    model = SystemModel()
    model.add_node(Node("bu:1", "evidence", "belief update"))
    result = persist_hypothesis_set(model, {"h:1": .7, "h:2": .3}, "bu:1", "hs:1")
    assert sum(result.values()) == pytest.approx(1.0)
    assert model.nodes["h:1"].kind == "hypothesis"
    assert model.nodes["hs:1"].attributes["confidences"]["h:1"] == pytest.approx(.7)
    assert model.neighbors("hs:1", "based_on") == ["bu:1"]

def test_rejects_non_hypothesis_collision_without_mutation():
    model = SystemModel()
    model.add_node(Node("bu:1", "evidence", "belief update"))
    model.add_node(Node("h:1", "belief", "wrong kind"))
    with pytest.raises(ValueError):
        persist_hypothesis_set(model, {"h:1": 1.0}, "bu:1", "hs:1")
    assert "hs:1" not in model.nodes
