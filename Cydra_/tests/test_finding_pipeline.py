from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision
from cydra.finding_pipeline import promote_candidate, promote_verified_candidate
from cydra.impact import ImpactLevel, assess_impact
from cydra.learning import FindingLearningContribution, LearningLimits, LearningStore


def make_finding() -> Finding:
    impact = assess_impact(
        level=ImpactLevel.HIGH,
        asset_at_risk="protocol funds",
        consequence="unauthorized loss",
        evidence_ids=("e1",),
    )
    return Finding(
        finding_id="F-001",
        title="Invariant violation",
        summary="Synthetic verified finding",
        severity="HIGH",
        impact=impact,
        affected_components=("Vault.withdraw",),
        evidence_ids=("e1",),
        hypothesis_id="H-001",
        poc_reference="poc/F-001",
    )


def make_learning() -> FindingLearningContribution:
    return FindingLearningContribution(
        invariant="withdrawal authorization must hold",
        hypothesis="authorization can be bypassed through the withdrawal path",
        observation_pattern="trace authorization state before value transfer",
        dependency_pattern="withdrawal path depends on authorization boundary",
        budget_heuristic="prioritize authorization observations before deeper exploration",
        confidence=0.9,
    )


def verified_candidate() -> FindingCandidate:
    return FindingCandidate(True, False, True, True, True, True)


def test_unverified_candidate_cannot_be_promoted():
    result = promote_candidate(
        FindingCandidate(True, False, True, True, False, True), make_finding()
    )
    assert result.decision == GateDecision.BLOCKED
    assert result.finding is None


def test_verified_candidate_is_promoted():
    result = promote_candidate(verified_candidate(), make_finding())
    assert result.decision == GateDecision.READY
    assert result.finding is not None


def test_verified_finding_requires_explicit_learning_when_store_is_used():
    store = LearningStore()
    result = promote_candidate(verified_candidate(), make_finding(), learning_store=store)
    assert result.decision == GateDecision.BLOCKED
    assert result.finding is None
    assert store.records == {}


def test_verified_finding_persists_all_learning_categories():
    store = LearningStore()
    result = promote_verified_candidate(verified_candidate(), make_finding(), store, make_learning())
    assert result.decision == GateDecision.READY
    assert result.finding is not None
    assert len(result.learning_ids) == 5
    assert {record.category for record in store.records.values()} == {
        "invariant", "hypothesis", "observation_pattern", "dependency_pattern", "budget_heuristic"
    }
    assert all(record.finding_id == "F-001" for record in store.records.values())


def test_learning_failure_does_not_partially_commit():
    store = LearningStore(LearningLimits(max_invariants=1, max_hypotheses=1, max_observation_patterns=1, max_dependency_patterns=1, max_budget_heuristics=1))
    existing = make_learning().records_for("OTHER")[0]
    store.learn(existing)
    result = promote_verified_candidate(verified_candidate(), make_finding(), store, make_learning())
    assert result.decision == GateDecision.BLOCKED
    assert result.finding is None
    assert len(store.records) == 1
    assert next(iter(store.records.values())).finding_id == "OTHER"


def test_learning_replay_is_idempotent():
    store = LearningStore()
    first = promote_verified_candidate(verified_candidate(), make_finding(), store, make_learning())
    second = promote_verified_candidate(verified_candidate(), make_finding(), store, make_learning())
    assert first.learning_ids == second.learning_ids
    assert len(store.records) == 5
