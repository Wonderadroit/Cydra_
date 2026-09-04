import pytest

from cydra.contradiction_re_evaluation import (
    ContradictionDisposition,
    reevaluate_contradiction,
)


def test_supporting_outcome_resolves_toward_supported():
    result = reevaluate_contradiction("c:1", "e:1", supports_hypothesis=True)
    assert result.disposition is ContradictionDisposition.SUPPORTED


def test_rejecting_outcome_resolves_toward_rejected():
    result = reevaluate_contradiction("c:1", "e:2", supports_hypothesis=False)
    assert result.disposition is ContradictionDisposition.REJECTED


def test_ambiguous_outcome_remains_inconclusive():
    result = reevaluate_contradiction("c:1", "e:3", supports_hypothesis=None)
    assert result.disposition is ContradictionDisposition.INCONCLUSIVE


def test_empty_identifiers_are_rejected():
    with pytest.raises(ValueError):
        reevaluate_contradiction("", "e:1", supports_hypothesis=True)
