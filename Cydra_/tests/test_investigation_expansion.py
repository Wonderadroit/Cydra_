import time

import pytest

from cydra.investigation_control import (
    InvestigationBudget,
    InvestigationController,
    InvestigationLease,
    InvestigationScope,
)
from cydra.investigation_expansion import (
    BudgetDepthExpansionGrant,
    DependencyCandidate,
    DependencyDecision,
    DependencyExpansionDecision,
    DependencyExpansionGrant,
    DependencyNeed,
    build_dependency_expansion_request,
    apply_dependency_decision,
    apply_budget_depth_expansion,
    authorize_dependency_expansion,
    dependency_requires_expansion,
)


def make_controller():
    now = time.time()
    return InvestigationController(
        "investigation:expansion",
        InvestigationScope("scope:expansion", allowed_observations=frozenset({"root"})),
        InvestigationBudget(max_rounds=2, max_observations=2, max_planning_steps=2, max_hypotheses=2, max_execution_cost=2, max_dependency_depth=1, max_branching_factor=2),
        InvestigationLease("lease:expansion", now - 1, now + 1000, generation=1),
    )


def test_dependency_expansion_requires_external_authorization():
    c = make_controller()
    candidate = DependencyCandidate("dep:1", "contract:A", "contract:B", "call", authorized=False, depth=1)
    grant = DependencyExpansionGrant("grant:1", c.authority_fingerprint, frozenset({"dep_read"}), frozenset({"dep:1"}), 2, "authority:1")
    with pytest.raises(PermissionError, match="self-authorize"):
        authorize_dependency_expansion(c, [candidate], grant=grant)
    assert c.scope.allowed_observations == frozenset({"root"})


def test_authorized_dependency_expansion_updates_scope_and_depth():
    c = make_controller()
    candidate = DependencyCandidate("dep:1", "contract:A", "contract:B", "call", authorized=True, depth=2)
    grant = DependencyExpansionGrant("grant:1", c.authority_fingerprint, frozenset({"dep_read"}), frozenset({"dep:1"}), 2, "authority:1")
    authorize_dependency_expansion(c, [candidate], grant=grant)
    assert "dep_read" in c.scope.allowed_observations
    assert c.budget.max_dependency_depth == 2


def test_dependency_discovery_request_has_no_authority_effect():
    c = make_controller()
    candidate = DependencyCandidate("dep:req", "contract:A", "contract:B", "router", authorized=False, depth=2)
    before = c.authority_fingerprint
    request = build_dependency_expansion_request(
        c,
        [candidate],
        request_id="request:req",
        dependency_ids=frozenset({"dep:req"}),
        requested_observations=frozenset({"dep_read"}),
        requested_max_dependency_depth=2,
    )
    assert request.parent_authority_fingerprint == before
    assert c.authority_fingerprint == before
    assert "dep_read" not in c.scope.allowed_observations


def test_dependency_denial_is_explicit_and_cannot_carry_a_grant():
    c = make_controller()
    candidate = DependencyCandidate("dep:deny", "contract:A", "contract:B", "oracle", authorized=False, depth=2)
    request = build_dependency_expansion_request(
        c, [candidate], request_id="request:deny", dependency_ids=frozenset({"dep:deny"}),
        requested_observations=frozenset({"oracle_read"}), requested_max_dependency_depth=2,
    )
    decision = DependencyExpansionDecision("decision:deny", request.fingerprint, DependencyDecision.DENIED, "authority:1", "out of scope")
    apply_dependency_decision(c, request, decision, candidates=[candidate])
    assert "oracle_read" not in c.scope.allowed_observations
    grant = DependencyExpansionGrant("grant:deny", c.authority_fingerprint, frozenset({"oracle_read"}), frozenset({"dep:deny"}), 2, "authority:1")
    with pytest.raises(PermissionError, match="denied"):
        apply_dependency_decision(c, request, decision, candidates=[candidate], grant=grant)


def test_dependency_approval_requires_exact_request_and_external_grant():
    c = make_controller()
    discovered = DependencyCandidate("dep:approve", "contract:A", "contract:B", "router", authorized=False, depth=2)
    request = build_dependency_expansion_request(
        c, [discovered], request_id="request:approve", dependency_ids=frozenset({"dep:approve"}),
        requested_observations=frozenset({"dep_read"}), requested_max_dependency_depth=2,
    )
    decision = DependencyExpansionDecision("decision:approve", request.fingerprint, DependencyDecision.APPROVED, "authority:1")
    with pytest.raises(PermissionError, match="requires an externally issued grant"):
        apply_dependency_decision(c, request, decision, candidates=[discovered])

    authorized = DependencyCandidate("dep:approve", "contract:A", "contract:B", "router", authorized=True, depth=2)
    grant = DependencyExpansionGrant("grant:approve", c.authority_fingerprint, frozenset({"dep_read"}), frozenset({"dep:approve"}), 2, "authority:1")
    apply_dependency_decision(c, request, decision, candidates=[authorized], grant=grant)
    assert "dep_read" in c.scope.allowed_observations


def test_dependency_approval_rejects_tampered_request_fingerprint():
    c = make_controller()
    candidate = DependencyCandidate("dep:tamper", "contract:A", "contract:B", "router", authorized=False, depth=2)
    request = build_dependency_expansion_request(
        c, [candidate], request_id="request:tamper", dependency_ids=frozenset({"dep:tamper"}),
        requested_observations=frozenset({"dep_read"}), requested_max_dependency_depth=2,
    )
    decision = DependencyExpansionDecision("decision:tamper", "forged", DependencyDecision.APPROVED, "authority:1")
    with pytest.raises(PermissionError, match="exact expansion request"):
        apply_dependency_decision(c, request, decision, candidates=[candidate])


def test_stale_dependency_grant_cannot_apply_after_authority_changes():
    c = make_controller()
    grant = DependencyExpansionGrant("grant:stale", c.authority_fingerprint, frozenset({"dep_read"}), frozenset(), 2, "authority:1")
    c.scope = InvestigationScope("scope:expansion", allowed_observations=frozenset({"root", "changed"}))
    with pytest.raises(PermissionError, match="stale"):
        authorize_dependency_expansion(c, [], grant=grant)


def test_budget_expansion_requires_an_absolute_ceiling():
    c = make_controller()
    grant = BudgetDepthExpansionGrant(
        "grant:budget", c.authority_fingerprint, "authority:1",
        additional_observations=5, additional_dependency_depth=3,
        ceiling_observations=4, ceiling_dependency_depth=3,
    )
    with pytest.raises(PermissionError, match="ceiling"):
        apply_budget_depth_expansion(c, grant)
    assert c.budget.max_observations == 2


def test_budget_expansion_can_be_applied_only_from_current_authority():
    c = make_controller()
    grant = BudgetDepthExpansionGrant(
        "grant:budget-ok", c.authority_fingerprint, "authority:1",
        additional_observations=2, additional_dependency_depth=2,
        ceiling_observations=4, ceiling_dependency_depth=3,
    )
    apply_budget_depth_expansion(c, grant)
    assert c.budget.max_observations == 4
    assert c.budget.max_dependency_depth == 3


def test_controller_consumes_dependency_grant_once_and_records_it():
    c = make_controller()
    candidate = DependencyCandidate("dep:consume", "contract:A", "contract:B", "call", authorized=True, depth=2)
    grant = DependencyExpansionGrant("grant:consume", c.authority_fingerprint, frozenset({"dep_read"}), frozenset({"dep:consume"}), 2, "authority:1")
    c.apply_dependency_expansion([candidate], grant=grant)
    assert "grant:consume" in c.consumed_expansion_grant_ids
    assert "dep_read" in c.scope.allowed_observations
    with pytest.raises(PermissionError, match="already been consumed"):
        c.apply_dependency_expansion([candidate], grant=grant)


def test_controller_consumes_budget_grant_once_and_records_it():
    c = make_controller()
    grant = BudgetDepthExpansionGrant(
        "grant:budget-consume", c.authority_fingerprint, "authority:1",
        additional_observations=1, ceiling_observations=3,
    )
    c.apply_budget_depth_expansion(grant)
    assert "grant:budget-consume" in c.consumed_expansion_grant_ids
    with pytest.raises(PermissionError, match="already been consumed"):
        c.apply_budget_depth_expansion(grant)


def test_consumed_expansion_state_survives_snapshot_recovery():
    c = make_controller()
    grant = BudgetDepthExpansionGrant(
        "grant:snapshot", c.authority_fingerprint, "authority:1",
        additional_observations=1, ceiling_observations=3,
    )
    c.apply_budget_depth_expansion(grant)
    snapshot = c.snapshot()
    recovered = InvestigationController.from_snapshot(
        snapshot,
        expected_authority_fingerprint=c.authority_fingerprint,
    )
    assert recovered.consumed_expansion_grant_ids == {"grant:snapshot"}
    with pytest.raises(PermissionError, match="already been consumed"):
        recovered.apply_budget_depth_expansion(grant)


def test_already_authorized_dependency_requires_no_expansion():
    candidate = DependencyCandidate(
        "dep:in-scope", "contract:A", "contract:B", "call", authorized=True,
        need=DependencyNeed.ACTIVE_INVESTIGATION,
    )
    assert candidate.can_be_used_without_expansion is True
    assert candidate.requires_scope_expansion is False
    assert dependency_requires_expansion(candidate) is False


def test_context_only_out_of_scope_dependency_requires_no_expansion():
    candidate = DependencyCandidate(
        "dep:context", "contract:A", "contract:B", "import", authorized=False,
        need=DependencyNeed.CONTEXT_ONLY,
    )
    assert candidate.can_be_used_without_expansion is True
    assert candidate.requires_scope_expansion is False
    assert dependency_requires_expansion(candidate) is False


def test_out_of_scope_active_dependency_requires_expansion():
    candidate = DependencyCandidate(
        "dep:active", "contract:A", "contract:B", "router", authorized=False,
        need=DependencyNeed.ACTIVE_INVESTIGATION,
    )
    assert candidate.can_be_used_without_expansion is False
    assert candidate.requires_scope_expansion is True
    assert dependency_requires_expansion(candidate) is True


def test_context_only_dependency_cannot_be_turned_into_expansion_request():
    c = make_controller()
    candidate = DependencyCandidate(
        "dep:context-request", "contract:A", "contract:B", "import", authorized=False,
        need=DependencyNeed.CONTEXT_ONLY,
    )
    with pytest.raises(PermissionError, match="context-only"):
        build_dependency_expansion_request(
            c, [candidate], request_id="request:context",
            dependency_ids=frozenset({"dep:context-request"}),
            requested_observations=frozenset({"dep_read"}),
            requested_max_dependency_depth=1,
        )
