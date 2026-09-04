from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_reconstruction import reconstruct_causal_chain
from cydra.system_model import Node, SystemModel


def model_with_refs():
    model = SystemModel()
    for node_id, kind in (("h1", "hypothesis"), ("o1", "observation"), ("e1", "evidence"), ("v1", "invariant"), ("b1", "belief")):
        model.add_node(Node(node_id, kind, node_id))
    persist_causal_chain(model, CausalChain("c1", "h1", "o1", "e1", "v1", "b1"))
    return model


def test_reconstructs_complete_chain():
    trace = reconstruct_causal_chain(model_with_refs(), "c1")
    assert trace == reconstruct_causal_chain(model_with_refs(), "c1")
    assert (trace.hypothesis_id, trace.observation_id, trace.outcome_evidence_id,
            trace.verification_id, trace.belief_update_id) == ("h1", "o1", "e1", "v1", "b1")


def test_missing_chain_rejected():
    import pytest
    with pytest.raises(KeyError):
        reconstruct_causal_chain(SystemModel(), "missing")


def test_broken_link_rejected():
    import pytest
    model = model_with_refs()
    model.edges = [e for e in model.edges if not (e.source == "c1" and e.relation == "plans")]
    with pytest.raises(ValueError):
        reconstruct_causal_chain(model, "c1")


def test_ambiguous_link_rejected():
    import pytest
    model = model_with_refs()
    from cydra.system_model import Edge
    model.add_node(Node("o2", "observation", "o2"))
    model.edges.append(Edge("c1", "plans", "o2", {"causal_chain_id": "c1"}))
    with pytest.raises(ValueError):
        reconstruct_causal_chain(model, "c1")
