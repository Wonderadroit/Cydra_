from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class CausalLink:
    source: str
    relation: str
    target: str
    evidence_ids: List[str]


@dataclass(frozen=True)
class CausalAssessment:
    valid: bool
    links: List[CausalLink]
    missing_evidence: List[str]
    reason: str


def verify_causal_chain(links: Iterable[CausalLink]) -> CausalAssessment:
    """Validate that every causal link has explicit evidence provenance."""
    links = list(links)
    missing = [f"{l.source}->{l.target}" for l in links if not l.evidence_ids]
    if missing:
        return CausalAssessment(False, links, missing, "causal links require evidence provenance")
    if not links:
        return CausalAssessment(False, [], ["causal_chain"], "causal chain is empty")
    return CausalAssessment(True, links, [], "causal chain is evidence-backed")
