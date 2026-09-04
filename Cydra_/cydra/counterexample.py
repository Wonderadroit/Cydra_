from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class Counterexample:
    """A deterministic failing execution captured as audit evidence."""

    test_name: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    trace: List[str] = field(default_factory=list)
    invariant: str = ""
    expected: Any = None
    actual: Any = None
    reproducible: bool = False

    def minimized(self) -> "Counterexample":
        """Return a deterministic reduced representation without mutating evidence."""
        return Counterexample(
            test_name=self.test_name,
            input_data={k: self.input_data[k] for k in sorted(self.input_data)},
            trace=list(self.trace),
            invariant=self.invariant,
            expected=self.expected,
            actual=self.actual,
            reproducible=self.reproducible,
        )

    def as_evidence(self) -> Dict[str, Any]:
        return {
            "type": "COUNTEREXAMPLE",
            "test_name": self.test_name,
            "input_data": dict(self.input_data),
            "trace": list(self.trace),
            "invariant": self.invariant,
            "expected": self.expected,
            "actual": self.actual,
            "reproducible": self.reproducible,
        }


def minimize_counterexample(counterexample: Counterexample) -> Counterexample:
    """Perform deterministic metadata-level minimization.

    Execution-aware shrinking belongs to the concrete test backend; CYDRA keeps
    the resulting reduced counterexample immutable and provenance-preserving.
    """
    return counterexample.minimized()
