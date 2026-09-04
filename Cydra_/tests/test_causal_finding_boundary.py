from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_verification import CausalVerificationState, verify_persisted_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def graph_with_trace(support=True):
    graph = ReasoningGraph()
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("verification:v1", "evidence"),
        ("belief:b1", "belief"),
    ):
        graph.model.add_node(Node(node_id, kind, node_id))
    if support:
        graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
        graph.model.connect("verification:v1", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(graph.model, CausalChain(
        "causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief:b1"
    ))
    return graph


def finding():
    return Finding(
        finding_id="finding:1",
        title="Protected state can be altered",
        summary="A causal chain is explicitly supported.",
        severity="HIGH",
        impact=ImpactAssessment(ImpactLevel.HIGH, "asset:vault", "loss of protected funds", evidence_ids=("evidence:e1",)),
        affected_components=("contract:Vault",),
        evidence_ids=("evidence:e1",),
        hypothesis_id="hypothesis:h1",
        causal_chain_id="causal:c1",
    )


def candidate():
    return FindingCandidate(True, False, True, True, True, True)


def test_graph_finding_gate_uses_causal_verification_boundary():
    graph = graph_with_trace()
    result = evaluate_finding_graph(graph, candidate(), finding())
    assert result.decision == GateDecision.READY
    assert verify_persisted_causal_chain(graph.model, "causal:c1").state == CausalVerificationState.VERIFIED


def test_graph_finding_gate_preserves_unresolved_causality():
    graph = graph_with_trace(support=False)
    result = evaluate_finding_graph(graph, candidate(), finding())
    assert result.decision == GateDecision.UNRESOLVED
    assert "explicitly support" in result.reasons[0]
