from dataclasses import dataclass

from .counterexample import Counterexample


@dataclass(frozen=True)
class POCArtifact:
    """A reproducible proof artifact grounded in canonical audit evidence.

    Counterexample remains the canonical representation of the failing
    execution. POCArtifact adds finding-oriented lineage and presentation
    metadata without redefining execution data. A PoC describes or presents a
    demonstrated behavior; it never implies that CYDRA itself executed an
    external action.
    """

    hypothesis_id: str
    counterexample: Counterexample
    expected_violation: str
    reproducibility_notes: str = ""
    finding_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    execution_request_id: str | None = None
    poc_id: str | None = None

    def validation_errors(
        self,
        *,
        finding_id: str | None = None,
        hypothesis_id: str | None = None,
        trace_evidence_ids: set[str] | None = None,
    ) -> list[str]:
        """Validate PoC lineage without executing or mutating anything."""
        errors: list[str] = []
        if not self.hypothesis_id.strip():
            errors.append("PoC hypothesis identity is empty")
        if finding_id is not None and self.finding_id != finding_id:
            errors.append("PoC finding identity does not match the canonical finding")
        if hypothesis_id is not None and self.hypothesis_id != hypothesis_id:
            errors.append("PoC hypothesis identity does not match the canonical finding hypothesis")
        if not self.expected_violation.strip():
            errors.append("PoC expected violation is empty")
        if not self.counterexample.test_name:
            errors.append("PoC counterexample test name is empty")
        if not self.counterexample.trace:
            errors.append("PoC counterexample trace is empty")
        if trace_evidence_ids is not None:
            if not self.evidence_ids:
                errors.append("PoC requires canonical evidence IDs")
            elif not set(self.evidence_ids).issubset(trace_evidence_ids):
                errors.append("PoC evidence must be grounded in the verified causal trace")
        if self.counterexample.reproducible and not self.execution_request_id:
            errors.append("reproducible PoC requires an execution request identity")
        return errors

    def is_reproducible(self) -> bool:
        """Return whether the artifact contains minimum reproduction data."""
        return bool(
            self.counterexample.test_name
            and self.counterexample.trace
            and self.counterexample.reproducible
            and self.execution_request_id
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "poc_id": self.poc_id,
            "hypothesis_id": self.hypothesis_id,
            "counterexample": self.counterexample.as_evidence(),
            "expected_violation": self.expected_violation,
            "reproducibility_notes": self.reproducibility_notes,
            "finding_id": self.finding_id,
            "evidence_ids": list(self.evidence_ids),
            "execution_request_id": self.execution_request_id,
        }
