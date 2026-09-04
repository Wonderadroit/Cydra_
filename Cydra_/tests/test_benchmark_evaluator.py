from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.evaluate_blind_benchmark import EvaluationError, evaluate


CASE = {
    "case_id": "case-1",
    "contest_name": "fixture",
    "repository": "example/repo",
    "revision": "0123456789abcdef0123456789abcdef01234567",
    "rules": {"name": "fixture"},
    "input_manifest": ["src/Target.sol"],
}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_evaluator_reports_tp_fp_fn_and_review_diagnostics(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.json"
    oracle = tmp_path / "oracle.json"
    annotations = tmp_path / "annotations.json"
    output = tmp_path / "evaluation.json"

    _write(
        candidate,
        {
            "case": CASE,
            "findings": [
                {"finding_fingerprint": "issue-a", "severity": "high"},
                {"finding_fingerprint": "unexpected", "severity": "low"},
            ],
        },
    )
    _write(
        oracle,
        {
            "issues": [
                {"issue_id": "A", "title": "A", "fingerprint": "issue-a", "severity": "high"},
                {"issue_id": "B", "title": "B", "fingerprint": "issue-b", "severity": "medium"},
            ]
        },
    )
    _write(
        annotations,
        {
            "annotations": [
                {
                    "candidate_fingerprint": "issue-a",
                    "issue_id": "A",
                    "rationale": "reviewed semantic equivalence",
                    "failure_class": None,
                    "evidence_gaps": [],
                    "reasoning_failures": [],
                }
            ]
        },
    )

    result = evaluate(candidate, oracle, annotations, output)

    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)
    assert result["matched_issue_ids"] == ["A"]
    assert result["missed_issue_ids"] == ["B"]
    assert result["unexpected_fingerprints"] == ["unexpected"]
    assert output.exists()


def test_sealed_blind_result_is_evaluator_compatible(tmp_path: Path) -> None:
    from cydra.blind_reasoning import BlindReasoningResult

    candidate = tmp_path / "candidate.json"
    oracle = tmp_path / "oracle.json"
    annotations = tmp_path / "annotations.json"
    output = tmp_path / "evaluation.json"

    result = BlindReasoningResult(
        case_id="case-1",
        contest_name="fixture",
        repository="example/repo",
        revision=CASE["revision"],
        input_manifest=("src/Target.sol",),
        materialization_fingerprint="materialized",
        model_fingerprint="model",
        hypothesis_names=("h1",),
        observation_names=("o1",),
        selected_observation="o1",
        rounds_used=1,
        planning_steps_used=1,
        observations_used=0,
    )
    candidate.write_text(result.to_json(), encoding="utf-8")
    _write(
        oracle,
        {"issues": [{"issue_id": "A", "title": "A", "fingerprint": "issue-a", "severity": "high"}]},
    )
    _write(annotations, {"annotations": []})

    evaluated = evaluate(candidate, oracle, annotations, output)

    assert evaluated["true_positives"] == 0
    assert evaluated["false_positives"] == 0
    assert evaluated["false_negatives"] == 1
    assert evaluated["missed_issue_ids"] == ["A"]
    assert evaluated["recall"] == pytest.approx(0.0)


def test_evaluator_rejects_oracle_material_in_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.json"
    oracle = tmp_path / "oracle.json"
    annotations = tmp_path / "annotations.json"
    output = tmp_path / "evaluation.json"

    _write(candidate, {"case": CASE, "findings": [], "ground_truth": ["secret"]})
    _write(oracle, {"issues": []})
    _write(annotations, {"annotations": []})

    with pytest.raises(EvaluationError, match="forbidden oracle material"):
        evaluate(candidate, oracle, annotations, output)
