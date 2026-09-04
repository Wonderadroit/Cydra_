import time

import pytest

from cydra.investigation_profiles import CapabilityProfile, InvestigationCapability, InvestigationProfile
from cydra.knowledge_authority import issue_knowledge_context, validate_knowledge_context
from cydra.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseError,
    KnowledgeKind,
    KnowledgeOrigin,
    KnowledgeRecord,
    bootstrap_knowledge_base,
)
from cydra.learning import LearningRecord, LearningStore
from cydra.investigation_control import InvestigationBudget, InvestigationController, InvestigationLease, InvestigationScope
from cydra.planner import Hypothesis, KnowledgeContext, Observation, choose_next_observation


def make_controller():
    now = time.time()
    return InvestigationController(
        "investigation:knowledge",
        InvestigationScope("scope:knowledge", allowed_observations=frozenset({"unrelated"})),
        InvestigationBudget(max_rounds=5, max_observations=5, max_planning_steps=5, max_hypotheses=5, max_execution_cost=10, max_dependency_depth=2, max_branching_factor=5),
        InvestigationLease("lease:knowledge", now - 1, now + 1000, generation=1),
    )


def test_bootstrap_catalog_contains_economic_and_cross_contract_framework():
    kb = bootstrap_knowledge_base()
    assert kb.matching(KnowledgeKind.HYPOTHESIS, "oracle_manipulation")
    assert kb.matching(KnowledgeKind.HYPOTHESIS, "state_desync")
    assert kb.matching(KnowledgeKind.OBSERVATION_PATTERN, "simulate_flash_loan")
    assert kb.matching(KnowledgeKind.DEPENDENCY_PATTERN, "router_pool")
    names = {profile.name for profile in kb.budget_profiles()}
    assert {"economic_attack", "cross_contract"} <= names


def test_seed_knowledge_cannot_claim_finding_provenance():
    with pytest.raises(KnowledgeBaseError, match="architectural seed"):
        KnowledgeRecord(
            KnowledgeKind.HYPOTHESIS, "x", "x", KnowledgeOrigin.ARCHITECTURAL_SEED,
            source_finding_id="finding:fake",
        )


def test_finding_derived_knowledge_requires_finding_provenance():
    with pytest.raises(KnowledgeBaseError, match="requires source_finding_id"):
        KnowledgeRecord(KnowledgeKind.HYPOTHESIS, "x", "x", KnowledgeOrigin.FINDING_DERIVED)


def test_learning_store_projects_into_knowledge_base_without_mislabeling():
    learning = LearningStore()
    learning.learn(LearningRecord("finding:1", "hypothesis", "oracle_manipulation", "oracle manipulation", 0.9))
    kb = KnowledgeBase(max_records=4)
    kb.ingest_learning(learning)
    records = kb.matching(KnowledgeKind.HYPOTHESIS, "oracle_manipulation")
    assert len(records) == 1
    assert records[0].origin == KnowledgeOrigin.FINDING_DERIVED
    assert records[0].source_finding_id == "finding:1"


def test_knowledge_context_rejects_mutation_after_snapshot():
    kb = bootstrap_knowledge_base()
    context = KnowledgeContext("investigation:1", "authority:1", 1, kb.authority_independent_fingerprint())
    kb.add(KnowledgeRecord(KnowledgeKind.HYPOTHESIS, "new", "new", KnowledgeOrigin.ARCHITECTURAL_SEED))
    with pytest.raises(RuntimeError, match="knowledge base changed"):
        context.validate_store(kb)


def test_knowledge_context_is_issued_from_live_authority():
    c = make_controller()
    kb = bootstrap_knowledge_base()
    context = issue_knowledge_context(c, kb)
    assert context.investigation_id == c.investigation_id
    assert context.authority_fingerprint == c.authority_fingerprint
    validate_knowledge_context(c, kb, context)


def test_knowledge_context_rejects_changed_authority_and_lease():
    c = make_controller()
    kb = bootstrap_knowledge_base()
    context = issue_knowledge_context(c, kb)
    c.scope = InvestigationScope("scope:knowledge", allowed_observations=frozenset({"unrelated", "new"}))
    with pytest.raises(PermissionError, match="authority fingerprint"):
        validate_knowledge_context(c, kb, context)


def test_knowledge_context_rejects_stale_lease_generation():
    c = make_controller()
    kb = bootstrap_knowledge_base()
    context = issue_knowledge_context(c, kb)
    c.lease = InvestigationLease("lease:knowledge-2", time.time() - 1, time.time() + 1000, generation=2)
    with pytest.raises(PermissionError, match="lease generation"):
        validate_knowledge_context(c, kb, context)


def test_capability_profile_filters_reasoning_knowledge_only():
    kb = bootstrap_knowledge_base()
    economic = kb.for_profile(CapabilityProfile.for_profile(InvestigationProfile.ECONOMIC))
    keys = {record.key for record in economic}
    assert "oracle_manipulation" in keys
    assert "router_pool" in keys
    assert "reentrancy" not in keys


def test_capability_profile_does_not_grant_authority():
    c = make_controller()
    before = c.authority_fingerprint
    combined = CapabilityProfile.for_profile(InvestigationProfile.COMBINED)
    assert combined.supports(InvestigationCapability.ECONOMIC)
    assert combined.supports(InvestigationCapability.CROSS_CONTRACT)
    assert combined.supports(InvestigationCapability.DEEP_ANALYSIS)
    assert c.authority_fingerprint == before
    assert c.budget.max_observations == 5


def test_knowledge_ranking_never_makes_unauthorized_observation_eligible():
    kb = bootstrap_knowledge_base()
    context = KnowledgeContext("investigation:1", "authority:1", 1, kb.authority_independent_fingerprint())
    hypotheses = [
        Hypothesis("oracle", 0.5, {
            "simulate_flash_loan": {"profit": 0.9, "loss": 0.1},
            "unrelated": {"profit": 0.9, "loss": 0.1},
        }),
        Hypothesis("safe", 0.5, {
            "simulate_flash_loan": {"profit": 0.1, "loss": 0.9},
            "unrelated": {"profit": 0.1, "loss": 0.9},
        }),
    ]
    observations = [
        Observation("simulate_flash_loan", ["profit", "loss"], 1, authorized=False),
        Observation("unrelated", ["profit", "loss"], 1, authorized=True),
    ]
    plan = choose_next_observation(hypotheses, observations, knowledge_base=kb, knowledge_context=context)
    assert plan is not None
    assert plan.observation == "unrelated"
    assert plan.knowledge_ids == ()
