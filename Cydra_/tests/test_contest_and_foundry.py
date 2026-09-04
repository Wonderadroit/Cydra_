import pytest

from cydra.contest import ContestRules, KnownIssue, KnownIssueBaseline
from cydra.foundry import FoundryAuthorization, FoundryResult, result_to_evidence
from cydra.evidence import EvidenceKind
from cydra.poc import Counterexample, POCArtifact


def test_contest_rules_fail_closed_for_unknown_targets():
    rules = ContestRules(name="example", in_scope=("contracts/A.sol",), out_of_scope=("contracts/B.sol",))
    assert rules.classify_target("contracts/A.sol") == "IN_SCOPE"
    assert rules.classify_target("contracts/B.sol") == "OUT_OF_SCOPE"
    assert rules.classify_target("contracts/C.sol") == "UNKNOWN"
    assert rules.action_allowed("deploy")


def test_forbidden_action_overrides_default_allowance():
    rules = ContestRules(name="example", forbidden_actions=("mainnet-write",))
    assert not rules.action_allowed("mainnet-write")


def test_known_issue_baseline_matches_fingerprint():
    baseline = KnownIssueBaseline.from_iterable([
        KnownIssue("K-1", "Known accounting issue", "sha256:abc", "medium")
    ])
    assert baseline.is_known("sha256:abc")
    assert not baseline.is_known("sha256:def")


def test_foundry_result_is_observation_not_proof_of_absence():
    passed = FoundryResult(("forge", "test"), 0, "No failing invariant", "")
    failed = FoundryResult(("forge", "test"), 1, "Failing invariant", "")
    assert passed.passed and not passed.counterexample
    assert failed.counterexample
    assert passed.outcome == "NO_COUNTEREXAMPLE"
    assert failed.outcome == "COUNTEREXAMPLE"


def test_foundry_result_becomes_provenance_aware_evidence():
    result = FoundryResult(
        ("forge", "test", "--match-test", "testFuzz"), 1, "FAIL", "trace",
        authorization_id="fixture-test", scope_status="AUTHORIZED_EXECUTION",
        execution_id="execution:fixture-test",
    )
    evidence = result_to_evidence(result, "evidence:foundry:1")
    assert evidence.kind is EvidenceKind.TEST_RESULT
    assert evidence.provenance.scope_status == "AUTHORIZED_EXECUTION"
    assert evidence.provenance.details["authorization_id"] == "fixture-test"
    assert evidence.value["outcome"] == "COUNTEREXAMPLE"
    assert evidence.value["stderr"] == "trace"


def test_foundry_authorization_can_construct_matching_result():
    authorization = FoundryAuthorization("fixture-test")
    result = FoundryResult(
        ("forge", "test"), 0, "ok", "",
        authorization_id=authorization.authorization_id,
        scope_status=authorization.scope_status,
        execution_id="execution:fixture-test",
    )
    assert result_to_evidence(result, "evidence:foundry:authorized").provenance.scope_status == authorization.scope_status


def test_reproducible_poc_requires_canonical_execution_request_identity():
    poc = POCArtifact(
        "H1",
        Counterexample(
            test_name="testInvariant",
            input_data={"x": 1},
            trace=["trace"],
            invariant="balance invariant",
            reproducible=True,
        ),
        "balance invariant",
    )
    assert not poc.is_reproducible()
    assert "execution request identity" in poc.validation_errors()[0]


def test_duplicate_known_issue_id_rejected():
    baseline = KnownIssueBaseline()
    baseline.add(KnownIssue("K-1", "Issue", "fp"))
    with pytest.raises(ValueError):
        baseline.add(KnownIssue("K-1", "Other", "fp2"))
