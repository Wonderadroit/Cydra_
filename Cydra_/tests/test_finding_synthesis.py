from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding_gate import FindingCandidate, GateDecision
from cydra.finding_synthesis import ReasoningFindingDraft, synthesize_reasoning_findings
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def graph_with_trace() -> ReasoningGraph:
    graph = ReasoningGraph()
    for node_id, kind, attributes in (
        ("hypothesis:h1", "hypothesis", {}),
        ("observation:o1", "observation", {"planned": True}),
        ("evidence:e1", "evidence", {}),
        ("evidence:v1", "evidence", {}),
        ("belief:b1", "belief", {"hypothesis_id": "hypothesis:h1"}),
    ):
        graph.model.add_node(Node(node_id, kind, node_id, attributes))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(
        graph.model,
        CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "evidence:v1", "belief:b1"),
    )
    return graph


def draft(**overrides) -> ReasoningFindingDraft:
    values = dict(
        finding_id="finding:1",
        title="Protected state can be altered",
        summary="An explicit reasoning claim is grounded in the verified causal trace.",
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
        candidate=FindingCandidate(True, False, True, True, True, True, True),
    )
    values.update(overrides)
    return ReasoningFindingDraft(**values)


def test_explicit_reasoning_draft_becomes_promotion_candidate():
    graph = graph_with_trace()
    candidates = synthesize_reasoning_findings(graph, [draft()])

    assert len(candidates) == 1
    assert candidates[0].finding.finding_id == "finding:1"
    assert candidates[0].candidate.causal_verified is True


def test_missing_canonical_evidence_is_rejected():
    graph = graph_with_trace()
    bad = draft(evidence_ids=("evidence:missing",))

    try:
        synthesize_reasoning_findings(graph, [bad])
    except ValueError as exc:
        assert "evidence is not canonical" in str(exc)
    else:
        raise AssertionError("missing evidence must not be synthesized")


def test_duplicate_draft_ids_are_rejected():
    graph = graph_with_trace()

    try:
        synthesize_reasoning_findings(graph, [draft(), draft()])
    except ValueError as exc:
        assert "duplicate finding draft ID" in str(exc)
    else:
        raise AssertionError("duplicate draft IDs must be rejected")
