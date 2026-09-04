import pytest

from cydra.benchmark import (
    BenchmarkError,
    BenchmarkFinding,
    BenchmarkMatchAnnotation,
    BlindBenchmarkCase,
    build_oracle,
    evaluate_annotated_blind_run,
    evaluate_blind_run,
)
from cydra.contest import ContestRules, KnownIssue


def make_case() -> BlindBenchmarkCase:
    return BlindBenchmarkCase(
        case_id="predy-2024-05",
        contest_name="historical-predy",
        repository="code-423n4/2024-05-predy",
        revision="contest-snapshot-sha",
        rules=ContestRules(
            name="predy",
            in_scope=("src/",),
            out_of_scope=("test/",),
            forbidden_actions=("live-mainnet-write",),
        ),
        input_manifest=("README.md", "src/"),
    )


def test_blind_case_contains_no_historical_issue_oracle():
    case = make_case()
    assert not hasattr(case, "baseline")
    assert not hasattr(case, "known_issues")
    assert case.fingerprint()


def test_blind_evaluation_matches_and_reports_misses_and_false_positives():
    case = make_case()
    oracle = build_oracle(
        [
            KnownIssue("H-01", "oracle manipulation", "fp:h01", "high"),
            KnownIssue("M-01", "stale price feed", "fp:m01", "medium"),
        ]
    )
    evaluation = evaluate_blind_run(
        case,
        oracle,
        [
            BenchmarkFinding("fp:h01", "high"),
            BenchmarkFinding("fp:unknown", "medium"),
        ],
    )

    assert evaluation.matched_issue_ids == ("H-01",)
    assert evaluation.missed_issue_ids == ("M-01",)
    assert evaluation.unexpected_fingerprints == ("fp:unknown",)
    assert evaluation.true_positives == 1
    assert evaluation.false_positives == 1
    assert evaluation.recall == 0.5
    assert evaluation.precision == 0.5
    assert evaluation.severity_matches == 1
    assert evaluation.severity_mismatches == 0


def test_annotated_evaluation_does_not_require_candidate_to_reproduce_oracle_fingerprint():
    case = make_case()
    oracle = build_oracle(
        [
            KnownIssue("H-01", "oracle manipulation", "historical-oracle-fingerprint", "high"),
            KnownIssue("M-01", "stale price feed", "another-oracle-fingerprint", "medium"),
        ]
    )
    findings = [
        BenchmarkFinding("cydra-claim-a", "high"),
        BenchmarkFinding("cydra-claim-b", "low"),
    ]

    evaluation = evaluate_annotated_blind_run(
        case,
        oracle,
        findings,
        [
            BenchmarkMatchAnnotation(
                "cydra-claim-a",
                "H-01",
                "same root cause and affected state transition after evaluator review",
            )
        ],
    )

    assert evaluation.matched_issue_ids == ("H-01",)
    assert evaluation.missed_issue_ids == ("M-01",)
    assert evaluation.unexpected_fingerprints == ("cydra-claim-b",)
    assert evaluation.severity_matches == 1
    assert evaluation.severity_mismatches == 0


def test_annotated_evaluation_requires_review_rationale():
    case = make_case()
    oracle = build_oracle([KnownIssue("H-01", "issue", "oracle-fp")])
    with pytest.raises(BenchmarkError, match="rationale"):
        evaluate_annotated_blind_run(
            case,
            oracle,
            [BenchmarkFinding("candidate")],
            [BenchmarkMatchAnnotation("candidate", "H-01", "")],
        )


def test_annotated_evaluation_rejects_duplicate_candidate_matches():
    case = make_case()
    oracle = build_oracle(
        [KnownIssue("H-01", "one", "fp:1"), KnownIssue("H-02", "two", "fp:2")]
    )
    with pytest.raises(BenchmarkError, match="multiple historical issues"):
        evaluate_annotated_blind_run(
            case,
            oracle,
            [BenchmarkFinding("candidate")],
            [
                BenchmarkMatchAnnotation("candidate", "H-01", "first"),
                BenchmarkMatchAnnotation("candidate", "H-02", "second"),
            ],
        )


def test_annotated_evaluation_rejects_unknown_candidate():
    case = make_case()
    oracle = build_oracle([KnownIssue("H-01", "issue", "fp:1")])
    with pytest.raises(BenchmarkError, match="unknown candidate"):
        evaluate_annotated_blind_run(
            case,
            oracle,
            [BenchmarkFinding("candidate")],
            [BenchmarkMatchAnnotation("other", "H-01", "reviewed")],
        )


def test_duplicate_historical_fingerprints_are_rejected():
    with pytest.raises(BenchmarkError):
        build_oracle(
            [
                KnownIssue("H-01", "one", "same-fingerprint"),
                KnownIssue("H-02", "two", "same-fingerprint"),
            ]
        )


def test_duplicate_candidate_fingerprints_are_rejected():
    case = make_case()
    oracle = build_oracle([KnownIssue("H-01", "issue", "fp:h01")])
    with pytest.raises(BenchmarkError):
        evaluate_blind_run(
            case,
            oracle,
            [BenchmarkFinding("fp:h01"), BenchmarkFinding("fp:h01")],
        )


def test_empty_candidate_fingerprint_is_rejected():
    case = make_case()
    oracle = build_oracle([KnownIssue("H-01", "issue", "fp:h01")])
    with pytest.raises(BenchmarkError):
        evaluate_blind_run(case, oracle, [BenchmarkFinding("")])
