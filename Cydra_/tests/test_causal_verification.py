from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_verification import CausalVerificationState, verify_persisted_causal_chain
from cydra.system_model import Node, SystemModel


def graph_with_chain(*, support=True):
    model = SystemModel()
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("verification:v1", "evidence"),
        ("belief:b1", "belief"),
    ):
        attributes = {"hypothesis_id": "hypothesis:h1"} if kind == "belief" else {}
        model.add_node(Node(node_id, kind, node_id, attributes))
    if support:
        model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_verification")
        model.connect("verification:v1", "supports", "hypothesis:h1", provenance="explicit_verification")
    persist_causal_chain(model, CausalChain(
        "causal:c1", "hypothesis:h1", "observation:o1",
        "evidence:e1", "verification:v1", "belief:b1",
    ))
    return model


def test_causal_verification_requires_explicit_support_and_belief_anchor():
    result = verify_persisted_causal_chain(graph_with_chain(), "causal:c1")
    assert result.state == CausalVerificationState.VERIFIED
    assert result.chain_id == "causal:c1"
    assert result.evidence_ids == ("evidence:e1", "verification:v1")
    assert result.reasons == ()


def test_missing_explicit_causal_support_remains_unresolved():
    result = verify_persisted_causal_chain(graph_with_chain(support=False), "causal:c1")
    assert result.state == CausalVerificationState.UNRESOLVED
    assert "does not explicitly support" in result.reasons[0]


def test_broken_chain_is_rejected():
    model = graph_with_chain()
    model.edges = [
        edge for edge in model.edges
        if not (edge.source == "causal:c1" and edge.relation == "plans")
    ]
    result = verify_persisted_causal_chain(model, "causal:c1")
    assert result.state == CausalVerificationState.REJECTED


def test_mismatched_belief_anchor_is_rejected():
    model = graph_with_chain()
    model.nodes["belief:b1"] = Node("belief:b1", "belief", "belief:b1", {"hypothesis_id": "hypothesis:other"})
    result = verify_persisted_causal_chain(model, "causal:c1")
    assert result.state == CausalVerificationState.REJECTED
    assert "belief-transition hypothesis" in result.reasons[0]


def test_invariant_verification_anchor_is_supported():
    model = SystemModel()
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("invariant:i1", "invariant"),
        ("belief:b1", "belief"),
    ):
        attributes = {"hypothesis_id": "hypothesis:h1"} if kind == "belief" else {}
        model.add_node(Node(node_id, kind, node_id, attributes))
    model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_verification")
    persist_causal_chain(model, CausalChain(
        "causal:c1", "hypothesis:h1", "observation:o1",
        "evidence:e1", "invariant:i1", "belief:b1",
    ))

    result = verify_persisted_causal_chain(model, "causal:c1")

    assert result.state == CausalVerificationState.VERIFIED
    assert result.trace is not None
    assert result.trace.verification_id == "invariant:i1"
    assert result.evidence_ids == ("evidence:e1",)
