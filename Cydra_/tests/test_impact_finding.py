from cydra.finding import Finding
from cydra.impact import ImpactLevel, assess_impact


def test_impact_assessment_requires_consequence_and_known_level():
    assessed = assess_impact(
        level=ImpactLevel.HIGH,
        asset_at_risk="protocol funds",
        consequence="attacker can cause unauthorized loss",
        evidence_ids=("e1",),
    )
    assert assessed.assessed is True


def test_unknown_impact_is_not_assessed():
    assessed = assess_impact(
        level=ImpactLevel.UNKNOWN,
        asset_at_risk="protocol funds",
        consequence="",
    )
    assert assessed.assessed is False


def test_finding_preserves_provenance():
    impact = assess_impact(
        level=ImpactLevel.HIGH,
        asset_at_risk="vault funds",
        consequence="unauthorized withdrawal",
        evidence_ids=("e-foundry-1",),
    )
    finding = Finding(
        finding_id="F-001",
        title="Accounting invariant violation",
        summary="A withdrawal path can violate the accounting invariant.",
        severity="HIGH",
        impact=impact,
        affected_components=("InvariantVault.withdraw",),
        evidence_ids=("e-foundry-1", "e-trace-1"),
        hypothesis_id="H-001",
        poc_reference="poc/F-001",
    )
    data = finding.as_report_data()
    assert data["hypothesis_id"] == "H-001"
    assert "e-foundry-1" in data["evidence_ids"]
    assert data["poc_reference"] == "poc/F-001"
