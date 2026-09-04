from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class ContestRules:
    """Machine-readable constraints for an authorized audit engagement."""

    name: str
    in_scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def classify_target(self, target: str) -> str:
        if target in self.out_of_scope:
            return "OUT_OF_SCOPE"
        if target in self.in_scope:
            return "IN_SCOPE"
        return "UNKNOWN"

    def action_allowed(self, action: str) -> bool:
        if action in self.forbidden_actions:
            return False
        if self.allowed_actions:
            return action in self.allowed_actions
        return True


@dataclass(frozen=True)
class KnownIssue:
    issue_id: str
    title: str
    fingerprint: str
    severity: Optional[str] = None
    notes: str = ""


@dataclass
class KnownIssueBaseline:
    issues: list[KnownIssue] = field(default_factory=list)

    def add(self, issue: KnownIssue) -> None:
        if any(existing.issue_id == issue.issue_id for existing in self.issues):
            raise ValueError(f"duplicate known issue id: {issue.issue_id}")
        self.issues.append(issue)

    def match(self, fingerprint: str) -> list[KnownIssue]:
        return [issue for issue in self.issues if issue.fingerprint == fingerprint]

    def is_known(self, fingerprint: str) -> bool:
        return bool(self.match(fingerprint))

    @classmethod
    def from_iterable(cls, issues: Iterable[KnownIssue]) -> "KnownIssueBaseline":
        baseline = cls()
        for issue in issues:
            baseline.add(issue)
        return baseline
