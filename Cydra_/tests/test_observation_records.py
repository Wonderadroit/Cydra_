import pytest

from cydra.observation_records import persist_test_plan
from cydra.system_model import Node, SystemModel
from cydra.test_planning import TestPlan


def _plan():
    return TestPlan(
        observation_id="obs-1",
        description="Inspect authorization boundary",
        information_gain=0.8,
        cost=1.0,
        utility=0.8,
        rationale="distinguishes competing hypotheses",
    )


def test_persist_test_plan_records_auditable_links_without_execution():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "H1"))
    model.add_node(Node("candidate:c1", "invariant", "C1"))

    record = persist_test_plan(
        model,
        _plan(),
        hypothesis_ids=["hypothesis:h1"],
        candidate_ids=["candidate:c1"],
    )

    node = model.nodes["observation:obs-1"]
    assert node.kind == "observation"
    assert node.attributes["status"] == "planned"
    assert node.attributes["executed"] is False
    assert record.hypothesis_ids == ("hypothesis:h1",)
    assert record.candidate_ids == ("candidate:c1",)
    assert model.neighbors("observation:obs-1", "tests") == ["hypothesis:h1"]
    assert model.neighbors("observation:obs-1", "targets") == ["candidate:c1"]


def test_persist_test_plan_rejects_missing_references_without_mutating_model():
    model = SystemModel()
    with pytest.raises(KeyError):
        persist_test_plan(model, _plan(), hypothesis_ids=["hypothesis:missing"])
    assert model.nodes == {}
    assert model.edges == []


def test_persist_test_plan_rejects_duplicate_observation():
    model = SystemModel()
    persist_test_plan(model, _plan())
    with pytest.raises(ValueError):
        persist_test_plan(model, _plan())
