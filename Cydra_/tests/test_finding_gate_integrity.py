from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.finding_pipeline import promote_candidate
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def graph_with_finding_trace() -> ReasoningGraph:
    graph = ReasoningGraph()
    for node_id, kind in (("hypothesis:h1", "hypothesis"), ("observation:o1", "observation"), ("evidence:e1", "evidence"), ("verification:v1", "evidence"), ("belief_update:b1", "belief")):
        graph.model.add_node(Node(node_id, kind, node_id))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
    graph.model.connect("verification:v1", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(graph.model, CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief_update:b1"))
    graph._event("FINDING_TEST_TRACE")
    return graph


def finding(**overrides) -> Finding:
    values = {
        "finding_id": "finding:1", "title": "Unauthorized state transition",
        "summary": "An attacker can cross the modeled trust boundary.", "severity": "HIGH",
        "impact": ImpactAssessment(ImpactLevel.HIGH, "asset:vault", "loss of protected funds", evidence_ids=("evidence:e1",)),
        "affected_components": ("contract:Vault",), "evidence_ids": ("evidence:e1",),
        "hypothesis_id": "hypothesis:h1", "causal_chain_id": "causal:c1",
    }
    values.update(overrides)
    return Finding(**values)


def ready_candidate() -> FindingCandidate:
    return FindingCandidate(True, False, True, True, True, True, True)


def test_graph_gate_requires_canonical_evidence_and_causal_trace():
    graph = graph_with_finding_trace()
    result = evaluate_finding_graph(graph, ready_candidate(), finding())
    assert result.decision == GateDecision.READY
    assert result.reasons == []


def test_graph_gate_rejects_missing_evidence_node():
    graph = graph_with_finding_trace()
    result = evaluate_finding_graph(graph, ready_candidate(), finding(evidence_ids=("evidence:missing",)))
    assert result.decision == GateDecision.BLOCKED
    assert "missing canonical evidence" in result.reasons[0]


def test_graph_gate_rejects_state_or_probability_without_explicit_support():
    graph = graph_with_finding_trace()
    graph.model.edges = [edge for edge in graph.model.edges if not (edge.source == "evidence:e1" and edge.relation == "supports")]
    result = evaluate_finding_graph(graph, ready_candidate(), finding())
    assert result.decision == GateDecision.UNRESOLVED
    assert "causal verification unresolved" in result.reasons[0]


def test_graph_gate_rejects_mismatched_causal_hypothesis():
    graph = graph_with_finding_trace()
    graph.model.nodes["hypothesis:h2"] = Node("hypothesis:h2", "hypothesis", "h2")
    graph.model.connect("evidence:e1", "supports", "hypothesis:h2", provenance="explicit_test")
    result = evaluate_finding_graph(graph, ready_candidate(), finding(hypothesis_id="hypothesis:h2"))
    assert result.decision == GateDecision.BLOCKED
    assert "causal chain hypothesis" in result.reasons[0]


def test_graph_gate_rejects_tampered_audit_history():
    graph = graph_with_finding_trace(); graph.history[0]["type"] = "TAMPERED"
    result = evaluate_finding_graph(graph, ready_candidate(), finding())
    assert result.decision == GateDecision.BLOCKED
    assert result.reasons == ["reasoning audit history is invalid"]


def test_pipeline_uses_graph_gate_when_graph_is_supplied():
    graph = graph_with_finding_trace()
    result = promote_candidate(ready_candidate(), finding(), graph=graph)
    assert result.decision == GateDecision.READY
    assert result.finding is not None


def test_pipeline_cannot_promote_graph_claim_with_boolean_flags_only():
    graph = graph_with_finding_trace()
    graph.model.edges = [edge for edge in graph.model.edges if not (edge.source == "evidence:e1" and edge.relation == "supports")]
    result = promote_candidate(ready_candidate(), finding(), graph=graph)
    assert result.decision == GateDecision.UNRESOLVED
    assert result.finding is None
