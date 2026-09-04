import pytest

from cydra.contradiction_re_evaluation import ContradictionDisposition, ReEvaluation
from cydra.contradiction_re_evaluation_model import persist_re_evaluation
from cydra.system_model import Node, SystemModel


def test_persists_re_evaluation_without_overwriting_source_evidence():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "external outcome", {"immutable": True}))
    result = ReEvaluation("c:1", ContradictionDisposition.SUPPORTED, "e:1", "supports hypothesis")
    persist_re_evaluation(model, result, "reeval:1")
    assert model.nodes["e:1"].attributes["immutable"] is True
    assert model.nodes["reeval:1"].attributes["disposition"] == "supported"
    assert model.neighbors("c:1", "re_evaluated_by") == ["reeval:1"]
    assert model.neighbors("reeval:1", "based_on") == ["e:1"]


def test_missing_evidence_does_not_mutate_model():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    result = ReEvaluation("c:1", ContradictionDisposition.INCONCLUSIVE, "e:missing", "inconclusive")
    with pytest.raises(KeyError):
        persist_re_evaluation(model, result, "reeval:1")
    assert "reeval:1" not in model.nodes
    assert model.edges == []


def test_duplicate_record_rejected():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "outcome"))
    result = ReEvaluation("c:1", ContradictionDisposition.REJECTED, "e:1", "rejects hypothesis")
    persist_re_evaluation(model, result, "reeval:1")
    with pytest.raises(ValueError):
        persist_re_evaluation(model, result, "reeval:1")
