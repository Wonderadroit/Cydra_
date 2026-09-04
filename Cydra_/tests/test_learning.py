import pytest

from cydra.learning import LearningError, LearningLimits, LearningRecord, LearningStore


def test_finding_learning_is_persistent_and_reusable_without_authority_escalation():
    store = LearningStore()
    ids = store.learn_from_finding(
        finding_id="finding:001",
        invariant="total debt cannot exceed collateral value",
        hypothesis="state transition can bypass collateral accounting",
        observation_pattern="compare debt before and after cross-contract callback",
        dependency_pattern="lending-pool -> token -> oracle",
        budget_heuristic="prioritize callback boundary before broad fuzzing",
    )
    assert len(ids) == 5
    assert store.apply_candidates("hypothesis", "state transition can bypass collateral accounting")
    assert store.apply_candidates("dependency_pattern", "lending-pool -> token -> oracle")
    assert "authority" not in str(store.apply_candidates("budget_heuristic", "prioritize callback boundary before broad fuzzing")[0]).lower()


def test_identical_learning_is_idempotent_and_conflict_is_rejected():
    store = LearningStore()
    record = LearningRecord("finding:001", "invariant", "k", "v")
    assert store.learn(record) == store.learn(record)
    with pytest.raises(LearningError, match="identity collision"):
        store.records[record.learning_id] = LearningRecord("finding:other", "invariant", "k", "v")
        store.learn(record)


def test_learning_category_limits_are_bounded():
    store = LearningStore(LearningLimits(max_invariants=1))
    store.learn(LearningRecord("finding:1", "invariant", "a", "a"))
    with pytest.raises(LearningError, match="learning budget exhausted"):
        store.learn(LearningRecord("finding:2", "invariant", "b", "b"))


def test_duplicate_new_records_count_once_against_category_limit():
    store = LearningStore(LearningLimits(max_invariants=1))
    record = LearningRecord("finding:1", "invariant", "same", "same")
    ids = store.learn_many((record, record))
    assert ids == (record.learning_id, record.learning_id)
    assert len(store.records) == 1
    assert len([r for r in store.records.values() if r.category == "invariant"]) == 1


def test_duplicate_new_records_do_not_hide_distinct_records_from_limits():
    store = LearningStore(LearningLimits(max_invariants=1))
    first = LearningRecord("finding:1", "invariant", "first", "first")
    second = LearningRecord("finding:2", "invariant", "second", "second")
    with pytest.raises(LearningError, match="learning budget exhausted"):
        store.learn_many((first, first, second))
    assert store.records == {}


def test_learning_rejects_invalid_confidence_and_unknown_category():
    with pytest.raises(LearningError):
        LearningRecord("finding:1", "invariant", "k", "v", confidence=1.1)
    with pytest.raises(LearningError):
        LearningRecord("finding:1", "unknown", "k", "v")


def test_learning_fingerprint_is_order_independent():
    a = LearningStore()
    b = LearningStore()
    records = [
        LearningRecord("finding:1", "hypothesis", "b", "2"),
        LearningRecord("finding:2", "invariant", "a", "1"),
    ]
    for record in records:
        a.learn(record)
    for record in reversed(records):
        b.learn(record)
    assert a.authority_independent_fingerprint() == b.authority_independent_fingerprint()


def test_learning_export_does_not_contain_authority_grant_fields():
    exported = LearningStore().export()
    assert set(exported) == {"limits", "records", "fingerprint"}
    assert "grant" not in exported
    assert "lease" not in exported
