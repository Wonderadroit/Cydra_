from cydra.benchmark_finding_promotion import (
    FindingPromotionCandidate,
    finding_claim_fingerprint,
    promote_reasoning_findings,
)
from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def graph_with_trace(*, support=True) -> ReasoningGraph:
    graph = ReasoningGraph()
    for node_id, kind, attributes in (
        ("hypothesis:h1", "hypothesis", {}),
        ("observation:o1", "observation", {"planned": True}),
        ("evidence:e1", "evidence", {}),
        ("evidence:v1", "evidence", {}),
        ("belief:b1", "belief", {"hypothesis_id": "hypothesis:h1"}),
    ):
        graph.model.add_node(Node(node_id, kind, node_id, attributes))
    if support:
        graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
        graph.model.connect("evidence:v1", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(
        graph.model,
        CausalChain(
            "causal:c1",
            "hypothesis:h1",
            "observation:o1",
            "evidence:e1",
            "evidence:v1",
            "belief:b1",
        ),
    )
    return graph


def finding() -> Finding:
    return Finding(
        finding_id="finding:benchmark:1",
        title="Protected state can be altered",
        summary="A verified causal chain demonstrates the security impact.",
        severity="HIGH",
        impact=ImpactAssessment(
            ImpactLevel.HIGH,
            "asset:vault",
            "loss of protected funds",
            evidence_ids=("evidence:e1",),
        ),
        affected_components=("contract:Vault",),
        evidence_ids=("evidence:e1",),
        hypothesis_id="hypothesis:h1",
        causal_chain_id="causal:c1",
    )


def candidate(**overrides) -> FindingCandidate:
    values = {
        "in_scope": True,
        "known_issue": False,
        "evidence": True,
        "reproducible": True,
        "causal_verified": True,
        "impact_assessed": True,
        "hypothesis_resolved": True,
    }
    values.update(overrides)
    return FindingCandidate(**values)


def test_ready_reasoning_finding_is_promoted_and_persisted():
    graph = graph_with_trace()
    item = FindingPromotionCandidate(candidate(), finding())

    attempts = promote_reasoning_findings(graph, [item])

    assert attempts[0].decision == GateDecision.READY
    assert attempts[0].finding_fingerprint == finding_claim_fingerprint(finding())
    assert graph.model.nodes["finding:benchmark:1"].kind == "finding"
    assert any(
        edge.source == "finding:benchmark:1"
        and edge.relation == "supported_by"
        and edge.target == "evidence:e1"
        for edge in graph.model.edges
    )


def test_blocked_candidate_never_persists():
    graph = graph_with_trace()
    item = FindingPromotionCandidate(candidate(impact_assessed=False), finding())

    attempts = promote_reasoning_findings(graph, [item])

    assert attempts[0].decision == GateDecision.BLOCKED
    assert "impact assessment" in attempts[0].reasons
    assert "finding:benchmark:1" not in graph.model.nodes


def test_unresolved_causality_never_persists():
    graph = graph_with_trace(support=False)
    item = FindingPromotionCandidate(candidate(), finding())

    attempts = promote_reasoning_findings(graph, [item])

    assert attempts[0].decision == GateDecision.UNRESOLVED
    assert "finding:benchmark:1" not in graph.model.nodes
