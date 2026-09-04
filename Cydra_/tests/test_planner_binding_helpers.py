import pytest

from cydra._planner_binding_helpers import normalize_hypothesis_pair, validate_competing_pair


def test_normalize_pair_requires_two_distinct_nonempty_ids():
    with pytest.raises(ValueError):
        normalize_hypothesis_pair(("hypothesis:a",))
    with pytest.raises(ValueError):
        normalize_hypothesis_pair(("hypothesis:a", "hypothesis:a"))
    with pytest.raises(ValueError):
        normalize_hypothesis_pair(("", "hypothesis:b"))


def test_validate_pair_requires_supplied_hypotheses():
    with pytest.raises(ValueError, match="unknown hypotheses"):
        validate_competing_pair(
            ("hypothesis:a", "hypothesis:b"),
            {"hypothesis:a": object()},
        )


def test_validate_pair_requires_declared_competition_when_relationships_are_supplied():
    hypotheses = {"hypothesis:a": object(), "hypothesis:b": object()}
    with pytest.raises(ValueError, match="not declared as competing"):
        validate_competing_pair(
            ("hypothesis:a", "hypothesis:b"),
            hypotheses,
            competing_pairs=(("hypothesis:a", "hypothesis:c"),),
        )


def test_validate_pair_accepts_declared_pair_in_either_graph_direction():
    hypotheses = {"hypothesis:a": object(), "hypothesis:b": object()}
    assert validate_competing_pair(
        ("hypothesis:b", "hypothesis:a"),
        hypotheses,
        competing_pairs=(("hypothesis:a", "hypothesis:b"),),
    ) == ("hypothesis:b", "hypothesis:a")
