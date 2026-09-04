from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.system_model import Node, SystemModel


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


def test_persists_complete_causal_chain():
    model = model_with_chain_nodes()
    chain = CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief_update:b1")
    persist_causal_chain(model, chain)
    assert model.nodes["causal:c1"].kind == "causal_chain"
    assert model.neighbors("hypothesis:h1", "motivates") == ["causal:c1"]
    assert model.neighbors("causal:c1", "plans") == ["observation:o1"]
    assert model.neighbors("observation:o1", "produced_evidence") == ["evidence:e1"]
    assert model.neighbors("evidence:e1", "informs") == ["verification:v1"]
    assert model.neighbors("verification:v1", "updates") == ["belief_update:b1"]


def test_missing_reference_does_not_mutate_model():
    model = model_with_chain_nodes()
    before = model.export()
    chain = CausalChain("causal:c2", "hypothesis:h1", "observation:missing", "evidence:e1", "verification:v1", "belief_update:b1")
    try:
        persist_causal_chain(model, chain)
    except KeyError:
        pass
    else:
        raise AssertionError("missing references must be rejected")
    assert model.export() == before


def test_duplicate_chain_is_rejected_without_extra_edges():
    model = model_with_chain_nodes()
    chain = CausalChain("causal:c3", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief_update:b1")
    persist_causal_chain(model, chain)
    before = model.export()
    try:
        persist_causal_chain(model, chain)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate chains must be rejected")
    assert model.export() == before
