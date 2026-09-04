"""Evidence-gated security-claim reasoning over canonical CYDRA state."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .finding_gate import FindingCandidate
from .finding_synthesis import ReasoningFindingDraft
from .impact import ImpactAssessment, ImpactLevel
from .reasoning_graph import ReasoningGraph
from .security_predicate import verify_security_predicate


class ClaimDecision(str, Enum):
    EMITTED = "emitted"
    UNRESOLVED = "unresolved"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SecurityClaimRule:
    """An explicit semantic claim contract evaluated against canonical graph state."""
    finding_id: str
    title: str
    summary: str
    severity: str
    impact: ImpactAssessment
    affected_components: tuple[str, ...]
    hypothesis_id: str
    causal_chain_id: str
    evidence_ids: tuple[str, ...]
    candidate: FindingCandidate
    required_invariant_ids: tuple[str, ...] = ()
    predicate_id: str = ""
    audit_session_id: str | None = None
    competing_hypothesis_id: str = ""

    def __post_init__(self) -> None:
        for name in ("finding_id", "title", "summary", "hypothesis_id", "causal_chain_id", "predicate_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not self.evidence_ids:
            raise ValueError("security claim requires evidence IDs")
        if not self.affected_components:
            raise ValueError("security claim requires affected components")
        if not self.required_invariant_ids:
            raise ValueError("security claim requires at least one canonical invariant")


@dataclass(frozen=True)
class SecurityClaimResult:
    decision: ClaimDecision
    reasons: tuple[str, ...] = ()
    draft: ReasoningFindingDraft | None = None


class SecurityClaimReasoner:
    """Conservatively adjudicate explicit security claims from canonical state."""
    def evaluate(self, graph: ReasoningGraph, rules: Iterable[SecurityClaimRule]) -> tuple[SecurityClaimResult, ...]:
        if not isinstance(graph, ReasoningGraph):
            raise TypeError("security-claim reasoning requires the canonical ReasoningGraph")
        graph_errors = graph.validate()
        if graph_errors:
            return tuple(SecurityClaimResult(ClaimDecision.BLOCKED, ("canonical reasoning graph is invalid",)) for _ in rules)
        results: list[SecurityClaimResult] = []
        seen: set[str] = set()
        for rule in rules:
            if not isinstance(rule, SecurityClaimRule):
                raise TypeError("security-claim rules must use SecurityClaimRule")
            if rule.finding_id in seen:
                results.append(SecurityClaimResult(ClaimDecision.BLOCKED, ("duplicate finding claim ID",)))
                continue
            seen.add(rule.finding_id)
            results.append(self._evaluate_one(graph, rule))
        return tuple(results)

    def _evaluate_one(self, graph: ReasoningGraph, rule: SecurityClaimRule) -> SecurityClaimResult:
        hypothesis = graph.model.nodes.get(rule.hypothesis_id)
        if hypothesis is None or hypothesis.kind != "hypothesis":
            return self._blocked("claim hypothesis is not canonical")
        if hypothesis.attributes.get("state") != "supported":
            state = hypothesis.attributes.get("state", "unknown")
            if state == "contradicted":
                return self._blocked("claim hypothesis is contradicted")
            return self._unresolved("claim hypothesis is not supported")

        if rule.competing_hypothesis_id:
            competing = graph.model.nodes.get(rule.competing_hypothesis_id)
            if competing is None or competing.kind != "hypothesis":
                return self._blocked("competing claim hypothesis is not canonical")
            bindings = [e for e in graph.model.edges if e.source == rule.hypothesis_id and e.relation == "competes_with" and e.target == rule.competing_hypothesis_id]
            if len(bindings) != 1:
                return self._blocked("claim competing hypothesis is not canonically bound")
            state = competing.attributes.get("state", "unknown")
            if state == "supported":
                return self._unresolved("competing claim hypothesis remains supported")
            if state == "unresolved":
                return self._unresolved("competing claim hypothesis remains unresolved")
            if state != "contradicted":
                return self._unresolved("competing claim hypothesis has no resolving state")

        predicate = graph.model.nodes.get(rule.predicate_id)
        if predicate is None or predicate.kind != "security_predicate":
            return self._blocked("security predicate is not canonical")
        if predicate.attributes.get("hypothesis_id") != rule.hypothesis_id:
            return self._blocked("security predicate is bound to the wrong claim hypothesis")
        predicate_invariants = predicate.attributes.get("invariant_ids")
        if not isinstance(predicate_invariants, list) or set(predicate_invariants) != set(rule.required_invariant_ids):
            return self._blocked("security predicate invariant binding does not match the claim")
        if predicate.attributes.get("causal_chain_id") != rule.causal_chain_id:
            return self._blocked("security predicate is bound to the wrong causal trace")

        pv = verify_security_predicate(graph, rule.predicate_id, rule.hypothesis_id, rule.required_invariant_ids, rule.causal_chain_id)
        if not pv.verified:
            reason = pv.reasons[0] if pv.reasons else "security predicate verification failed"
            if "not supported" in reason or "unresolved" in reason:
                return self._unresolved(reason)
            return self._blocked(reason)
        for invariant_id in rule.required_invariant_ids:
            if any(e.source == invariant_id and e.target == rule.hypothesis_id and e.relation == "contradicts" for e in graph.model.edges):
                return self._blocked(f"required invariant contradicts claim hypothesis: {invariant_id}")
        trace_edges = [e for e in graph.model.edges if e.source == rule.predicate_id and e.relation == "verified_by_trace" and e.target == rule.causal_chain_id]
        if len(trace_edges) != 1:
            return self._blocked("security predicate is not uniquely bound to the exact causal trace")
        from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
        verification = verify_persisted_causal_chain(graph.model, rule.causal_chain_id)
        if verification.state == CausalVerificationState.REJECTED:
            return self._blocked(f"causal verification rejected: {verification.reasons[0] if verification.reasons else 'causal chain rejected'}")
        if verification.state == CausalVerificationState.UNRESOLVED:
            return self._unresolved(f"causal verification unresolved: {verification.reasons[0] if verification.reasons else 'causal chain unresolved'}")
        if verification.trace is None:
            return self._blocked("verified causal chain has no trace")
        if verification.trace.hypothesis_id != rule.hypothesis_id:
            return self._blocked("causal chain does not match claim hypothesis")
        trace_evidence = set(verification.evidence_ids)
        if not set(rule.evidence_ids).issubset(trace_evidence):
            return self._blocked("claim evidence is not fully grounded in the verified causal trace")
        if not set(rule.impact.evidence_ids).issubset(trace_evidence):
            return self._blocked("claim impact evidence is not fully grounded in the verified causal trace")
        unsupported = [eid for eid in rule.evidence_ids if not any(e.source == eid and e.relation == "supports" and e.target == rule.hypothesis_id for e in graph.model.edges)]
        if unsupported:
            return self._blocked("claim evidence does not explicitly support the claim hypothesis: " + ", ".join(unsupported))
        if rule.impact.level == ImpactLevel.UNKNOWN or not rule.impact.consequence.strip():
            return self._unresolved("security claim impact is unresolved")
        if rule.severity.upper() != rule.impact.level.value:
            return self._blocked("claim severity does not match canonical impact level")
        if not rule.candidate.in_scope:
            return self._blocked("claim target is out of scope")
        if not rule.candidate.hypothesis_resolved:
            return self._unresolved("finding candidate hypothesis remains unresolved")
        draft = ReasoningFindingDraft(finding_id=rule.finding_id, title=rule.title, summary=rule.summary, severity=rule.severity.upper(), impact=rule.impact, affected_components=rule.affected_components, evidence_ids=rule.evidence_ids, hypothesis_id=rule.hypothesis_id, causal_chain_id=rule.causal_chain_id, candidate=rule.candidate, audit_session_id=rule.audit_session_id)
        return SecurityClaimResult(ClaimDecision.EMITTED, (), draft)

    @staticmethod
    def _blocked(reason: str) -> SecurityClaimResult:
        return SecurityClaimResult(ClaimDecision.BLOCKED, (reason,))

    @staticmethod
    def _unresolved(reason: str) -> SecurityClaimResult:
        return SecurityClaimResult(ClaimDecision.UNRESOLVED, (reason,))


def _claim_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"security claim {field} must be a non-empty string")
    return value.strip()


def _claim_strings(value: object, field: str, *, required: bool = True) -> tuple[str, ...]:
    if value is None and not required:
        return ()
    if not isinstance(value, (list, tuple)) or (required and not value):
        raise ValueError(f"security claim {field} must be a non-empty sequence of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"security claim {field} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _rule_from_hypothesis(graph: ReasoningGraph, hypothesis_id: str, causal_chain_id: str) -> SecurityClaimRule | None:
    hypothesis = graph.model.nodes.get(hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        return None
    claim = hypothesis.attributes.get("security_claim")
    if not isinstance(claim, dict) or claim.get("claim_kind", "finding") != "finding":
        return None
    required_invariants = _claim_strings(claim.get("required_invariant_ids", claim.get("invariant_ids")), "required_invariant_ids")
    evidence_ids = _claim_strings(claim.get("evidence_ids"), "evidence_ids")
    impact_evidence_ids = _claim_strings(claim.get("impact_evidence_ids", evidence_ids), "impact_evidence_ids")
    affected_components = _claim_strings(claim.get("affected_components"), "affected_components")
    predicate_id = _claim_text(claim.get("predicate_id"), "predicate_id")
    severity = _claim_text(claim.get("severity"), "severity").upper()
    try:
        impact_level = ImpactLevel(severity)
    except ValueError as exc:
        raise ValueError(f"security claim severity is not canonical: {severity}") from exc
    if impact_level == ImpactLevel.UNKNOWN:
        raise ValueError("security claim severity cannot be UNKNOWN")
    declared_chain = claim.get("causal_chain_id")
    if declared_chain is not None and declared_chain != causal_chain_id:
        raise ValueError("security claim causal chain does not match verified trace")
    prerequisites = _claim_strings(claim.get("prerequisites", ()), "prerequisites", required=False)
    candidate = FindingCandidate(in_scope=bool(claim.get("in_scope", False)), known_issue=bool(claim.get("known_issue", False)), evidence=True, reproducible=bool(claim.get("reproducible", False)), causal_verified=True, impact_assessed=True, hypothesis_resolved=bool(claim.get("hypothesis_resolved", True)))
    impact = ImpactAssessment(impact_level, _claim_text(claim.get("asset_at_risk"), "asset_at_risk"), _claim_text(claim.get("consequence"), "consequence"), prerequisites, impact_evidence_ids)
    competing_id = claim.get("competing_hypothesis_id", "")
    if competing_id is not None and not isinstance(competing_id, str):
        raise ValueError("security claim competing_hypothesis_id must be a string")
    return SecurityClaimRule(finding_id=_claim_text(claim.get("finding_id"), "finding_id"), title=_claim_text(claim.get("title"), "title"), summary=_claim_text(claim.get("summary"), "summary"), severity=severity, impact=impact, affected_components=affected_components, hypothesis_id=hypothesis_id, causal_chain_id=causal_chain_id, evidence_ids=evidence_ids, candidate=candidate, required_invariant_ids=required_invariants, predicate_id=predicate_id, audit_session_id=claim.get("audit_session_id") if isinstance(claim.get("audit_session_id"), str) else None, competing_hypothesis_id=competing_id or "")


class SecurityClaimDraftProvider:
    """Autonomous-driver adapter for evidence-gated security claims."""
    def __init__(self, max_claims: int = 16) -> None:
        if max_claims < 1:
            raise ValueError("max_claims must be positive")
        self.max_claims = max_claims
        self.reasoner = SecurityClaimReasoner()

    def propose(self, model, step) -> tuple[ReasoningFindingDraft, ...]:
        if not isinstance(model, ReasoningGraph):
            raise TypeError("security claim provider requires the canonical ReasoningGraph")
        rules: list[SecurityClaimRule] = []
        seen: set[str] = set()
        for node in sorted(model.model.nodes.values(), key=lambda item: item.node_id):
            if node.kind != "causal_chain":
                continue
            for edge in model.model.edges:
                if edge.relation != "motivates" or edge.target != node.node_id or edge.source in seen:
                    continue
                rule = _rule_from_hypothesis(model, edge.source, node.node_id)
                if rule is None:
                    continue
                rules.append(rule)
                seen.add(edge.source)
                if len(rules) >= self.max_claims:
                    break
            if len(rules) >= self.max_claims:
                break
        results = self.reasoner.evaluate(model, rules)
        return tuple(result.draft for result in results if result.decision == ClaimDecision.EMITTED and result.draft is not None)
