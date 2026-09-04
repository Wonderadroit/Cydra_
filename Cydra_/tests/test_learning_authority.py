import time

import pytest

from cydra.investigation_control import (
    InvestigationBudget,
    InvestigationController,
    InvestigationLease,
    InvestigationScope,
)
from cydra.learning import LearningRecord, LearningStore
from cydra.learning_authority import issue_learning_context, validate_learning_context


def make_controller():
    now = time.time()
    return InvestigationController(
        "investigation:learning",
        InvestigationScope("scope:learning", allowed_observations=frozenset({"observe"})),
        InvestigationBudget(),
        InvestigationLease("lease:learning", now - 1, now + 1000, generation=7),
    )


def test_learning_context_is_issued_from_live_authority():
    controller = make_controller()
    store = LearningStore()
    context = issue_learning_context(controller, store)
    assert context.investigation_id == controller.investigation_id
    assert context.authority_fingerprint == controller.authority_fingerprint
    assert context.lease_generation == controller.lease.generation
    assert context.learning_fingerprint == store.authority_independent_fingerprint()


def test_forged_context_authority_is_rejected():
    controller = make_controller()
    store = LearningStore()
    context = issue_learning_context(controller, store)
    forged = type(context)(
        context.investigation_id,
        "forged-authority",
        context.lease_generation,
        context.learning_fingerprint,
    )
    with pytest.raises(PermissionError, match="authority fingerprint"):
        validate_learning_context(controller, store, forged)


def test_stale_lease_generation_is_rejected():
    controller = make_controller()
    store = LearningStore()
    context = issue_learning_context(controller, store)
    controller.lease = InvestigationLease(
        controller.lease.lease_id,
        controller.lease.issued_at,
        controller.lease.expires_at,
        generation=8,
    )
    with pytest.raises(PermissionError, match="lease generation"):
        validate_learning_context(controller, store, context)


def test_expired_authority_cannot_issue_or_validate_learning_context():
    now = time.time()
    controller = InvestigationController(
        "investigation:expired",
        InvestigationScope("scope:expired", allowed_observations=frozenset({"observe"})),
        InvestigationBudget(),
        InvestigationLease("lease:expired", now - 10, now - 1, generation=1),
    )
    store = LearningStore()
    with pytest.raises(RuntimeError, match="not active"):
        issue_learning_context(controller, store)


def test_learning_mutation_invalidates_existing_context():
    controller = make_controller()
    store = LearningStore()
    context = issue_learning_context(controller, store)
    store.learn(LearningRecord("finding:1", "observation_pattern", "observe", "observe"))
    with pytest.raises(RuntimeError, match="learning store changed"):
        validate_learning_context(controller, store, context)
