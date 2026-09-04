import pytest

from cydra.learning import LearningRecord, LearningStore
from cydra.planner import Hypothesis, Observation, LearningContext, choose_next_observation


def hypotheses():
    return [
        Hypothesis(
            "h1",
            0.5,
            {
                "observe-a": {"yes": 0.9, "no": 0.1},
                "observe-b": {"yes": 0.6, "no": 0.4},
            },
        ),
        Hypothesis(
            "h2",
            0.5,
            {
                "observe-a": {"yes": 0.1, "no": 0.9},
                "observe-b": {"yes": 0.4, "no": 0.6},
            },
        ),
    ]


def context_for(store):
    return LearningContext(
        investigation_id="investigation:1",
        authority_fingerprint="authority:1",
        lease_generation=1,
        learning_fingerprint=store.authority_independent_fingerprint(),
    )


def test_planner_records_exact_learning_provenance():
    store = LearningStore()
    record = LearningRecord("finding:1", "observation_pattern", "observe-a", "observe-a")
    store.learn(record)
    observations = [
        Observation("observe-a", ["yes", "no"], 1.0),
        Observation("observe-b", ["yes", "no"], 1.0),
    ]
    plan = choose_next_observation(hypotheses(), observations, store, context_for(store))
    assert plan is not None
    assert record.learning_id in plan.learning_ids
    assert plan.learning_context_fingerprint == store.authority_independent_fingerprint()
    assert plan.investigation_id == "investigation:1"
    assert "learning" in plan.rationale.lower()


def test_learning_requires_an_immutable_investigation_context():
    store = LearningStore()
    store.learn(LearningRecord("finding:1", "observation_pattern", "observe-a", "observe-a"))
    with pytest.raises(ValueError, match="investigation context"):
        choose_next_observation(
            hypotheses(),
            [Observation("observe-a", ["yes", "no"], 1.0)],
            store,
        )


def test_learning_context_rejects_store_mutation_after_snapshot():
    store = LearningStore()
    store.learn(LearningRecord("finding:1", "observation_pattern", "observe-a", "observe-a"))
    context = context_for(store)
    store.learn(LearningRecord("finding:2", "observation_pattern", "observe-b", "observe-b"))
    with pytest.raises(RuntimeError, match="learning store changed"):
        choose_next_observation(
            hypotheses(),
            [Observation("observe-a", ["yes", "no"], 1.0)],
            store,
            context,
        )


def test_learning_context_rejects_mismatched_snapshot():
    store = LearningStore()
    store.learn(LearningRecord("finding:1", "observation_pattern", "observe-a", "observe-a"))
    context = LearningContext(
        investigation_id="investigation:1",
        authority_fingerprint="authority:1",
        lease_generation=1,
        learning_fingerprint="tampered-learning-fingerprint",
    )
    with pytest.raises(RuntimeError, match="learning store changed"):
        choose_next_observation(
            hypotheses(),
            [Observation("observe-a", ["yes", "no"], 1.0)],
            store,
            context,
        )


def test_learning_cannot_authorize_an_observation():
    store = LearningStore()
    store.learn(LearningRecord("finding:1", "observation_pattern", "observe-a", "observe-a"))
    observations = [Observation("observe-a", ["yes", "no"], 1.0, authorized=False)]
    assert choose_next_observation(hypotheses(), observations, store, context_for(store)) is None


def test_learning_does_not_change_observation_cost_or_information_gain():
    observations = [Observation("observe-a", ["yes", "no"], 2.0)]
    baseline = choose_next_observation(hypotheses(), observations)
    store = LearningStore()
    store.learn(LearningRecord("finding:1", "observation_pattern", "observe-a", "observe-a"))
    learned = choose_next_observation(hypotheses(), observations, store, context_for(store))
    assert baseline is not None and learned is not None
    assert learned.observation == baseline.observation
    assert learned.expected_information_gain == baseline.expected_information_gain
    assert learned.utility > baseline.utility
    assert record_ids(learned) != ()


def record_ids(plan):
    return plan.learning_ids


def test_unrelated_learning_is_not_implicitly_applied():
    store = LearningStore()
    store.learn(LearningRecord("finding:1", "observation_pattern", "other-observation", "observe-a"))
    plan = choose_next_observation(
        hypotheses(),
        [Observation("observe-a", ["yes", "no"], 1.0)],
        store,
        context_for(store),
    )
    assert plan is not None
    assert plan.learning_ids == ()
