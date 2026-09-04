from cydra.counterexample import Counterexample
from cydra.poc import POCArtifact


def make_poc(reproducible=False):
    return POCArtifact(
        hypothesis_id="hypothesis:H1",
        counterexample=Counterexample(
            test_name="test_withdraw",
            trace=["call", "state_change", "assertion"],
            invariant="user balance cannot increase without attributable value",
            expected="invariant holds",
            actual="invariant violated",
            reproducible=reproducible,
        ),
        expected_violation="user balance increases without attributable value",
        finding_id="finding:F1",
        evidence_ids=("evidence:E1",),
        execution_request_id="execution_request:R1" if reproducible else None,
    )


def test_poc_is_grounded_in_finding_hypothesis_and_trace():
    poc = make_poc()
    assert poc.validation_errors(
        finding_id="finding:F1",
        hypothesis_id="hypothesis:H1",
        trace_evidence_ids={"evidence:E1", "evidence:E2"},
    ) == []


def test_poc_rejects_unrelated_finding_or_hypothesis():
    poc = make_poc()
    errors = poc.validation_errors(
        finding_id="finding:OTHER",
        hypothesis_id="hypothesis:OTHER",
        trace_evidence_ids={"evidence:E1"},
    )
    assert "PoC finding identity does not match the canonical finding" in errors
    assert "PoC hypothesis identity does not match the canonical finding hypothesis" in errors


def test_poc_rejects_evidence_outside_verified_trace():
    poc = make_poc()
    errors = poc.validation_errors(
        finding_id="finding:F1",
        hypothesis_id="hypothesis:H1",
        trace_evidence_ids={"evidence:OTHER"},
    )
    assert "PoC evidence must be grounded in the verified causal trace" in errors


def test_reproducible_poc_requires_execution_request_identity():
    poc = make_poc(reproducible=True)
    poc = POCArtifact(
        poc.hypothesis_id,
        poc.counterexample,
        poc.expected_violation,
        poc.reproducibility_notes,
        poc.finding_id,
        poc.evidence_ids,
        None,
    )
    errors = poc.validation_errors(trace_evidence_ids={"evidence:E1"})
    assert "reproducible PoC requires an execution request identity" in errors
    assert not poc.is_reproducible()


def test_reproducible_poc_requires_canonical_execution_identity():
    poc = make_poc(reproducible=True)
    assert poc.validation_errors(trace_evidence_ids={"evidence:E1"}) == []
    assert poc.is_reproducible()


def test_poc_serialization_preserves_lineage():
    poc = make_poc(reproducible=True)
    data = poc.as_dict()
    assert data["finding_id"] == "finding:F1"
    assert data["hypothesis_id"] == "hypothesis:H1"
    assert data["evidence_ids"] == ["evidence:E1"]
    assert data["execution_request_id"] == "execution_request:R1"
    assert data["counterexample"]["type"] == "COUNTEREXAMPLE"
