from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.reasoning_graph import ReasoningGraph
from cydra.security_reasoning import SecurityReasoningInputs, persist_security_claims, security_reasoning_inputs
from cydra.system_model import Node, SystemModel
from cydra.verified_security_reasoning import derive_verified_security_claims
from cydra.ast_dataflow import SemanticRelationshipEvidence


def graph_with_verified_security_chain():
    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "external_call", "token.transfer", 0.95,
        "solc-json-ast:Vault.sol", 100, (100, 10, 1), 10, None,
    ))
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 101, (120, 8, 1), 10, 20,
    ))
    inputs = security_reasoning_inputs(model)
    graph = ReasoningGraph(model)
    graph.add_hypotheses(list(inputs.hypotheses))
    persist_security_claims(graph, inputs)

    primary = next(h for h in inputs.hypotheses if h.name.startswith("security:reentrancy:"))
    for node_id, kind in (
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("verification:v1", "evidence"),
        ("belief:b1", "belief"),
    ):
        attributes = {"hypothesis_id": primary.hypothesis_id} if kind == "belief" else {}
        graph.model.add_node(Node(node_id, kind, node_id, attributes))
    graph.model.connect("evidence:e1", "supports", primary.hypothesis_id, provenance="explicit_verification")
    graph.model.connect("verification:v1", "supports", primary.hypothesis_id, provenance="explicit_verification")
    persist_causal_chain(graph.model, CausalChain(
        "causal:c1", primary.hypothesis_id, "observation:o1",
        "evidence:e1", "verification:v1", "belief:b1",
    ))
    return graph, primary


def test_verified_security_claim_requires_verified_causal_chain():
    graph, primary = graph_with_verified_security_chain()
    claims = derive_verified_security_claims(graph)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.hypothesis_id == primary.hypothesis_id
    assert claim.causal_chain_id == "causal:c1"
    assert claim.evidence_ids == ("evidence:e1", "verification:v1")
    assert claim.mechanism == "external_call_precedes_state_write"


def test_unresolved_causal_chain_emits_no_security_claim():
    graph, primary = graph_with_verified_security_chain()
    graph.model.edges = [
        edge for edge in graph.model.edges
        if not (edge.source == "verification:v1" and edge.target == primary.hypothesis_id and edge.relation == "supports")
    ]
    assert derive_verified_security_claims(graph) == ()


def test_verified_security_claim_does_not_create_finding_nodes():
    graph, _ = graph_with_verified_security_chain()
    derive_verified_security_claims(graph)
    assert all(node.kind != "finding" for node in graph.model.nodes.values())
