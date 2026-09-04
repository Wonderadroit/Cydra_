import pytest

from cydra.scope import ScopePolicy, ScopeRule, ScopeState, ScopeViolation


def test_out_of_scope_nodes_are_pruned():
    policy = ScopePolicy(
        rules=[
            ScopeRule("src/**", ScopeState.IN_SCOPE, "authorized source"),
            ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE, "excluded test material"),
        ]
    )

    assert policy.decide("tests/test_auth.py").allowed_for_active_testing is False
    assert policy.decide("tests/test_auth.py").state is ScopeState.OUT_OF_SCOPE
    assert policy.decide("src/auth.py").allowed_for_active_testing is True


def test_unknown_scope_fails_closed():
    policy = ScopePolicy(rules=[], default_state=ScopeState.UNKNOWN)
    decision = policy.decide("unknown/path.py")
    assert decision.state is ScopeState.UNKNOWN
    assert decision.allowed_for_active_testing is False

    with pytest.raises(ScopeViolation):
        policy.require_active_testing("unknown/path.py")


def test_conditional_scope_requires_conditions():
    policy = ScopePolicy(
        rules=[
            ScopeRule(
                "integration/**",
                ScopeState.CONDITIONAL,
                "allowed only in approved environment",
                ("approved-environment",),
            )
        ]
    )

    blocked = policy.decide("integration/api.py")
    assert blocked.allowed_for_active_testing is False
    assert blocked.unresolved_conditions == ("approved-environment",)

    allowed = policy.decide("integration/api.py", ["approved-environment"])
    assert allowed.allowed_for_active_testing is True


def test_scope_decision_is_explicit_for_recon_nodes():
    policy = ScopePolicy(
        rules=[ScopeRule("vendor/**", ScopeState.OUT_OF_SCOPE, "dependency boundary")]
    )
    decision = policy.decide("vendor/library.py")
    assert decision.matched_rule == "vendor/**"
    assert decision.reason == "dependency boundary"
