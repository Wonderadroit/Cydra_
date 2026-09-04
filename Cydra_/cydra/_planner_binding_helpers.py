from __future__ import annotations

from typing import Iterable, Mapping, Optional


def normalize_hypothesis_pair(pair: Iterable[str]) -> tuple[str, str]:
    """Validate and normalize an explicit two-hypothesis discriminator binding."""
    values = tuple(pair)
    if len(values) != 2:
        raise ValueError("discriminating hypothesis binding must contain exactly two hypotheses")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("discriminating hypothesis IDs must be non-empty strings")
    if values[0] == values[1]:
        raise ValueError("discriminating hypothesis binding must reference two distinct hypotheses")
    return values


def validate_competing_pair(
    pair: Iterable[str],
    hypotheses: Mapping[str, object],
    competing_pairs: Optional[Iterable[tuple[str, str]]] = None,
) -> tuple[str, str]:
    """Validate semantic pair identity without deriving it from information gain.

    ``competing_pairs=None`` means the caller is validating only pair shape and
    hypothesis identity.  An explicitly supplied competition set is authoritative,
    including an empty set, and therefore requires the pair to be declared there.
    """
    normalized = normalize_hypothesis_pair(pair)
    missing = [hypothesis_id for hypothesis_id in normalized if hypothesis_id not in hypotheses]
    if missing:
        raise ValueError(f"unknown hypotheses in discriminating binding: {', '.join(missing)}")
    if competing_pairs is not None:
        canonical = {tuple(candidate) for candidate in competing_pairs}
        reverse = (normalized[1], normalized[0])
        if normalized not in canonical and reverse not in canonical:
            raise ValueError("discriminating hypothesis pair is not declared as competing")
    return normalized
