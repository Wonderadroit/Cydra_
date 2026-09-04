from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ImpactAssessment:
    level: ImpactLevel
    asset_at_risk: str
    consequence: str
    prerequisites: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @property
    def assessed(self) -> bool:
        return self.level != ImpactLevel.UNKNOWN and bool(self.consequence.strip())


def assess_impact(
    *,
    level: ImpactLevel,
    asset_at_risk: str,
    consequence: str,
    prerequisites: tuple[str, ...] = (),
    evidence_ids: tuple[str, ...] = (),
) -> ImpactAssessment:
    return ImpactAssessment(level, asset_at_risk, consequence, prerequisites, evidence_ids)
