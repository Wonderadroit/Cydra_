from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def graph_with_trace() -> ReasoningGraph:
    graph = ReasoningGraph()
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("verification:v1", "evidence"),
        ("evidence:unrelated", "evidence"),
        ("belief:b1", "belief"),
    ):
        graph.model.add_node(Node(node_id, kind, node_id))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
    graph.model.connect("evidence:unrelated", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(
        graph.model,
        CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief:b1"),
    )
    return graph


def make_finding(evidence_ids, impact_evidence_ids=("evidence:e1",), severity="HIGH"):
    return Finding(
        finding_id="finding:1",
        title="Protected state can be altered",
        summary="A verified reasoning chain supports the claim.",
        severity=severity,
        impact=ImpactAssessment(
            ImpactLevel.HIGH,
            "asset:vault",
            "loss of protected funds",
            evidence_ids=impact_evidence_ids,
        ),
        affected_components=("contract:Vault",),
        evidence_ids=evidence_ids,
        hypothesis_id="hypothesis:h1",
        causal_chain_id="causal:c1",
    )


def test_graph_finding_gate_rejects_evidence_outside_causal_trace():
    graph = graph_with_trace()
    result = evaluate_finding_graph(
        graph,
        FindingCandidate(True, False, True, True, True, True),
        make_finding(("evidence:e1", "evidence:unrelated")),
    )
    assert result.decision == GateDecision.BLOCKED
    assert "grounded in the causal trace" in result.reasons[0]


def test_finding_persistence_rejects_evidence_outside_causal_trace_without_mutation():
    graph = graph_with_trace()
    finding = make_finding(("evidence:e1", "evidence:unrelated"))
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, finding)
    except ValueError as exc:
        assert "grounded in the causal trace" in str(exc)
    else:
        raise AssertionError("ungrounded finding evidence must be rejected")
    assert (graph.model.export(), graph.export_history()) == before


def test_graph_finding_gate_rejects_detached_impact_evidence():
    graph = graph_with_trace()
    result = evaluate_finding_graph(
        graph,
        FindingCandidate(True, False, True, True, True, True),
        make_finding(("evidence:e1",), impact_evidence_ids=("evidence:unrelated",)),
    )
    assert result.decision == GateDecision.BLOCKED
    assert "impact evidence must be grounded in the causal trace" in result.reasons[0]


def test_finding_persistence_rejects_detached_impact_evidence_without_mutation():
    graph = graph_with_trace()
    finding = make_finding(("evidence:e1",), impact_evidence_ids=("evidence:unrelated",))
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, finding)
    except ValueError as exc:
        assert "impact evidence must be grounded in the causal trace" in str(exc)
    else:
        raise AssertionError("detached impact evidence must be rejected")
    assert (graph.model.export(), graph.export_history()) == before


def test_finding_persistence_rejects_severity_impact_mismatch_without_mutation():
    graph = graph_with_trace()
    finding = make_finding(("evidence:e1",), severity="CRITICAL")
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, finding)
    except ValueError as exc:
        assert "severity must match" in str(exc)
    else:
        raise AssertionError("severity/impact mismatch must be rejected")
    assert (graph.model.export(), graph.export_history()) == before


def test_finding_persistence_rejects_missing_impact_evidence_without_mutation():
    graph = graph_with_trace()
    finding = make_finding(("evidence:e1",), impact_evidence_ids=())
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, finding)
    except ValueError as exc:
        assert "impact requires canonical evidence IDs" in str(exc)
    else:
        raise AssertionError("impact without evidence must be rejected")
    assert (graph.model.export(), graph.export_history()) == before
