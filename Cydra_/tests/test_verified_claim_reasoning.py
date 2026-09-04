from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_verification import CausalVerificationState
from cydra.finding_gate import FindingCandidate
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.security_reasoning import SecurityClaimProposal, VerifiedSecurityClaim, persist_verified_security_claim
from cydra.system_model import Node
from cydra.verified_claim_reasoning import VerifiedClaimPolicy, propose_verified_claims


def graph_with_verified_claim() -> ReasoningGraph:
    graph = ReasoningGraph()
    graph.model.add_node(Node("hypothesis:h1", "hypothesis", "h1", {
        "security_claim": {
            "finding_id": "finding:h1",
            "title": "Protected balance can diverge",
            "summary": "The verified counterexample demonstrates a protected accounting failure.",
            "severity": "HIGH",
            "asset_at_risk": "vault balance",
            "consequence": "accounting state can diverge from the protected balance",
            "affected_components": ["Vault"],
            "evidence_ids": ["evidence:e1", "evidence:v1"],
            "impact_evidence_ids": ["evidence:e1"],
            "in_scope": True,
            "reproducible": True,
            "hypothesis_resolved": True,
            "competing_hypothesis_id": "hypothesis:h2",
        },
        "state": "supported",
    }))
    graph.model.add_node(Node("hypothesis:h2", "hypothesis", "h2", {"state": "contradicted"}))
    graph.model.add_node(Node("observation:o1", "observation", "o1", {
        "planned": True,
        "discriminates_hypothesis_ids": ("hypothesis:h1", "hypothesis:h2"),
    }))
    graph.model.add_node(Node("evidence:e1", "evidence", "e1", {}))
    graph.model.add_node(Node("evidence:v1", "evidence", "v1", {}))
    graph.model.add_node(Node("belief:b1", "belief", "b1", {"hypothesis_id": "hypothesis:h1"}))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="counterexample")
    graph.model.connect("evidence:v1", "supports", "hypothesis:h1", provenance="independent_replay")
    graph.model.connect("hypothesis:h1", "competes_with", "hypothesis:h2", provenance="test")
    persist_causal_chain(graph.model, CausalChain(
        "causal:h1", "hypothesis:h1", "observation:o1", "evidence:e1", "evidence:v1", "belief:b1"
    ))
    persist_verified_security_claim(
        graph,
        VerifiedSecurityClaim(
            SecurityClaimProposal("hypothesis:h1", "o1", graph.model.nodes["hypothesis:h1"].attributes["security_claim"]),
            "causal:h1",
            ("evidence:e1", "evidence:v1"),
        ),
    )
    return graph


def test_verified_causal_state_emits_explicit_claim_draft():
    graph = graph_with_verified_claim()
    drafts = propose_verified_claims(graph)

    assert len(drafts) == 1
    assert drafts[0].finding_id == "finding:h1"
    assert drafts[0].candidate == FindingCandidate(True, False, True, True, True, True, True)


def test_unverified_causal_state_emits_nothing():
    graph = graph_with_verified_claim()
    graph.model.edges = [edge for edge in graph.model.edges if not (
        edge.source == "evidence:v1" and edge.relation == "supports"
    )]

    assert propose_verified_claims(graph) == ()


def test_hypothesis_without_explicit_claim_metadata_emits_nothing():
    graph = graph_with_verified_claim()
    node = graph.model.nodes["hypothesis:h1"]
    graph.model.nodes["hypothesis:h1"] = Node(node.node_id, node.kind, node.label, {})

    assert propose_verified_claims(graph) == ()


def test_claim_policy_bounds_output():
    graph = graph_with_verified_claim()
    assert len(propose_verified_claims(graph, policy=VerifiedClaimPolicy(max_claims=1))) == 1


def test_finding_claim_requires_persisted_verified_security_claim():
    graph = graph_with_verified_claim()
    del graph.model.nodes["security_claim:hypothesis:h1"]
    assert propose_verified_claims(graph) == ()
