from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_reconstruction import reconstruct_causal_chain
from cydra.graph_semantics import validate_graph
from cydra.system_model import Edge, Node, SystemModel


def model_with_chain_nodes() -> SystemModel:
    model = SystemModel()
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("verification:v1", "evidence"),
        ("belief_update:b1", "belief"),
    ):
        model.add_node(Node(node_id, kind, node_id))
    return model


def chain() -> CausalChain:
    return CausalChain(
        "causal:c1",
        "hypothesis:h1",
        "observation:o1",
        "evidence:e1",
        "verification:v1",
        "belief_update:b1",
    )


def test_causal_chain_edges_are_canonically_semantic():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    assert validate_graph(model) == []


def test_causal_chain_reconstruction_is_deterministic():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    trace = reconstruct_causal_chain(model, "causal:c1")
    assert trace.hypothesis_id == "hypothesis:h1"
    assert trace.observation_id == "observation:o1"
    assert trace.outcome_evidence_id == "evidence:e1"
    assert trace.verification_id == "verification:v1"
    assert trace.belief_update_id == "belief_update:b1"
    assert trace.evidence_ids == ("evidence:e1", "verification:v1")


def test_wrong_node_kind_is_rejected_before_mutation():
    model = model_with_chain_nodes()
    model.nodes["verification:v1"] = Node("verification:v1", "observation", "wrong")
    before = model.export()
    try:
        persist_causal_chain(model, chain())
    except ValueError:
        pass
    else:
        raise AssertionError("wrong node kinds must be rejected")
    assert model.export() == before


def test_broken_causal_link_is_rejected_by_reconstruction():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    model.edges = [
        edge for edge in model.edges
        if not (edge.source == "causal:c1" and edge.relation == "plans")
    ]
    try:
        reconstruct_causal_chain(model, "causal:c1")
    except ValueError:
        pass
    else:
        raise AssertionError("missing causal link must be rejected")


def test_duplicate_chain_link_is_rejected_by_reconstruction():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    model.edges.append(Edge(
        "causal:c1",
        "plans",
        "observation:o1",
        {"causal_chain_id": "causal:c1", "evidence_ids": ["evidence:e1", "verification:v1"]},
    ))
    try:
        reconstruct_causal_chain(model, "causal:c1")
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate causal links must be rejected")


def test_causal_chain_preserves_explicit_evidence_references():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    node = model.nodes["causal:c1"]
    assert node.attributes["evidence_ids"] == ["evidence:e1", "verification:v1"]
    chain_edges = [e for e in model.edges if e.attributes.get("causal_chain_id") == "causal:c1"]
    assert all(e.attributes["evidence_ids"] == ["evidence:e1", "verification:v1"] for e in chain_edges)
