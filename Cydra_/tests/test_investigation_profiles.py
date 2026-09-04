import pytest

from cydra.investigation_profiles import (
    CapabilityProfile,
    InvestigationCapability,
    InvestigationProfile,
)


def test_profiles_are_explicit_and_deterministic():
    standard = CapabilityProfile.for_profile(InvestigationProfile.STANDARD)
    combined = CapabilityProfile.for_profile("COMBINED")
    assert not standard.supports(InvestigationCapability.ECONOMIC)
    assert combined.supports("economic")
    assert combined.supports("cross_contract")
    assert combined.supports("deep_analysis")
    assert combined.fingerprint() == CapabilityProfile.for_profile("COMBINED").fingerprint()


def test_profile_never_escalates_authority():
    standard = CapabilityProfile.for_profile("STANDARD")
    with pytest.raises(PermissionError, match="does not enable"):
        standard.require("economic")
    assert not standard.supports("cross_contract")


def test_economic_profile_does_not_implicitly_enable_expansion_or_deep_analysis():
    economic = CapabilityProfile.for_profile("ECONOMIC")
    economic.require("economic")
    with pytest.raises(PermissionError):
        economic.require("cross_contract")
    with pytest.raises(PermissionError):
        economic.require("deep_analysis")
