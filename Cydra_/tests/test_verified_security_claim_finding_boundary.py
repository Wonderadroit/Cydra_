import pytest

from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.security_reasoning import (
    emit_verified_security_claims,
    persist_verified_security_claim,
)

from test_security_claim_emission import add_verified_causal_chain, add_verified_update, prepared_graph


def make_security_finding(graph, inputs):
    primary, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    verified_claim = emit_verified_security_claims(graph, inputs)[0]
    persist_verified_security_claim(graph, verified_claim)
    return Finding(
        finding_id="finding:security-claim",
        title="Verified security claim",
        summary="The canonical security claim has a verified causal basis.",
        severity="HIGH",
        impact=ImpactAssessment(
            ImpactLevel.HIGH,
            "asset:protected-state",
            "protected state can be altered",
            evidence_ids=(outcome_id,),
        ),
        affected_components=("component:target",),
        evidence_ids=(outcome_id,),
        hypothesis_id=primary.hypothesis_id,
        causal_chain_id=verified_claim.causal_chain_id,
    )


def test_security_finding_requires_persisted_verified_claim():
    graph, inputs = prepared_graph()
    primary, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    finding = Finding(
        finding_id="finding:missing-claim",
        title="Security claim missing",
        summary="Should not cross the claim boundary.",
        severity="HIGH",
        impact=ImpactAssessment(ImpactLevel.HIGH, "asset:x", "impact", evidence_ids=(outcome_id,)),
        affected_components=("component:x",),
        evidence_ids=(outcome_id,),
        hypothesis_id=primary.hypothesis_id,
        causal_chain_id="causal:security-claim",
    )
    result = evaluate_finding_graph(graph, FindingCandidate(True, False, True, True, True, True), finding)
    assert result.decision == GateDecision.BLOCKED
    assert "persisted verified security claim" in result.reasons[0]


def test_verified_security_claim_is_canonical_bridge_to_finding():
    graph, inputs = prepared_graph()
    finding = make_security_finding(graph, inputs)
    result = evaluate_finding_graph(graph, FindingCandidate(True, False, True, True, True, True), finding)
    assert result.decision == GateDecision.READY

    finding_id = persist_finding(graph, finding)
    claim_id = f"security_claim:{finding.hypothesis_id}"
    assert finding_id in graph.model.nodes
    assert graph.model.nodes[claim_id].kind == "security_claim"
    assert any(
        edge.source == finding_id
        and edge.relation == "derived_from_security_claim"
        and edge.target == claim_id
        for edge in graph.model.edges
    )


def test_tampered_verified_claim_cannot_promote_security_finding():
    graph, inputs = prepared_graph()
    finding = make_security_finding(graph, inputs)
    claim_id = f"security_claim:{finding.hypothesis_id}"
    claim = graph.model.nodes[claim_id]
    graph.model.nodes[claim_id] = type(claim)(
        claim.node_id,
        claim.kind,
        claim.label,
        {**claim.attributes, "causal_chain_id": "causal:tampered"},
    )
    result = evaluate_finding_graph(graph, FindingCandidate(True, False, True, True, True, True), finding)
    assert result.decision == GateDecision.BLOCKED
    assert "causal chain does not match" in result.reasons[0]


def test_tampered_verified_claim_payload_cannot_persist_security_finding():
    graph, inputs = prepared_graph()
    finding = make_security_finding(graph, inputs)
    claim_id = f"security_claim:{finding.hypothesis_id}"
    claim = graph.model.nodes[claim_id]
    payload = dict(claim.attributes["claim"])
    payload["statement"] = "tampered claim statement"
    graph.model.nodes[claim_id] = type(claim)(
        claim.node_id,
        claim.kind,
        claim.label,
        {**claim.attributes, "claim": payload},
    )
    with pytest.raises(ValueError, match="security claim payload does not match"):
        persist_finding(graph, finding)


def test_tampered_verified_claim_fingerprint_cannot_persist_security_finding():
    graph, inputs = prepared_graph()
    finding = make_security_finding(graph, inputs)
    claim_id = f"security_claim:{finding.hypothesis_id}"
    claim = graph.model.nodes[claim_id]
    graph.model.nodes[claim_id] = type(claim)(
        claim.node_id,
        claim.kind,
        claim.label,
        {**claim.attributes, "claim_fingerprint": "tampered"},
    )
    with pytest.raises(ValueError, match="security claim fingerprint"):
        persist_finding(graph, finding)

def finding_claim_graph():
    from test_verified_claim_reasoning import graph_with_verified_claim
    graph = graph_with_verified_claim()
    claim = graph.model.nodes["hypothesis:h1"].attributes["security_claim"]
    return graph, Finding(
        finding_id=claim["finding_id"],
        title=claim["title"],
        summary=claim["summary"],
        severity=claim["severity"],
        impact=ImpactAssessment(
            ImpactLevel(claim["severity"]),
            claim["asset_at_risk"],
            claim["consequence"],
            tuple(claim.get("prerequisites", ())),
            tuple(claim.get("impact_evidence_ids", claim["evidence_ids"])),
        ),
        affected_components=tuple(claim["affected_components"]),
        evidence_ids=tuple(claim["evidence_ids"]),
        hypothesis_id="hypothesis:h1",
        poc_reference=claim.get("poc_reference"),
        causal_chain_id="causal:h1",
        audit_session_id=claim.get("audit_session_id"),
    )


@pytest.mark.parametrize(
    "field, value, reason",
    [
        ("title", "Forged title", "finding title does not match verified security claim"),
        ("summary", "Forged summary", "finding summary does not match verified security claim"),
        ("affected_components", ("component:forged",), "finding affected components do not match verified security claim"),
        ("evidence_ids", ("evidence:e1", "evidence:forged"), "finding evidence does not match verified security claim"),
    ],
)
def test_verified_security_claim_binds_report_fields(field, value, reason):
    graph, finding = finding_claim_graph()
    tampered_finding = Finding(**{**finding.__dict__, field: value})

    result = evaluate_finding_graph(
        graph,
        FindingCandidate(True, False, True, True, True, True),
        tampered_finding,
    )

    assert result.decision == GateDecision.BLOCKED
    assert result.reasons == [reason]


def test_verified_security_claim_binds_severity_to_claim_not_only_impact():
    graph, finding = finding_claim_graph()
    tampered_finding = Finding(
        **{
            **finding.__dict__,
            "severity": "MEDIUM",
            "impact": ImpactAssessment(
                ImpactLevel.MEDIUM,
                finding.impact.asset_at_risk,
                finding.impact.consequence,
                finding.impact.prerequisites,
                finding.impact.evidence_ids,
            ),
        }
    )
    result = evaluate_finding_graph(
        graph,
        FindingCandidate(True, False, True, True, True, True),
        tampered_finding,
    )
    assert result.decision == GateDecision.BLOCKED
    assert result.reasons == ["finding severity does not match verified security claim"]

