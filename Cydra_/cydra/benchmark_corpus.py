from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Sequence


class BenchmarkCorpusError(ValueError):
    """Raised when a blind benchmark corpus definition is unsafe or invalid."""


_ORACLE_PATH_RE = re.compile(
    r"(^|/)(?:4naly3er-report|report|reports?|findings?|known[-_ ]?issues?)(?:\.|/|$)",
    re.IGNORECASE,
)


def _matches_manifest_path(declaration: str, path: str) -> bool:
    """Match exact files or explicitly declared directory prefixes only."""
    return declaration == path or (declaration.endswith("/") and path.startswith(declaration))


def _manifest_declarations_overlap(left: str, right: str) -> bool:
    """Return whether two exact/prefix declarations can select the same path."""
    return _matches_manifest_path(left, right) or _matches_manifest_path(right, left)


@dataclass(frozen=True)
class BenchmarkCorpusEntry:
    case_id: str
    contest_name: str
    repository: str
    revision: str
    input_paths: tuple[str, ...]
    excluded_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.contest_name.strip() or not self.repository.strip():
            raise BenchmarkCorpusError("case, contest, and repository must not be empty")
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise BenchmarkCorpusError("benchmark revision must be a full 40-character commit SHA")
        if not self.input_paths:
            raise BenchmarkCorpusError("blind benchmark entry requires at least one input path")
        if any(not path or path != path.strip() for path in (*self.input_paths, *self.excluded_paths)):
            raise BenchmarkCorpusError("benchmark paths must be non-empty and trimmed")
        if len(set(self.input_paths)) != len(self.input_paths):
            raise BenchmarkCorpusError("duplicate blind input paths are not allowed")
        if len(set(self.excluded_paths)) != len(self.excluded_paths):
            raise BenchmarkCorpusError("duplicate excluded paths are not allowed")
        if any(_ORACLE_PATH_RE.search(path) for path in self.input_paths):
            raise BenchmarkCorpusError("historical report/oracle paths cannot be blind inputs")
        if any(
            _manifest_declarations_overlap(input_path, excluded_path)
            for input_path in self.input_paths
            for excluded_path in self.excluded_paths
        ):
            raise BenchmarkCorpusError("blind input and excluded path declarations overlap")

    def fingerprint(self) -> str:
        payload = {
            "case_id": self.case_id,
            "contest_name": self.contest_name,
            "repository": self.repository,
            "revision": self.revision,
            "input_paths": list(self.input_paths),
            "excluded_paths": list(self.excluded_paths),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def validate_selected_paths(self, selected_paths: Sequence[str]) -> None:
        """Ensure every materialized file is explicitly allowed and not excluded."""
        for path in selected_paths:
            if not isinstance(path, str) or not path:
                raise BenchmarkCorpusError("selected benchmark paths must be non-empty strings")
            if _ORACLE_PATH_RE.search(path):
                raise BenchmarkCorpusError(f"excluded benchmark path: {path}")
            if any(_matches_manifest_path(excluded, path) for excluded in self.excluded_paths):
                raise BenchmarkCorpusError(f"excluded benchmark path: {path}")
            if not any(_matches_manifest_path(allowed, path) for allowed in self.input_paths):
                raise BenchmarkCorpusError(f"path is not in blind input manifest: {path}")


def validate_corpus(entries: Sequence[BenchmarkCorpusEntry]) -> tuple[BenchmarkCorpusEntry, ...]:
    seen: set[str] = set()
    validated: list[BenchmarkCorpusEntry] = []
    for entry in entries:
        if entry.case_id in seen:
            raise BenchmarkCorpusError(f"duplicate benchmark case ID: {entry.case_id}")
        seen.add(entry.case_id)
        entry.validate_selected_paths(entry.input_paths)
        validated.append(entry)
    return tuple(validated)
