"""Explicit investigation capability profiles.

Profiles select reasoning capabilities; they are policy labels, not authority.
A profile can require a capability, but it can never mint scope, budget, depth,
lease, execution rights, or an expansion grant. The live InvestigationController
remains the sole authority boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


class InvestigationCapability(str, Enum):
    ECONOMIC = "economic"
    CROSS_CONTRACT = "cross_contract"
    DEEP_ANALYSIS = "deep_analysis"


class InvestigationProfile(str, Enum):
    STANDARD = "STANDARD"
    ECONOMIC = "ECONOMIC"
    CROSS_CONTRACT = "CROSS_CONTRACT"
    DEEP_ANALYSIS = "DEEP_ANALYSIS"
    COMBINED = "COMBINED"


@dataclass(frozen=True)
class CapabilityProfile:
    """A deterministic reasoning-policy preset with no authority semantics."""

    profile: InvestigationProfile
    capabilities: FrozenSet[InvestigationCapability]

    @classmethod
    def for_profile(cls, profile: InvestigationProfile | str) -> "CapabilityProfile":
        profile = InvestigationProfile(profile)
        mapping = {
            InvestigationProfile.STANDARD: frozenset(),
            InvestigationProfile.ECONOMIC: frozenset({InvestigationCapability.ECONOMIC}),
            InvestigationProfile.CROSS_CONTRACT: frozenset({InvestigationCapability.CROSS_CONTRACT}),
            InvestigationProfile.DEEP_ANALYSIS: frozenset({InvestigationCapability.DEEP_ANALYSIS}),
            InvestigationProfile.COMBINED: frozenset({
                InvestigationCapability.ECONOMIC,
                InvestigationCapability.CROSS_CONTRACT,
                InvestigationCapability.DEEP_ANALYSIS,
            }),
        }
        return cls(profile, mapping[profile])

    def supports(self, capability: InvestigationCapability | str) -> bool:
        return InvestigationCapability(capability) in self.capabilities

    def require(self, capability: InvestigationCapability | str) -> None:
        capability = InvestigationCapability(capability)
        if capability not in self.capabilities:
            raise PermissionError(f"investigation profile {self.profile.value} does not enable {capability.value}")

    def fingerprint(self) -> str:
        import hashlib
        import json

        payload = {
            "profile": self.profile.value,
            "capabilities": sorted(capability.value for capability in self.capabilities),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
