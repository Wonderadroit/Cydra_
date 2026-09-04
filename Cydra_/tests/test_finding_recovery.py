from copy import deepcopy

import hashlib
import json
import pytest

from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_recovery import rehydrate_persisted_finding
from cydra.impact import ImpactLevel, assess_impact
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Edge, Node


def _claim_fingerprint(finding):
    encoded = json.dumps(finding.as_report_data(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_persisted_graph():
    graph = ReasoningGraph()
    graph.model.add_node(Node("hypothesis:H1", "hypothesis", "H1", {"state": "supported"}))
    graph.model.add_node(Node("observation:O1", "observation", "O1", {"authorized": True}))
    graph.model.add_node(Node("evidence:E1", "evidence", "E1", {"value": "observed"}))
    graph.model.add_node(Node("evidence:V1", "evidence", "V1", {"value": "verified"}))
    graph.model.add_node(Node("belief:H1:0", "belief", "H1", {"state": "supported"}))
    graph.model.connect("evidence:E1", "supports", "hypothesis:H1")
    persist_causal_chain(
        graph.model,
        CausalChain("causal:C1", "hypothesis:H1", "observation:O1", "evidence:E1", "evidence:V1", "belief:H1:0"),
    )
    finding = Finding(
        "finding:F1", "Original title", "summary", "HIGH",
        assess_impact(level=ImpactLevel.HIGH, asset_at_risk="funds", consequence="loss", evidence_ids=("evidence:E1",)),
        ("Vault",), ("evidence:E1",), "hypothesis:H1", causal_chain_id="causal:C1",
    )
    attrs = finding.as_report_data()
    attrs.update({
        "persisted": True,
        "canonical_evidence_ids": list(finding.evidence_ids),
        "canonical_impact_evidence_ids": list(finding.impact.evidence_ids),
        "canonical_hypothesis_id": finding.hypothesis_id,
        "canonical_causal_chain_id": finding.causal_chain_id,
        "canonical_audit_session_id": finding.audit_session_id,
        "claim_fingerprint": _claim_fingerprint(finding),
    })
    graph.model.add_node(Node(finding.finding_id, "finding", finding.title, attrs))
    graph.model.edges.extend([
        Edge(finding.finding_id, "supported_by", "evidence:E1"),
        Edge(finding.finding_id, "about", "hypothesis:H1"),
        Edge(finding.finding_id, "traced_by", "causal:C1"),
    ])
    graph._event("FINDING_PERSISTED", finding=finding.finding_id)
    return graph, finding


def test_recovery_rejects_report_claim_tampering_bound_by_audit_state():
    graph, finding = make_persisted_graph()
    graph.model.nodes[finding.finding_id].attributes["title"] = "substituted title"
    with pytest.raises(ValueError, match="audit state does not correspond"):
        rehydrate_persisted_finding(graph, finding.finding_id)


def test_recovery_rejects_impact_claim_tampering_bound_by_audit_state():
    graph, finding = make_persisted_graph()
    graph.model.nodes[finding.finding_id].attributes["impact"]["consequence"] = "unbounded loss"
    with pytest.raises(ValueError, match="audit state does not correspond"):
        rehydrate_persisted_finding(graph, finding.finding_id)


def test_recovery_survives_serialization_without_mutation():
    graph, finding = make_persisted_graph()
    restored = ReasoningGraph.from_state_dict(deepcopy(graph.export_state()))
    assert rehydrate_persisted_finding(restored, finding.finding_id) == finding
