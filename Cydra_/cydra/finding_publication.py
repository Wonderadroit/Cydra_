"""Trusted publication boundary for canonical CYDRA findings.

Publication data follows an explicit trust transition:

    UNTRUSTED TRANSPORT -> STRICT PARSE -> CANONICAL VERIFICATION -> TRUSTED PUBLICATION

Parsing a valid envelope never produces a trusted publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .finding import Finding
from .finding_recovery import rehydrate_persisted_finding
from .reproducibility import ReproducibilityManifest, build_reproducibility_manifest, verify_reproducibility_manifest
from .reasoning_graph import ReasoningGraph

_PUBLICATION_KEYS = {"finding", "manifest"}
_FINDING_KEYS = {"finding_id", "title", "summary", "severity", "impact", "affected_components", "evidence_ids", "hypothesis_id", "poc_reference", "causal_chain_id", "audit_session_id"}
_IMPACT_KEYS = {"level", "asset_at_risk", "consequence", "prerequisites", "evidence_ids"}
_MANIFEST_KEYS = {"schema", "finding_id", "audit_session_id", "evidence_ids", "impact_evidence_ids", "hypothesis_id", "causal_chain_id", "graph_fingerprint", "claim_fingerprint", "reasoning_node_ids", "audit_history_fingerprint"}


@dataclass(frozen=True)
class FindingPublication:
    finding: Finding
    manifest: ReproducibilityManifest

    def as_dict(self) -> dict[str, Any]: return {"finding": self.finding.as_report_data(), "manifest": self.manifest.as_dict()}
    @classmethod
    def _from_verified(cls, finding: Finding, manifest: ReproducibilityManifest) -> "FindingPublication": return cls(finding, manifest)


@dataclass(frozen=True)
class UntrustedFindingPublication:
    finding: Finding
    manifest: ReproducibilityManifest

    def as_dict(self) -> dict[str, Any]: return {"finding": self.finding.as_report_data(), "manifest": self.manifest.as_dict()}

    def verify(self, graph: ReasoningGraph) -> FindingPublication:
        errors = _verify_finding_publication_parts(graph, self.finding, self.manifest)
        if errors: raise ValueError("finding publication verification failed: " + "; ".join(errors))
        canonical = rehydrate_persisted_finding(graph, self.finding.finding_id)
        return FindingPublication._from_verified(canonical, build_reproducibility_manifest(graph, canonical))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "UntrustedFindingPublication":
        if not isinstance(payload, Mapping): raise TypeError("finding publication must be a mapping")
        if set(payload) != _PUBLICATION_KEYS: raise ValueError("finding publication must contain exactly finding and manifest")
        finding_payload, manifest_payload = payload["finding"], payload["manifest"]
        if not isinstance(finding_payload, Mapping): raise TypeError("finding publication finding must be a mapping")
        if not isinstance(manifest_payload, Mapping): raise TypeError("finding publication manifest must be a mapping")
        if set(finding_payload) != _FINDING_KEYS: raise ValueError("finding publication finding has an unsupported schema shape")
        impact_payload = finding_payload.get("impact")
        if not isinstance(impact_payload, Mapping) or set(impact_payload) != _IMPACT_KEYS: raise ValueError("finding publication impact has an unsupported schema shape")
        if set(manifest_payload) != _MANIFEST_KEYS: raise ValueError("finding publication manifest has an unsupported schema shape")
        def string(value: object, field: str, allow_none: bool = False) -> str | None:
            if value is None and allow_none: return None
            if not isinstance(value, str): raise TypeError(f"manifest {field} must be a string")
            return value
        def sequence(value: object, field: str) -> tuple[str, ...]:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value): raise TypeError(f"manifest {field} must be a list of strings")
            return tuple(value)
        manifest = ReproducibilityManifest(schema=string(manifest_payload["schema"], "schema") or "", finding_id=string(manifest_payload["finding_id"], "finding_id") or "", audit_session_id=string(manifest_payload["audit_session_id"], "audit_session_id", True), evidence_ids=sequence(manifest_payload["evidence_ids"], "evidence_ids"), impact_evidence_ids=sequence(manifest_payload["impact_evidence_ids"], "impact_evidence_ids"), hypothesis_id=string(manifest_payload["hypothesis_id"], "hypothesis_id") or "", causal_chain_id=string(manifest_payload["causal_chain_id"], "causal_chain_id") or "", graph_fingerprint=string(manifest_payload["graph_fingerprint"], "graph_fingerprint") or "", claim_fingerprint=string(manifest_payload["claim_fingerprint"], "claim_fingerprint") or "", reasoning_node_ids=sequence(manifest_payload["reasoning_node_ids"], "reasoning_node_ids"), audit_history_fingerprint=string(manifest_payload["audit_history_fingerprint"], "audit_history_fingerprint") or "")
        return cls(Finding.from_report_data(finding_payload), manifest)


def build_finding_publication(graph: ReasoningGraph, finding_id: str) -> FindingPublication:
    canonical = rehydrate_persisted_finding(graph, finding_id)
    return FindingPublication._from_verified(canonical, build_reproducibility_manifest(graph, canonical))


def _verify_finding_publication_parts(graph: ReasoningGraph, finding: Finding, manifest: ReproducibilityManifest) -> list[str]:
    try:
        canonical = rehydrate_persisted_finding(graph, finding.finding_id)
    except (KeyError, TypeError, ValueError) as exc:
        detail = exc.args[0] if exc.args and isinstance(exc.args[0], str) else str(exc)
        return [f"canonical finding recovery failed: {detail}"]
    errors: list[str] = []
    if canonical != finding: errors.append("published finding claims do not match canonical persisted finding")
    errors.extend(verify_reproducibility_manifest(graph, canonical, manifest))
    return errors


def verify_finding_publication(graph: ReasoningGraph, publication: FindingPublication) -> list[str]:
    if not isinstance(publication, FindingPublication): return ["publication must be a trusted FindingPublication"]
    return _verify_finding_publication_parts(graph, publication.finding, publication.manifest)


def verify_finding_publication_data(graph: ReasoningGraph, payload: Mapping[str, object]) -> list[str]:
    try: publication = UntrustedFindingPublication.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc: return [f"publication transport validation failed: {exc}"]
    return _verify_finding_publication_parts(graph, publication.finding, publication.manifest)


def verify_and_trust_finding_publication_data(graph: ReasoningGraph, payload: Mapping[str, object]) -> FindingPublication:
    return UntrustedFindingPublication.from_dict(payload).verify(graph)
