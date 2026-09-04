from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def _graph_with_invariant_anchor():
    graph = ReasoningGraph()
    for node_id, kind in (("hypothesis:h1", "hypothesis"), ("observation:o1", "observation"), ("evidence:e1", "evidence"), ("invariant:i1", "invariant"), ("belief:b1", "belief")):
        attrs = {"hypothesis_id": "hypothesis:h1"} if kind == "belief" else {}
        graph.model.add_node(Node(node_id, kind, node_id, attrs))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_verification")
    persist_causal_chain(graph.model, CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "invariant:i1", "belief:b1"))
    return graph


def _ready_candidate():
    return FindingCandidate(True, False, True, True, True, True, True)


def _finding():
    return Finding(
        finding_id="finding:f1", title="Invariant-backed finding", summary="test",
        severity=ImpactLevel.MEDIUM.value,
        impact=ImpactAssessment(ImpactLevel.MEDIUM, "component", "test impact", evidence_ids=("evidence:e1",)),
        affected_components=("component",), evidence_ids=("evidence:e1",),
        hypothesis_id="hypothesis:h1", causal_chain_id="causal:c1",
    )


def test_finding_gate_accepts_invariant_backed_trace():
    graph = _graph_with_invariant_anchor()
    result = evaluate_finding_graph(graph, _ready_candidate(), _finding())
    assert result.decision == GateDecision.READY


def test_finding_persistence_accepts_same_invariant_backed_trace():
    graph = _graph_with_invariant_anchor()
    finding = _finding()
    assert persist_finding(graph, finding) == finding.finding_id
    assert graph.model.nodes[finding.finding_id].kind == "finding"
