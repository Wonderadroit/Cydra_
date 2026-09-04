from copy import deepcopy

import hashlib
import json
import pytest

from cydra.finding import Finding
from cydra.finding_publication import (
    FindingPublication,
    UntrustedFindingPublication,
    build_finding_publication,
    verify_and_trust_finding_publication_data,
    verify_finding_publication,
    verify_finding_publication_data,
)
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
    graph.model.add_node(Node("causal:C1", "causal_chain", "C1", {"evidence_ids": ["evidence:E1", "evidence:V1"]}))
    causal_attrs = {"causal_chain_id": "causal:C1", "evidence_ids": ["evidence:E1", "evidence:V1"]}
    graph.model.edges.extend([
        Edge("hypothesis:H1", "motivates", "causal:C1", causal_attrs),
        Edge("causal:C1", "plans", "observation:O1", causal_attrs),
        Edge("observation:O1", "produced_evidence", "evidence:E1", causal_attrs),
        Edge("evidence:E1", "informs", "evidence:V1", causal_attrs),
        Edge("evidence:V1", "updates", "belief:H1:0", causal_attrs),
        Edge("evidence:E1", "supports", "hypothesis:H1"),
    ])
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


def test_publication_binds_report_to_canonical_finding():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    assert isinstance(publication, FindingPublication)
    assert publication.finding == finding
    assert verify_finding_publication(graph, publication) == []


def test_serialized_parse_is_explicitly_untrusted():
    graph, finding = make_persisted_graph()
    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    parsed = UntrustedFindingPublication.from_dict(deepcopy(payload))
    assert isinstance(parsed, UntrustedFindingPublication)
    assert not isinstance(parsed, FindingPublication)
    assert parsed.finding == finding


def test_trusted_publication_requires_explicit_verification():
    graph, finding = make_persisted_graph()
    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    parsed = UntrustedFindingPublication.from_dict(deepcopy(payload))
    trusted = parsed.verify(graph)
    assert isinstance(trusted, FindingPublication)
    assert trusted.finding == finding
    assert verify_finding_publication(graph, trusted) == []


def test_untrusted_publication_cannot_be_verified_as_trusted():
    graph, finding = make_persisted_graph()
    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    parsed = UntrustedFindingPublication.from_dict(payload)
    assert verify_finding_publication(graph, parsed) == ["publication must be a trusted FindingPublication"]


def test_publication_rejects_substituted_finding_claim():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    altered = Finding(
        finding.finding_id, "substituted title", finding.summary, finding.severity,
        finding.impact, finding.affected_components, finding.evidence_ids,
        finding.hypothesis_id, finding.poc_reference, finding.causal_chain_id,
        finding.audit_session_id,
    )
    forged = FindingPublication(altered, publication.manifest)
    errors = verify_finding_publication(graph, forged)
    assert "published finding claims do not match canonical persisted finding" in errors


def test_publication_rejects_tampered_manifest():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    data = publication.as_dict()
    data["manifest"]["claim_fingerprint"] = "0" * 64
    errors = verify_finding_publication_data(graph, data)
    assert "finding claim fingerprint does not match" in errors


def test_serialized_publication_roundtrip_verifies_against_canonical_graph():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    restored = UntrustedFindingPublication.from_dict(deepcopy(publication.as_dict()))
    assert restored.verify(graph).finding == finding
    assert verify_finding_publication_data(graph, publication.as_dict()) == []


def test_serialized_publication_rejects_substituted_title():
    graph, finding = make_persisted_graph()
    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    payload["finding"]["title"] = "transport-layer substitution"
    errors = verify_finding_publication_data(graph, payload)
    assert "published finding claims do not match canonical persisted finding" in errors
    with pytest.raises(ValueError, match="finding publication verification failed"):
        verify_and_trust_finding_publication_data(graph, payload)


def test_serialized_publication_rejects_finding_and_manifest_schema_drift():
    graph, finding = make_persisted_graph()
    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    payload["finding"]["unexpected"] = "tamper"
    assert any("publication transport validation failed" in error for error in verify_finding_publication_data(graph, payload))

    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    payload["manifest"].pop("claim_fingerprint")
    assert any("publication transport validation failed" in error for error in verify_finding_publication_data(graph, payload))

    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    payload["manifest"]["unexpected"] = "tamper"
    assert any("publication transport validation failed" in error for error in verify_finding_publication_data(graph, payload))


def test_serialized_publication_rejects_finding_id_rebinding():
    graph, finding = make_persisted_graph()
    payload = build_finding_publication(graph, finding.finding_id).as_dict()
    payload["finding"]["finding_id"] = "finding:other"
    errors = verify_finding_publication_data(graph, payload)
    assert "canonical finding recovery failed: persisted finding missing: finding:other" in errors


def test_publication_survives_export_import():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    restored = ReasoningGraph.from_state_dict(deepcopy(graph.export_state()))
    assert verify_finding_publication(restored, publication) == []


def test_publication_verification_is_read_only():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    before = deepcopy(graph.export_state())
    assert verify_finding_publication(graph, publication) == []
    assert graph.export_state() == before


def test_stale_publication_is_rejected_after_canonical_finding_mutation():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    graph.model.nodes[finding.finding_id].attributes["title"] = "canonical mutation"
    errors = verify_finding_publication(graph, publication)
    assert errors
    assert any("canonical" in error or "history" in error for error in errors)


def test_stale_publication_is_rejected_after_relevant_evidence_mutation():
    graph, finding = make_persisted_graph()
    publication = build_finding_publication(graph, finding.finding_id)
    graph.model.nodes["evidence:E1"].attributes["value"] = "mutated evidence"
    errors = verify_finding_publication(graph, publication)
    assert errors
    assert any("canonical" in error or "history" in error for error in errors)
