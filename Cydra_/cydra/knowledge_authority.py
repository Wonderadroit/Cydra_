"""Authority-bound issuance and validation for Knowledge Base planning context."""
from __future__ import annotations

from .knowledge_base import KnowledgeBase
from .planner import KnowledgeContext
from .investigation_control import InvestigationController


def issue_knowledge_context(controller: InvestigationController, knowledge_base: KnowledgeBase) -> KnowledgeContext:
    """Derive a knowledge snapshot from the live investigation authority."""
    controller.require_active()
    return KnowledgeContext(
        investigation_id=controller.investigation_id,
        authority_fingerprint=controller.authority_fingerprint,
        lease_generation=controller.lease.generation,
        knowledge_fingerprint=knowledge_base.authority_independent_fingerprint(),
    )


def validate_knowledge_context(
    controller: InvestigationController,
    knowledge_base: KnowledgeBase,
    context: KnowledgeContext,
) -> None:
    """Fail closed if authority or knowledge changed after context issuance."""
    controller.require_active()
    if context.investigation_id != controller.investigation_id:
        raise PermissionError("knowledge context investigation identity does not match live authority")
    if context.lease_generation != controller.lease.generation:
        raise PermissionError("knowledge context has stale lease generation")
    if context.authority_fingerprint != controller.authority_fingerprint:
        raise PermissionError("knowledge context authority fingerprint does not match live authority")
    context.validate_store(knowledge_base)
