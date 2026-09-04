from copy import deepcopy

from cydra.finding import Finding
from cydra.finding_recovery import _claim_fingerprint, rehydrate_persisted_finding, validate_persisted_findings
from cydra.impact import ImpactLevel, assess_impact
from cydra.reasoning_graph import ReasoningGraph
from cydra.reproducibility import build_reproducibility_manifest, verify_reproducibility_manifest
from cydra.system_model import Edge, Node, SystemModel


def make_graph_and_finding():
    graph = ReasoningGraph()
    graph.model.add_node(Node("finding:F1", "finding", "F1"))
    graph.model.add_node(Node("hypothesis:H1", "hypothesis", "H1", {"state": "supported", "probability": 0.95}))
    graph.model.add_node(Node("observation:O1", "observation", "O1", {"authorized": True}))
    graph.model.add_node(Node("evidence:E1", "evidence", "E1", {"value": "observed"}))
    graph.model.add_node(Node("evidence:V1", "evidence", "V1", {"value": "verified"}))
    graph.model.add_node(Node("belief:H1:0", "belief", "H1", {"state": "supported"}))
    graph.model.add_node(Node("causal:C1", "causal_chain", "C1", {"evidence_ids": ["evidence:E1", "evidence:V1"]}))
    graph.model.edges.extend([
        Edge("hypothesis:H1", "motivates", "causal:C1", {"causal_chain_id": "causal:C1"}),
        Edge("causal:C1", "plans", "observation:O1", {"causal_chain_id": "causal:C1"}),
        Edge("observation:O1", "produced_evidence", "evidence:E1", {"causal_chain_id": "causal:C1"}),
        Edge("evidence:E1", "informs", "evidence:V1", {"causal_chain_id": "causal:C1"}),
        Edge("evidence:V1", "updates", "belief:H1:0", {"causal_chain_id": "causal:C1"}),
        Edge("evidence:E1", "supports", "hypothesis:H1", {"provenance": "test"}),
    ])
    finding = Finding(
        "finding:F1", "F1", "summary", "HIGH",
        assess_impact(level=ImpactLevel.HIGH, asset_at_risk="funds", consequence="loss", evidence_ids=("evidence:E1",)),
        ("Vault",), ("evidence:E1",), "hypothesis:H1", causal_chain_id="causal:C1",
    )
    return graph, finding


def persist_fixture_finding(graph, finding):
    attributes = finding.as_report_data()
    attributes.update({
        "persisted": True,
        "canonical_evidence_ids": list(finding.evidence_ids),
        "canonical_impact_evidence_ids": list(finding.impact.evidence_ids),
        "canonical_hypothesis_id": finding.hypothesis_id,
        "canonical_causal_chain_id": finding.causal_chain_id,
        "canonical_audit_session_id": finding.audit_session_id,
        "claim_fingerprint": _claim_fingerprint(finding),
    })
    graph.model.nodes[finding.finding_id] = Node(finding.finding_id, "finding", finding.title, attributes)
    graph.model.edges.extend([
        Edge(finding.finding_id, "supported_by", evidence_id, {"provenance": "explicit_finding_gate"})
        for evidence_id in finding.evidence_ids
    ])
    graph.model.edges.extend([
        Edge(finding.finding_id, "about", finding.hypothesis_id, {"provenance": "explicit_finding_gate"}),
        Edge(finding.finding_id, "traced_by", finding.causal_chain_id, {"provenance": "explicit_finding_gate"}),
    ])


def test_manifest_is_deterministic():
    graph, finding = make_graph_and_finding()
    assert build_reproducibility_manifest(graph, finding) == build_reproducibility_manifest(graph, finding)


def test_manifest_contains_full_causal_reasoning_closure():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    assert manifest.reasoning_node_ids == ("belief:H1:0", "causal:C1", "evidence:E1", "evidence:V1", "finding:F1", "hypothesis:H1", "observation:O1")
    assert manifest.impact_evidence_ids == ("evidence:E1",)


def test_manifest_verifies_unchanged_canonical_state():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    assert verify_reproducibility_manifest(graph, finding, manifest) == []


def test_manifest_detects_canonical_state_tampering():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    node = graph.model.nodes["evidence:E1"]
    graph.model.nodes["evidence:E1"] = Node(node.node_id, node.kind, node.label, {**node.attributes, "value": "tampered"})
    assert "canonical graph fingerprint does not match" in verify_reproducibility_manifest(graph, finding, manifest)


def test_manifest_detects_finding_claim_tampering():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    altered = Finding(finding.finding_id, "Tampered title", finding.summary, finding.severity, finding.impact, finding.affected_components, finding.evidence_ids, finding.hypothesis_id, finding.poc_reference, finding.causal_chain_id, finding.audit_session_id)
    errors = verify_reproducibility_manifest(graph, altered, manifest)
    assert "finding claim fingerprint does not match" in errors


def test_manifest_detects_impact_evidence_tampering():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    altered_impact = assess_impact(level=ImpactLevel.HIGH, asset_at_risk="funds", consequence="different consequence", evidence_ids=("evidence:E1",))
    altered = Finding(finding.finding_id, finding.title, finding.summary, finding.severity, altered_impact, finding.affected_components, finding.evidence_ids, finding.hypothesis_id, finding.poc_reference, finding.causal_chain_id, finding.audit_session_id)
    errors = verify_reproducibility_manifest(graph, altered, manifest)
    assert "finding claim fingerprint does not match" in errors


def test_manifest_detects_audit_history_tampering():
    graph, finding = make_graph_and_finding()
    graph._event("TEST_EVENT", reason="baseline")
    manifest = build_reproducibility_manifest(graph, finding)
    graph.history[0]["type"] = "TAMPERED_EVENT"
    errors = verify_reproducibility_manifest(graph, finding, manifest)
    assert "canonical state cannot be fingerprinted" in errors[0]


def test_manifest_rejects_unreconstructable_causal_chain():
    graph, finding = make_graph_and_finding()
    graph.model.edges = []
    try:
        build_reproducibility_manifest(graph, finding)
    except ValueError as exc:
        assert "causal chain is not reproducible" in str(exc)
    else:
        raise AssertionError("expected causal-chain reconstruction failure")


def test_manifest_identity_mismatch_does_not_mutate_graph():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    altered = Finding("finding:OTHER", finding.title, finding.summary, finding.severity, finding.impact, finding.affected_components, finding.evidence_ids, finding.hypothesis_id, finding.poc_reference, finding.causal_chain_id, finding.audit_session_id)
    before = dict(graph.model.nodes["evidence:E1"].attributes)
    assert "manifest finding identity does not match" in verify_reproducibility_manifest(graph, altered, manifest)
    assert graph.model.nodes["evidence:E1"].attributes == before


def test_report_data_round_trip_rehydrates_identical_finding():
    _, finding = make_graph_and_finding()
    persisted = finding.as_report_data()
    recovered = Finding.from_report_data(deepcopy(persisted))
    assert recovered == finding
    assert recovered.as_report_data() == persisted


def test_rehydrated_finding_verifies_against_manifest():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    recovered = Finding.from_report_data(finding.as_report_data())
    assert verify_reproducibility_manifest(graph, recovered, manifest) == []


def test_rehydrated_tampered_title_fails_manifest_verification():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    payload = finding.as_report_data()
    payload["title"] = "substituted title"
    recovered = Finding.from_report_data(payload)
    errors = verify_reproducibility_manifest(graph, recovered, manifest)
    assert "finding claim fingerprint does not match" in errors


def test_rehydrated_tampered_impact_evidence_fails_manifest_verification():
    graph, finding = make_graph_and_finding()
    manifest = build_reproducibility_manifest(graph, finding)
    payload = finding.as_report_data()
    payload["impact"]["evidence_ids"] = []
    recovered = Finding.from_report_data(payload)
    errors = verify_reproducibility_manifest(graph, recovered, manifest)
    assert "manifest impact evidence identities do not match" in errors
    assert "finding claim fingerprint does not match" in errors


def test_rehydration_rejects_noncanonical_severity():
    _, finding = make_graph_and_finding()
    payload = finding.as_report_data()
    payload["severity"] = "SEVERE"
    try:
        Finding.from_report_data(payload)
    except ValueError as exc:
        assert "severity is not canonical" in str(exc)
    else:
        raise AssertionError("expected noncanonical severity to be rejected")


def test_rehydration_rejects_malformed_claim_types():
    _, finding = make_graph_and_finding()
    payload = finding.as_report_data()
    payload["affected_components"] = "Vault"
    try:
        Finding.from_report_data(payload)
    except TypeError as exc:
        assert "affected components" in str(exc)
    else:
        raise AssertionError("expected malformed persisted finding to be rejected")


def test_persisted_finding_rehydrates_from_canonical_graph():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    recovered = rehydrate_persisted_finding(graph, finding.finding_id)
    assert recovered == finding
    assert validate_persisted_findings(graph) == []


def test_export_import_preserves_persisted_finding_recovery():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    restored = ReasoningGraph.from_state_dict(graph.export_state())
    assert rehydrate_persisted_finding(restored, finding.finding_id) == finding


def test_recovery_rejects_substituted_canonical_evidence_ids():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    graph.model.nodes[finding.finding_id].attributes["canonical_evidence_ids"] = ["evidence:V1"]
    try:
        rehydrate_persisted_finding(graph, finding.finding_id)
    except ValueError as exc:
        assert "canonical_evidence_ids disagrees" in str(exc)
    else:
        raise AssertionError("expected substituted canonical evidence to be rejected")


def test_recovery_rejects_tampered_persisted_impact_claim():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    graph.model.nodes[finding.finding_id].attributes["impact"]["consequence"] = "unbounded loss"
    errors = validate_persisted_findings(graph)
    assert any("canonical" in error or "claim" in error or "disagrees" in error for error in errors)


def test_recovery_rejects_missing_canonical_finding_edge():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    graph.model.edges = [edge for edge in graph.model.edges if not (edge.source == finding.finding_id and edge.relation == "traced_by")]
    try:
        rehydrate_persisted_finding(graph, finding.finding_id)
    except ValueError as exc:
        assert "missing canonical graph edges" in str(exc)
    else:
        raise AssertionError("expected missing finding edge to be rejected")


def test_recovery_rejects_severity_impact_mismatch():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    graph.model.nodes[finding.finding_id].attributes["severity"] = "CRITICAL"
    try:
        rehydrate_persisted_finding(graph, finding.finding_id)
    except ValueError as exc:
        assert "severity" in str(exc)
    else:
        raise AssertionError("expected severity/impact mismatch to be rejected")


def test_recovery_is_read_only():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    before = deepcopy(graph.export_state())
    rehydrate_persisted_finding(graph, finding.finding_id)
    assert graph.export_state() == before


def test_system_model_round_trip_retains_serialized_finding_for_recovery():
    graph, finding = make_graph_and_finding()
    persist_fixture_finding(graph, finding)
    restored_model = SystemModel.from_dict(graph.model.export())
    restored = ReasoningGraph(restored_model)
    assert rehydrate_persisted_finding(restored, finding.finding_id) == finding
