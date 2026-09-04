from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.learning import FindingLearningContribution, LearningLimits, LearningStore
from cydra.learning_persistence import persist_verified_finding_learning, rehydrate_persisted_learning
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node


def graph_with_finding() -> tuple[ReasoningGraph, Finding]:
    graph = ReasoningGraph()
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("verification:v1", "evidence"),
        ("belief_update:b1", "belief"),
    ):
        graph.model.add_node(Node(node_id, kind, node_id))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(
        graph.model,
        CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief_update:b1"),
    )
    finding = Finding(
        finding_id="finding:1",
        title="Protected state can be altered",
        summary="A verified reasoning chain supports the security claim.",
        severity="HIGH",
        impact=ImpactAssessment(ImpactLevel.HIGH, "asset:vault", "loss of protected funds", evidence_ids=("evidence:e1",)),
        affected_components=("contract:Vault",),
        evidence_ids=("evidence:e1",),
        hypothesis_id="hypothesis:h1",
        causal_chain_id="causal:c1",
    )
    persist_finding(graph, finding)
    return graph, finding


def contribution() -> FindingLearningContribution:
    return FindingLearningContribution(
        invariant="withdrawal authorization must hold",
        hypothesis="authorization can be bypassed through the withdrawal path",
        observation_pattern="trace authorization state before value transfer",
        dependency_pattern="withdrawal path depends on authorization boundary",
        budget_heuristic="prioritize authorization observations before deeper exploration",
        confidence=0.9,
    )


def test_verified_finding_learning_is_persisted_with_lineage():
    graph, finding = graph_with_finding()
    store = LearningStore()
    ids = persist_verified_finding_learning(graph, store, finding, contribution())
    assert len(ids) == 5
    assert all(node_id.startswith("learning:") for node_id in ids)
    assert all(graph.model.neighbors(node_id, "derived_from_finding") == ["finding:1"] for node_id in ids)
    assert graph.validate() == []
    assert graph.history[-1]["type"] == "LEARNING_PERSISTED"


def test_learning_survives_store_rehydration():
    graph, finding = graph_with_finding()
    store = LearningStore()
    persist_verified_finding_learning(graph, store, finding, contribution())
    recovered = rehydrate_persisted_learning(graph, LearningLimits())
    assert recovered.authority_independent_fingerprint() == store.authority_independent_fingerprint()
    assert len(recovered.records) == 5


def test_learning_recovery_rejects_finding_rebinding():
    graph, finding = graph_with_finding()
    store = LearningStore()
    ids = persist_verified_finding_learning(graph, store, finding, contribution())
    graph.model.nodes[ids[0]].attributes["finding_id"] = "finding:other"
    try:
        rehydrate_persisted_learning(graph, LearningLimits())
    except (KeyError, ValueError):
        pass
    else:
        raise AssertionError("learning rebinding must fail recovery")


def test_learning_recovery_requires_external_limits_match():
    graph, finding = graph_with_finding()
    store = LearningStore(LearningLimits(max_invariants=2))
    persist_verified_finding_learning(graph, store, finding, contribution())
    try:
        rehydrate_persisted_learning(graph, LearningLimits())
    except ValueError as exc:
        assert "limits" in str(exc).lower()
    else:
        raise AssertionError("tampered or mismatched learning limits must fail recovery")
