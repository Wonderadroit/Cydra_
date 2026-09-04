from cydra.graph_semantics import contradiction_pairs, validate_graph
from cydra.system_model import Node, SystemModel


def node(model, ident, kind):
    model.add_node(Node(ident, kind, ident))


def test_valid_relationships_are_accepted():
    m = SystemModel()
    node(m, "e", "evidence")
    node(m, "h", "hypothesis")
    node(m, "o", "observation")
    node(m, "b", "belief")
    m.connect("e", "supports", "h")
    m.connect("h", "tested_by", "o")
    m.connect("o", "updates", "b")
    assert validate_graph(m) == []


def test_observation_produced_evidence_relationship_is_accepted():
    m = SystemModel()
    node(m, "o", "observation")
    node(m, "e", "evidence")
    m.connect("o", "produced", "e", executed_externally=True)
    assert validate_graph(m) == []


def test_ast_relationships_are_accepted():
    m = SystemModel()
    node(m, "f", "function")
    node(m, "s", "state_variable")
    node(m, "d", "data_flow")
    m.connect("f", "reads", "s")
    m.connect("f", "writes", "s")
    m.connect("f", "external_call", "d")
    assert validate_graph(m) == []


def test_invalid_relationship_direction_is_rejected():
    m = SystemModel()
    node(m, "h", "hypothesis")
    node(m, "e", "evidence")
    m.connect("h", "supports", "e")
    assert validate_graph(m)


def test_unknown_relationship_is_rejected():
    m = SystemModel()
    node(m, "h", "hypothesis")
    node(m, "e", "evidence")
    m.connect("h", "invented_relation", "e")
    assert any("unknown relationship type" in x for x in validate_graph(m))


def test_contradictions_are_preserved_not_collapsed():
    m = SystemModel()
    node(m, "e1", "evidence")
    node(m, "e2", "evidence")
    m.connect("e1", "contradicts", "e2")
    assert contradiction_pairs(m) == [("e1", "e2")]
