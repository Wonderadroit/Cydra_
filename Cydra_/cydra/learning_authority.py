"""Authority-plane binding for investigation learning consumption.

The learning store is intentionally authority-independent. This module binds a
read-only learning snapshot to the *actual* live investigation controller so
planner callers do not have to manufacture an authority fingerprint or lease
generation themselves.
"""
from __future__ import annotations

from .investigation_control import InvestigationController
from .learning import LearningStore
from .planner import LearningContext


def issue_learning_context(
    controller: InvestigationController,
    learning_store: LearningStore,
) -> LearningContext:
    """Issue a learning context from the live externally controlled envelope.

    The controller is the authority source. The returned context records the
    current investigation identity, authority fingerprint, lease generation,
    and an exact fingerprint of the learning snapshot. It does not modify the
    controller or grant any additional authority.
    """
    controller.require_active()
    return LearningContext(
        investigation_id=controller.investigation_id,
        authority_fingerprint=controller.authority_fingerprint,
        lease_generation=controller.lease.generation,
        learning_fingerprint=learning_store.authority_independent_fingerprint(),
    )


def validate_learning_context(
    controller: InvestigationController,
    learning_store: LearningStore,
    context: LearningContext,
) -> None:
    """Fail closed when either authority or learning state has changed."""
    controller.require_active()
    if context.investigation_id != controller.investigation_id:
        raise PermissionError("learning context investigation identity does not match")
    if context.lease_generation != controller.lease.generation:
        raise PermissionError("learning context has stale lease generation")
    if context.authority_fingerprint != controller.authority_fingerprint:
        raise PermissionError("learning context authority fingerprint is stale")
    context.validate_store(learning_store)
