import pytest
from cydra.belief_update import update_belief
from cydra.contradiction_re_evaluation import ContradictionDisposition

def test_support_increases_confidence():
    result = update_belief("b:1", "c:1", 0.5, ContradictionDisposition.SUPPORTED, "e:1")
    assert result.posterior_confidence > result.prior_confidence

def test_rejection_decreases_confidence():
    result = update_belief("b:1", "c:1", 0.5, ContradictionDisposition.REJECTED, "e:1")
    assert result.posterior_confidence < result.prior_confidence

def test_inconclusive_preserves_confidence():
    result = update_belief("b:1", "c:1", 0.5, ContradictionDisposition.INCONCLUSIVE, "e:1")
    assert result.posterior_confidence == result.prior_confidence

def test_invalid_confidence_rejected():
    with pytest.raises(ValueError):
        update_belief("b:1", "c:1", 1.2, ContradictionDisposition.SUPPORTED, "e:1")
