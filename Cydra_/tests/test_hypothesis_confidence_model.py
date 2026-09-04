import pytest

from cydra.hypothesis_confidence import project_hypothesis_confidence
from cydra.hypothesis_confidence_model import persist_hypothesis_confidence
from cydra.system_model import Node, SystemModel


def test_persists_confidence_and_updates_hypothesis():
    model = SystemModel()
    model.add_node(Node("bu:1", "evidence", "belief update"))
    projection = project_hypothesis_confidence("h:1", 0.8, "bu:1")
    persist_hypothesis_confidence(model, projection, "hc:1")
    assert model.nodes["h:1"].kind == "hypothesis"
    assert model.nodes["h:1"].attributes["current_confidence"] == 0.8
    assert model.nodes["hc:1"].attributes["source_update_id"] == "bu:1"
    assert model.neighbors("hc:1", "updates") == ["h:1"]
    assert model.neighbors("hc:1", "based_on") == ["bu:1"]


def test_existing_hypothesis_attributes_are_preserved():
    model = SystemModel()
    model.add_node(Node("bu:1", "evidence", "belief update"))
    model.add_node(Node("h:1", "hypothesis", "h:1", {"history": [0.4]}))
    projection = project_hypothesis_confidence("h:1", 0.7, "bu:1")
    persist_hypothesis_confidence(model, projection, "hc:1")
    assert model.nodes["h:1"].attributes["history"] == [0.4]
    assert model.nodes["h:1"].attributes["current_confidence"] == 0.7


def test_missing_source_does_not_mutate():
    model = SystemModel()
    projection = project_hypothesis_confidence("h:1", 0.7, "bu:missing")
    with pytest.raises(KeyError):
        persist_hypothesis_confidence(model, projection, "hc:1")
    assert "hc:1" not in model.nodes


def test_non_hypothesis_node_is_rejected():
    model = SystemModel()
    model.add_node(Node("bu:1", "evidence", "belief update"))
    model.add_node(Node("h:1", "evidence", "not a hypothesis"))
    projection = project_hypothesis_confidence("h:1", 0.7, "bu:1")
    with pytest.raises(ValueError):
        persist_hypothesis_confidence(model, projection, "hc:1")
