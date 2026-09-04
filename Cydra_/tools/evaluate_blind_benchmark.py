#!/usr/bin/env python3
"""Evaluate a sealed blind CYDRA candidate against a separately held oracle.

This process is intentionally post-run. The oracle and reviewer annotations are
never accepted as investigation input; they are consumed only after the blind
candidate has been sealed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from cydra.benchmark import (
    BenchmarkFinding,
    BenchmarkMatchAnnotation,
    BlindBenchmarkCase,
    BenchmarkOracle,
    evaluate_annotated_blind_run,
)
from cydra.contest import ContestRules, KnownIssue, KnownIssueBaseline


class EvaluationError(ValueError):
    """Raised when post-run benchmark evaluation input is malformed."""


@dataclass(frozen=True)
class ReviewerDiagnostic:
    issue_id: str
    failure_class: str | None
    evidence_gaps: tuple[str, ...]
    reasoning_failures: tuple[str, ...]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"invalid JSON: {path}") from exc


def _load_case(data: dict[str, Any]) -> BlindBenchmarkCase:
    rules_data = data.get("rules", {})
    if not isinstance(rules_data, dict):
        raise EvaluationError("case.rules must be an object")
    rules = ContestRules(
        name=str(rules_data.get("name", "")),
        in_scope=tuple(rules_data.get("in_scope", ())),
        out_of_scope=tuple(rules_data.get("out_of_scope", ())),
        forbidden_actions=tuple(rules_data.get("forbidden_actions", ())),
        allowed_actions=tuple(rules_data.get("allowed_actions", ())),
        notes=tuple(rules_data.get("notes", ())),
    )
    return BlindBenchmarkCase(
        case_id=str(data["case_id"]),
        contest_name=str(data["contest_name"]),
        repository=str(data["repository"]),
        revision=str(data["revision"]),
        rules=rules,
        input_manifest=tuple(data.get("input_manifest", ())),
    )


def _load_oracle(data: dict[str, Any]) -> BenchmarkOracle:
    issues_data = data.get("issues")
    if not isinstance(issues_data, list):
        raise EvaluationError("oracle.issues must be an array")
    issues: list[KnownIssue] = []
    for item in issues_data:
        if not isinstance(item, dict):
            raise EvaluationError("each oracle issue must be an object")
        issues.append(
            KnownIssue(
                issue_id=str(item["issue_id"]),
                title=str(item.get("title", "")),
                fingerprint=str(item["fingerprint"]),
                severity=item.get("severity"),
                notes=str(item.get("notes", "")),
            )
        )
    return BenchmarkOracle(baseline=KnownIssueBaseline.from_iterable(issues))


def _load_candidate(data: dict[str, Any]) -> tuple[BenchmarkFinding, ...]:
    findings_data = data.get("findings")
    if not isinstance(findings_data, list):
        raise EvaluationError("candidate.findings must be an array")
    findings: list[BenchmarkFinding] = []
    for item in findings_data:
        if not isinstance(item, dict):
            raise EvaluationError("each candidate finding must be an object")
        findings.append(
            BenchmarkFinding(
                finding_fingerprint=str(item["finding_fingerprint"]),
                severity=item.get("severity"),
            )
        )
    return tuple(findings)


def _forbidden_keys(value: Any) -> set[str]:
    forbidden_tokens = ("ORACLE", "GROUND_TRUTH", "KNOWN_ISSUE", "HISTORICAL_FINDING")
    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                upper = str(key).upper()
                if any(token in upper for token in forbidden_tokens):
                    found.add(str(key))
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return found


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_annotations(data: dict[str, Any]) -> tuple[tuple[BenchmarkMatchAnnotation, ...], tuple[ReviewerDiagnostic, ...]]:
    rows = data.get("annotations", [])
    if not isinstance(rows, list):
        raise EvaluationError("annotations must be an array")
    annotations: list[BenchmarkMatchAnnotation] = []
    diagnostics: list[ReviewerDiagnostic] = []
    for item in rows:
        if not isinstance(item, dict):
            raise EvaluationError("each annotation must be an object")
        annotations.append(
            BenchmarkMatchAnnotation(
                candidate_fingerprint=str(item["candidate_fingerprint"]),
                issue_id=str(item["issue_id"]),
                rationale=str(item["rationale"]),
            )
        )
        evidence_gaps = item.get("evidence_gaps", ())
        reasoning_failures = item.get("reasoning_failures", ())
        if not isinstance(evidence_gaps, list) or not all(isinstance(v, str) for v in evidence_gaps):
            raise EvaluationError("annotation.evidence_gaps must be an array of strings")
        if not isinstance(reasoning_failures, list) or not all(isinstance(v, str) for v in reasoning_failures):
            raise EvaluationError("annotation.reasoning_failures must be an array of strings")
        diagnostics.append(
            ReviewerDiagnostic(
                issue_id=str(item["issue_id"]),
                failure_class=item.get("failure_class"),
                evidence_gaps=tuple(evidence_gaps),
                reasoning_failures=tuple(reasoning_failures),
            )
        )
    return tuple(annotations), tuple(diagnostics)


def evaluate(candidate_path: Path, oracle_path: Path, annotations_path: Path, output_path: Path) -> dict[str, Any]:
    candidate_data = _load_json(candidate_path)
    oracle_data = _load_json(oracle_path)
    annotations_data = _load_json(annotations_path)
    if not isinstance(candidate_data, dict) or not isinstance(oracle_data, dict) or not isinstance(annotations_data, dict):
        raise EvaluationError("candidate, oracle, and annotations must be JSON objects")

    leaked = _forbidden_keys(candidate_data)
    if leaked:
        raise EvaluationError(f"candidate contains forbidden oracle material: {sorted(leaked)}")

    case_data = candidate_data.get("case")
    if not isinstance(case_data, dict):
        raise EvaluationError("candidate.case must be an object")
    case = _load_case(case_data)
    oracle = _load_oracle(oracle_data)
    findings = _load_candidate(candidate_data)
    annotations, diagnostics = _load_annotations(annotations_data)
    evaluation = evaluate_annotated_blind_run(case, oracle, findings, annotations)

    diagnostic_by_issue = {item.issue_id: item for item in diagnostics}
    output = {
        "case_id": evaluation.case_id,
        "candidate_sha256": _sha256(candidate_path),
        "oracle_sha256": _sha256(oracle_path),
        "annotations_sha256": _sha256(annotations_path),
        "true_positives": evaluation.true_positives,
        "false_positives": evaluation.false_positives,
        "false_negatives": len(evaluation.missed_issue_ids),
        "precision": evaluation.precision,
        "recall": evaluation.recall,
        "matched_issue_ids": list(evaluation.matched_issue_ids),
        "missed_issue_ids": list(evaluation.missed_issue_ids),
        "unexpected_fingerprints": list(evaluation.unexpected_fingerprints),
        "severity_matches": evaluation.severity_matches,
        "severity_mismatches": evaluation.severity_mismatches,
        "review_diagnostics": [
            {
                "issue_id": issue_id,
                "failure_class": diagnostic_by_issue[issue_id].failure_class,
                "evidence_gaps": list(diagnostic_by_issue[issue_id].evidence_gaps),
                "reasoning_failures": list(diagnostic_by_issue[issue_id].reasoning_failures),
            }
            for issue_id in sorted(diagnostic_by_issue)
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = evaluate(args.candidate, args.oracle, args.annotations, args.output)
    for key in ("case_id", "true_positives", "false_positives", "false_negatives", "precision", "recall"):
        print(f"{key}={result[key]}")
    print(f"evaluation_output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
