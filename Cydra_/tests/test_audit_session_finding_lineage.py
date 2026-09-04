import pytest

from cydra.audit_session import RepositoryAuditSession
from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactLevel, assess_impact
from cydra.reasoning_graph import ReasoningGraph
from cydra.scope import ScopeDecision, ScopeState
from cydra.system_model import Node


def _resolver(path):
    return ScopeDecision(
        target=path,
        state=ScopeState.IN_SCOPE,
        allowed_for_active_testing=True,
        reason="test",
    )


def _graph():
    session = RepositoryAuditSession(_resolver)
    result = session.scan(["src/A.sol"], {"src/A.sol": "contract A {}"})
    graph = ReasoningGraph(result.model)
    for node_id, kind in (
        ("hypothesis:h1", "hypothesis"),
        ("observation:o1", "observation"),
        ("evidence:e1", "evidence"),
        ("invariant:i1", "invariant"),
        ("belief:b1", "belief"),
    ):
        attrs = {"hypothesis_id": "hypothesis:h1"} if kind == "belief" else {}
        graph.model.add_node(Node(node_id, kind, node_id, attrs))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_verification")
    persist_causal_chain(
        graph.model,
        CausalChain(
            "causal:c1",
            "hypothesis:h1",
            "observation:o1",
            "evidence:e1",
            "invariant:i1",
            "belief:b1",
            result.session_id,
        ),
    )
    return graph, result.session_id


def _finding(session_id):
    return Finding(
        finding_id="finding:f1",
        title="lineage test",
        summary="test",
        severity="MEDIUM",
        impact=assess_impact(
            level=ImpactLevel.MEDIUM,
            asset_at_risk="test asset",
            consequence="test consequence",
            evidence_ids=("evidence:e1",),
        ),
        affected_components=("A",),
        evidence_ids=("evidence:e1",),
        hypothesis_id="hypothesis:h1",
        causal_chain_id="causal:c1",
        audit_session_id=session_id,
    )


def test_finding_persistence_accepts_canonical_session_lineage():
    graph, session_id = _graph()
    persist_finding(graph, _finding(session_id))
    assert graph.model.nodes["finding:f1"].kind == "finding"


def test_finding_persistence_rejects_existing_session_substitution():
    graph, session_id = _graph()
    fake = Node("audit-session:fake", "audit_session", "fake", {"passive": True})
    graph.model.add_node(fake)
    finding = _finding("audit-session:fake")
    with pytest.raises(ValueError, match="audit-session provenance is invalid"):
        persist_finding(graph, finding)


def test_finding_persistence_rejects_missing_session_lineage():
    graph, session_id = _graph()
    finding = _finding("")
    with pytest.raises(ValueError, match="finding requires audit-session provenance"):
        persist_finding(graph, finding)


def test_finding_persistence_rejects_cross_session_causal_chain():
    graph, session_id = _graph()
    source = graph.model.nodes[session_id]
    fake_session_id = "audit-session:other"
    graph.model.add_node(Node(fake_session_id, "audit_session", fake_session_id, dict(source.attributes)))
    persist_causal_chain(
        graph.model,
        CausalChain(
            "causal:c2",
            "hypothesis:h1",
            "observation:o1",
            "evidence:e1",
            "invariant:i1",
            "belief:b1",
            fake_session_id,
        ),
    )
    finding = _finding(session_id)
    finding = Finding(
        finding_id=finding.finding_id,
        title=finding.title,
        summary=finding.summary,
        severity=finding.severity,
        impact=finding.impact,
        affected_components=finding.affected_components,
        evidence_ids=finding.evidence_ids,
        hypothesis_id=finding.hypothesis_id,
        causal_chain_id="causal:c2",
        audit_session_id=session_id,
    )
    with pytest.raises(ValueError, match="causal chain audit-session provenance"):
        persist_finding(graph, finding)
