"""Canonical promotion boundary from reasoning output to benchmark findings.

This module deliberately does not discover vulnerabilities and does not consume
historical benchmark truth. It accepts findings already produced by CYDRA's
reasoning layer, routes them through the existing finding pipeline, and persists
only findings that pass the same causal/evidence/impact/provenance checks used by
normal audits.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .finding import Finding
from .finding_gate import FindingCandidate, GateDecision
from .finding_pipeline import promote_candidate
from .finding_persistence import persist_finding
from .reasoning_graph import ReasoningGraph


@dataclass(frozen=True)
class FindingPromotionCandidate:
    """One reasoning-produced finding plus its gate state inputs."""

    candidate: FindingCandidate
    finding: Finding


@dataclass(frozen=True)
class FindingPromotionAttempt:
    """Auditable result of attempting canonical finding promotion."""

    finding_id: str
    decision: GateDecision
    finding_fingerprint: str | None
    reasons: tuple[str, ...]


def finding_claim_fingerprint(finding: Finding) -> str:
    """Return the deterministic report-claim fingerprint used by persistence."""
    # Keep this serialization byte-for-byte aligned with finding_persistence's
    # canonical claim fingerprint. The fingerprint is a claim identity, not an
    # oracle identity, and therefore remains safe to compute during a blind run.
    payload = finding.as_report_data()
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def promote_reasoning_findings(
    graph: ReasoningGraph,
    candidates: Iterable[FindingPromotionCandidate],
) -> tuple[FindingPromotionAttempt, ...]:
    """Promote reasoning output through the canonical finding pipeline.

    No benchmark oracle is consulted here. The existing ``promote_candidate``
    function owns gate semantics; this adapter only adds benchmark-safe result
    serialization and persists a finding after the canonical pipeline returns
    ``READY``. No learning contribution is supplied, so benchmark promotion does
    not silently create benchmark-specific learning state.
    """
    if not isinstance(graph, ReasoningGraph):
        raise TypeError("finding promotion requires the canonical ReasoningGraph")

    attempts: list[FindingPromotionAttempt] = []
    for item in candidates:
        if not isinstance(item, FindingPromotionCandidate):
            raise TypeError("finding promotion candidates must use the canonical candidate type")
        finding = item.finding
        fingerprint = finding_claim_fingerprint(finding)
        result = promote_candidate(item.candidate, finding, graph)
        if result.decision == GateDecision.READY:
            try:
                persist_finding(graph, finding)
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                attempts.append(
                    FindingPromotionAttempt(
                        finding.finding_id,
                        GateDecision.BLOCKED,
                        fingerprint,
                        (f"finding persistence failed: {exc}",),
                    )
                )
                continue
        attempts.append(
            FindingPromotionAttempt(
                finding.finding_id,
                result.decision,
                fingerprint if result.decision == GateDecision.READY else None,
                tuple(result.reasons),
            )
        )
    return tuple(attempts)
