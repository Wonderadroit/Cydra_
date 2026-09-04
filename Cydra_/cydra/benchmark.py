from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from .contest import ContestRules, KnownIssue, KnownIssueBaseline


class BenchmarkError(ValueError):
    """Raised when a blind benchmark contract is malformed."""


@dataclass(frozen=True)
class BlindBenchmarkCase:
    """Input envelope for a historical audit benchmark.

    This object intentionally contains no historical findings or evaluation
    oracle. It is safe to hand to an investigation runner as blind input.
    """

    case_id: str
    contest_name: str
    repository: str
    revision: str
    rules: ContestRules
    input_manifest: tuple[str, ...] = ()

    def fingerprint(self) -> str:
        payload = {
            "case_id": self.case_id,
            "contest_name": self.contest_name,
            "repository": self.repository,
            "revision": self.revision,
            "rules": {
                "name": self.rules.name,
                "in_scope": list(self.rules.in_scope),
                "out_of_scope": list(self.rules.out_of_scope),
                "forbidden_actions": list(self.rules.forbidden_actions),
                "allowed_actions": list(self.rules.allowed_actions),
                "notes": list(self.rules.notes),
            },
            "input_manifest": list(self.input_manifest),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class BenchmarkFinding:
    """Evaluator-side finding identity emitted by a blind run."""

    finding_fingerprint: str
    severity: str | None = None


@dataclass(frozen=True)
class BenchmarkMatchAnnotation:
    """Explicit evaluator annotation connecting a candidate to one oracle issue.

    This is deliberately created after the blind run. The benchmark does not
    pretend that string similarity or independently generated fingerprints prove
    semantic equivalence. A reviewer must make the correspondence explicit and
    provide a short rationale that can be audited later.
    """

    candidate_fingerprint: str
    issue_id: str
    rationale: str


@dataclass(frozen=True)
class BenchmarkEvaluation:
    """Deterministic comparison of blind-run findings against a sealed oracle."""

    case_id: str
    matched_issue_ids: tuple[str, ...]
    missed_issue_ids: tuple[str, ...]
    unexpected_fingerprints: tuple[str, ...]
    severity_matches: int
    severity_mismatches: int

    @property
    def true_positives(self) -> int:
        return len(self.matched_issue_ids)

    @property
    def false_positives(self) -> int:
        return len(self.unexpected_fingerprints)

    @property
    def recall(self) -> float:
        denominator = self.true_positives + len(self.missed_issue_ids)
        return self.true_positives / denominator if denominator else 1.0

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 1.0


@dataclass(frozen=True)
class BenchmarkOracle:
    """Evaluation-only oracle kept outside the blind investigation input."""

    baseline: KnownIssueBaseline


def build_oracle(issues: Sequence[KnownIssue]) -> BenchmarkOracle:
    """Build an evaluator oracle from externally curated historical issues."""
    issue_list = tuple(issues)
    fingerprints = [issue.fingerprint for issue in issue_list]
    if len(set(fingerprints)) != len(fingerprints):
        raise BenchmarkError("historical issue fingerprints must be unique")
    return BenchmarkOracle(KnownIssueBaseline.from_iterable(issue_list))


def _validate_candidates(findings: Sequence[BenchmarkFinding]) -> tuple[BenchmarkFinding, ...]:
    candidates = tuple(findings)
    candidate_fingerprints = tuple(item.finding_fingerprint for item in candidates)
    if any(not fingerprint.strip() for fingerprint in candidate_fingerprints):
        raise BenchmarkError("candidate finding fingerprints must not be empty")
    if len(set(candidate_fingerprints)) != len(candidate_fingerprints):
        raise BenchmarkError("duplicate candidate finding fingerprints are not allowed")
    return candidates


def evaluate_blind_run(
    case: BlindBenchmarkCase,
    oracle: BenchmarkOracle,
    findings: Sequence[BenchmarkFinding],
) -> BenchmarkEvaluation:
    """Compare exact fingerprints for synthetic/unit-test benchmark cases.

    Real historical evaluations should use ``evaluate_annotated_blind_run`` so
    semantic equivalence is established explicitly rather than requiring the
    candidate to reproduce an oracle-generated fingerprint.
    """
    if not case.case_id.strip():
        raise BenchmarkError("benchmark case_id must not be empty")

    candidates = _validate_candidates(findings)
    matched: list[str] = []
    missed: list[str] = []
    severity_matches = 0
    severity_mismatches = 0

    for issue in oracle.baseline.issues:
        matches = [
            candidate
            for candidate in candidates
            if candidate.finding_fingerprint == issue.fingerprint
        ]
        if not matches:
            missed.append(issue.issue_id)
            continue
        matched.append(issue.issue_id)
        candidate = matches[0]
        if issue.severity is None or candidate.severity is None:
            continue
        if issue.severity == candidate.severity:
            severity_matches += 1
        else:
            severity_mismatches += 1

    known_fingerprints = {issue.fingerprint for issue in oracle.baseline.issues}
    unexpected = sorted(
        fingerprint
        for fingerprint in tuple(item.finding_fingerprint for item in candidates)
        if fingerprint not in known_fingerprints
    )

    return BenchmarkEvaluation(
        case_id=case.case_id,
        matched_issue_ids=tuple(sorted(matched)),
        missed_issue_ids=tuple(sorted(missed)),
        unexpected_fingerprints=tuple(unexpected),
        severity_matches=severity_matches,
        severity_mismatches=severity_mismatches,
    )


def evaluate_annotated_blind_run(
    case: BlindBenchmarkCase,
    oracle: BenchmarkOracle,
    findings: Sequence[BenchmarkFinding],
    annotations: Sequence[BenchmarkMatchAnnotation],
) -> BenchmarkEvaluation:
    """Evaluate real historical findings using explicit post-run annotations.

    The annotations are evaluator output, not investigation input. Each candidate
    may match at most one historical issue, each historical issue may be matched
    at most once, and every annotation must name an existing candidate and issue
    plus a non-empty review rationale. Unannotated candidates remain false
    positives; unannotated oracle issues remain misses.
    """
    if not case.case_id.strip():
        raise BenchmarkError("benchmark case_id must not be empty")

    candidates = _validate_candidates(findings)
    candidate_by_fp = {item.finding_fingerprint: item for item in candidates}
    issues_by_id = {issue.issue_id: issue for issue in oracle.baseline.issues}
    if len(issues_by_id) != len(oracle.baseline.issues):
        raise BenchmarkError("historical issue IDs must be unique")

    annotations = tuple(annotations)
    matched_candidates: set[str] = set()
    matched_issues: set[str] = set()
    matched: list[str] = []
    severity_matches = 0
    severity_mismatches = 0

    for annotation in annotations:
        if not annotation.candidate_fingerprint.strip():
            raise BenchmarkError("annotation candidate fingerprint must not be empty")
        if not annotation.issue_id.strip():
            raise BenchmarkError("annotation issue ID must not be empty")
        if not annotation.rationale.strip():
            raise BenchmarkError("annotation rationale must not be empty")
        if annotation.candidate_fingerprint not in candidate_by_fp:
            raise BenchmarkError("annotation references an unknown candidate fingerprint")
        if annotation.issue_id not in issues_by_id:
            raise BenchmarkError("annotation references an unknown historical issue")
        if annotation.candidate_fingerprint in matched_candidates:
            raise BenchmarkError("candidate may not be matched to multiple historical issues")
        if annotation.issue_id in matched_issues:
            raise BenchmarkError("historical issue may not be matched to multiple candidates")

        candidate = candidate_by_fp[annotation.candidate_fingerprint]
        issue = issues_by_id[annotation.issue_id]
        matched_candidates.add(annotation.candidate_fingerprint)
        matched_issues.add(annotation.issue_id)
        matched.append(issue.issue_id)
        if issue.severity is not None and candidate.severity is not None:
            if issue.severity == candidate.severity:
                severity_matches += 1
            else:
                severity_mismatches += 1

    missed = sorted(issue_id for issue_id in issues_by_id if issue_id not in matched_issues)
    unexpected = sorted(
        fingerprint for fingerprint in candidate_by_fp if fingerprint not in matched_candidates
    )

    return BenchmarkEvaluation(
        case_id=case.case_id,
        matched_issue_ids=tuple(sorted(matched)),
        missed_issue_ids=tuple(missed),
        unexpected_fingerprints=tuple(unexpected),
        severity_matches=severity_matches,
        severity_mismatches=severity_mismatches,
    )
