import time

import pytest

from cydra.dependency_authorization import (
    DependencyDecision,
    approve_dependency_request,
    create_dependency_request,
    decision_to_grant,
    deny_dependency_request,
)
from cydra.investigation_control import InvestigationBudget, InvestigationController, InvestigationLease, InvestigationScope
from cydra.investigation_expansion import DependencyCandidate


def candidate():
    return DependencyCandidate("dep:router", "contract:A", "router:B", "call", authorized=False, depth=2)


def request():
    now = time.time()
    controller = InvestigationController(
        "investigation:dep",
        InvestigationScope("scope:dep", allowed_observations=frozenset({"root"})),
        InvestigationBudget(max_rounds=2, max_observations=4, max_planning_steps=4, max_hypotheses=4, max_execution_cost=4, max_dependency_depth=2),
        InvestigationLease("lease:dep", now - 1, now + 1000, generation=1),
    )
    return controller, create_dependency_request(
        request_id="request:dep",
        investigation_id=controller.investigation_id,
        authority_fingerprint=controller.authority_fingerprint,
        candidates=(candidate(),),
        requested_observations=frozenset({"router_read"}),
        requested_max_depth=2,
    )


def test_discovery_request_does_not_authorize_scope():
    controller, req = request()
    assert "router_read" not in controller.scope.allowed_observations
    assert req.dependency_ids == frozenset({"dep:router"})


def test_external_deny_is_explicit_and_cannot_become_grant():
    _, req = request()
    decision = deny_dependency_request(req, decision_id="decision:deny", authority_id="authority:1", reason="out of scope")
    assert decision.decision == DependencyDecision.DENIED
    with pytest.raises(PermissionError, match="denied"):
        decision_to_grant(req, decision)


def test_exact_external_approval_converts_to_existing_grant_boundary():
    _, req = request()
    decision = approve_dependency_request(
        req,
        decision_id="decision:approve",
        authority_id="authority:1",
        reason="authorized dependency review",
    )
    grant = decision_to_grant(req, decision)
    assert grant.dependency_ids == req.dependency_ids
    assert grant.added_observations == frozenset({"router_read"})
    assert grant.max_dependency_depth == 2


def test_rebound_approval_is_rejected():
    _, req = request()
    decision = approve_dependency_request(req, decision_id="decision:approve", authority_id="authority:1", reason="ok")
    other = create_dependency_request(
        request_id="request:other",
        investigation_id=req.investigation_id,
        authority_fingerprint=req.parent_authority_fingerprint,
        candidates=(candidate(),),
        requested_observations=frozenset({"other_read"}),
        requested_max_depth=2,
    )
    with pytest.raises(PermissionError, match="exact request"):
        decision_to_grant(other, decision)
