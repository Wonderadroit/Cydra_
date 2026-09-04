from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from .impact import ImpactAssessment, ImpactLevel


@dataclass(frozen=True)
class Finding:
    finding_id: str
    title: str
    summary: str
    severity: str
    impact: ImpactAssessment
    affected_components: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    hypothesis_id: str
    poc_reference: str | None = None
    causal_chain_id: str | None = None
    audit_session_id: str | None = None

    def claim_validation_errors(self, trace_evidence_ids: set[str]) -> list[str]:
        """Validate report-level security claims against canonical reasoning evidence."""
        errors: list[str] = []
        if self.severity not in {level.value for level in ImpactLevel}:
            errors.append(f"finding severity is not canonical: {self.severity}")
        if self.impact.level == ImpactLevel.UNKNOWN:
            errors.append("finding impact level is unresolved")
        if not self.impact.consequence.strip():
            errors.append("finding impact consequence is empty")

        impact_evidence = set(self.impact.evidence_ids)
        if not impact_evidence:
            errors.append("finding impact requires canonical evidence IDs")
        elif not impact_evidence.issubset(trace_evidence_ids):
            errors.append("finding impact evidence must be grounded in the causal trace")
        if self.impact.level != ImpactLevel.UNKNOWN and self.severity != self.impact.level.value:
            errors.append("finding severity must match the canonical impact level")
        return errors

    def as_report_data(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "impact": {
                "level": self.impact.level.value,
                "asset_at_risk": self.impact.asset_at_risk,
                "consequence": self.impact.consequence,
                "prerequisites": list(self.impact.prerequisites),
                "evidence_ids": list(self.impact.evidence_ids),
            },
            "affected_components": list(self.affected_components),
            "evidence_ids": list(self.evidence_ids),
            "hypothesis_id": self.hypothesis_id,
            "poc_reference": self.poc_reference,
            "causal_chain_id": self.causal_chain_id,
            "audit_session_id": self.audit_session_id,
        }

    @classmethod
    def from_report_data(cls, payload: Mapping[str, object]) -> "Finding":
        """Rehydrate a persisted finding without silently substituting defaults."""
        if not isinstance(payload, Mapping):
            raise TypeError("finding report data must be a mapping")

        required = (
            "finding_id",
            "title",
            "summary",
            "severity",
            "impact",
            "affected_components",
            "evidence_ids",
            "hypothesis_id",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"persisted finding is missing required fields: {', '.join(missing)}")

        impact_payload = payload["impact"]
        if not isinstance(impact_payload, Mapping):
            raise TypeError("persisted finding impact must be a mapping")
        impact_required = ("level", "asset_at_risk", "consequence", "prerequisites", "evidence_ids")
        missing_impact = [key for key in impact_required if key not in impact_payload]
        if missing_impact:
            raise ValueError(
                f"persisted finding impact is missing required fields: {', '.join(missing_impact)}"
            )

        try:
            impact_level = ImpactLevel(str(impact_payload["level"]))
        except ValueError as exc:
            raise ValueError(f"persisted finding impact level is not canonical: {impact_payload['level']}") from exc

        def tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
            if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
                raise TypeError(f"persisted finding {field_name} must be a sequence of strings")
            return tuple(value)

        finding_id = payload["finding_id"]
        title = payload["title"]
        summary = payload["summary"]
        severity = payload["severity"]
        hypothesis_id = payload["hypothesis_id"]
        if not all(isinstance(value, str) for value in (finding_id, title, summary, severity, hypothesis_id)):
            raise TypeError("persisted finding identity and report fields must be strings")
        if severity not in {level.value for level in ImpactLevel}:
            raise ValueError(f"persisted finding severity is not canonical: {severity}")
        if impact_level == ImpactLevel.UNKNOWN:
            raise ValueError("persisted finding impact level is unresolved")
        if not isinstance(impact_payload["consequence"], str) or not impact_payload["consequence"].strip():
            raise ValueError("persisted finding impact consequence is empty")
        if severity != impact_level.value:
            raise ValueError("persisted finding severity must match the canonical impact level")

        prerequisites = tuple_of_strings(impact_payload["prerequisites"], "impact prerequisites")
        impact_evidence_ids = tuple_of_strings(impact_payload["evidence_ids"], "impact evidence IDs")
        affected_components = tuple_of_strings(payload["affected_components"], "affected components")
        evidence_ids = tuple_of_strings(payload["evidence_ids"], "evidence IDs")

        asset_at_risk = impact_payload["asset_at_risk"]
        consequence = impact_payload["consequence"]
        if not isinstance(asset_at_risk, str) or not isinstance(consequence, str):
            raise TypeError("persisted finding impact asset and consequence must be strings")

        optional = {}
        for field_name in ("poc_reference", "causal_chain_id", "audit_session_id"):
            value = payload.get(field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"persisted finding {field_name} must be a string or null")
            optional[field_name] = value

        return cls(
            finding_id=finding_id,
            title=title,
            summary=summary,
            severity=severity,
            impact=ImpactAssessment(
                level=impact_level,
                asset_at_risk=asset_at_risk,
                consequence=consequence,
                prerequisites=prerequisites,
                evidence_ids=impact_evidence_ids,
            ),
            affected_components=affected_components,
            evidence_ids=evidence_ids,
            hypothesis_id=hypothesis_id,
            **optional,
        )
