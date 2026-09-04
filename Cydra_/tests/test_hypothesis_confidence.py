import pytest
from cydra.hypothesis_confidence import normalize_competing_confidences, project_hypothesis_confidence

def test_projects_valid_hypothesis_confidence():
    result = project_hypothesis_confidence("h:1", .7, "bu:1")
    assert result.confidence == .7
    assert result.source_update_id == "bu:1"

def test_normalizes_competing_hypotheses():
    result = normalize_competing_confidences({"h:1": .7, "h:2": .3})
    assert sum(result.values()) == pytest.approx(1.0)
    assert result["h:1"] > result["h:2"]

def test_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        project_hypothesis_confidence("h:1", 1.2, "bu:1")

def test_rejects_zero_total():
    with pytest.raises(ValueError):
        normalize_competing_confidences({"h:1": 0.0, "h:2": 0.0})
