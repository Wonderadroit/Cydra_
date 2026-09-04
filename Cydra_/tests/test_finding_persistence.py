from cydra.audit_session import RepositoryAuditSession
from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.system_model import Node


def graph_with_trace() -> ReasoningGraph:
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
    return graph


def graph_with_audit_session() -> tuple[ReasoningGraph, str]:
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(["src/Vault.sol"], {"src/Vault.sol": "contract Vault {}"})
    graph = ReasoningGraph(result.model)
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
        CausalChain(
            "causal:c1",
            "hypothesis:h1",
            "observation:o1",
            "evidence:e1",
            "verification:v1",
            "belief_update:b1",
            result.session_id,
        ),
    )
    return graph, result.session_id


def make_finding(**overrides) -> Finding:
    values = {
        "finding_id": "finding:1",
        "title": "Protected state can be altered",
        "summary": "A verified reasoning chain supports the security claim.",
        "severity": "HIGH",
        "impact": ImpactAssessment(
            ImpactLevel.HIGH,
            "asset:vault",
            "loss of protected funds",
            evidence_ids=("evidence:e1",),
        ),
        "affected_components": ("contract:Vault",),
        "evidence_ids": ("evidence:e1",),
        "hypothesis_id": "hypothesis:h1",
        "causal_chain_id": "causal:c1",
    }
    values.update(overrides)
    return Finding(**values)


def test_persist_finding_creates_first_class_graph_node_and_edges():
    graph = graph_with_trace()
    finding = make_finding()
    assert persist_finding(graph, finding) == "finding:1"
    assert graph.model.nodes["finding:1"].kind == "finding"
    assert graph.model.neighbors("finding:1", "supported_by") == ["evidence:e1"]
    assert graph.model.neighbors("finding:1", "about") == ["hypothesis:h1"]
    assert graph.model.neighbors("finding:1", "traced_by") == ["causal:c1"]
    assert graph.history[-1]["type"] == "FINDING_PERSISTED"
    assert graph.validate() == []


def test_persist_finding_binds_audit_session_lineage():
    graph, session_id = graph_with_audit_session()
    finding = make_finding(audit_session_id=session_id)
    assert persist_finding(graph, finding) == "finding:1"
    assert graph.model.neighbors("finding:1", "originates_from") == [session_id]
    assert graph.model.nodes["finding:1"].attributes["canonical_audit_session_id"] == session_id
    assert graph.validate() == []


def test_persist_finding_requires_audit_session_when_canonical_session_exists():
    graph, _ = graph_with_audit_session()
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, make_finding())
    except ValueError as exc:
        assert "audit-session provenance" in str(exc)
    else:
        raise AssertionError("findings in session-backed graphs require audit-session provenance")
    assert (graph.model.export(), graph.export_history()) == before


def test_persist_finding_rejects_tampered_audit_session_provenance():
    graph, session_id = graph_with_audit_session()
    graph.model.nodes[session_id].attributes["intake_id"] = "intake:tampered"
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, make_finding(audit_session_id=session_id))
    except ValueError as exc:
        assert "audit-session provenance" in str(exc)
    else:
        raise AssertionError("tampered audit-session provenance must block finding persistence")
    assert (graph.model.export(), graph.export_history()) == before


def test_persist_finding_is_idempotency_guarded():
    graph = graph_with_trace()
    finding = make_finding()
    persist_finding(graph, finding)
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, finding)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate findings must be rejected")
    assert (graph.model.export(), graph.export_history()) == before


def test_persist_finding_rejects_without_explicit_support():
    graph = graph_with_trace()
    graph.model.edges = [
        edge for edge in graph.model.edges
        if not (edge.source == "evidence:e1" and edge.relation == "supports")
    ]
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, make_finding())
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported findings must be rejected")
    assert (graph.model.export(), graph.export_history()) == before


def test_persist_finding_rejects_disconnected_evidence():
    graph = graph_with_trace()
    graph.model.add_node(Node("evidence:e2", "evidence", "unrelated"))
    graph.model.connect("evidence:e2", "supports", "hypothesis:h1", provenance="explicit_test")
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, make_finding(evidence_ids=("evidence:e2",)))
    except ValueError:
        pass
    else:
        raise AssertionError("disconnected evidence must be rejected")
    assert (graph.model.export(), graph.export_history()) == before


def test_persist_finding_rejects_invalid_audit_history():
    graph = graph_with_trace()
    graph._event("AUDIT_TEST")
    graph.history[0]["type"] = "TAMPERED"
    before = graph.model.export(), graph.export_history()
    try:
        persist_finding(graph, make_finding())
    except ValueError:
        pass
    else:
        raise AssertionError("invalid audit history must block persistence")
    assert (graph.model.export(), graph.export_history()) == before
