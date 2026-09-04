"""Deterministic repository acquisition and build-preparation boundary.

This module owns filesystem materialization only. It does not reason about
vulnerabilities, grant testing authority, or execute application tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RepositorySpec:
    repository: str
    revision: str

    def __post_init__(self) -> None:
        if not self.repository.strip() or not self.revision.strip():
            raise ValueError("repository and revision are required")


@dataclass(frozen=True)
class WorkspaceManifest:
    root: str
    repository: str
    revision: str
    commit: str
    files: tuple[tuple[str, str], ...]
    fingerprint: str


class RepositoryWorkspace:
    """Materialize and verify an exact repository revision in an isolated path."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    @staticmethod
    def _git(root: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    def clone(self, spec: RepositorySpec, *, git_executable: str = "git") -> WorkspaceManifest:
        if self.root.exists() and any(self.root.iterdir()):
            raise FileExistsError(f"workspace is not empty: {self.root}")
        self.root.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [git_executable, "clone", "--no-tags", spec.repository, str(self.root)],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"git clone failed ({completed.returncode}): {(completed.stderr or completed.stdout).strip()}")
        checkout = self._git(self.root, "checkout", "--detach", spec.revision)
        if checkout.returncode != 0:
            raise RuntimeError(f"git checkout failed ({checkout.returncode}): {(checkout.stderr or checkout.stdout).strip()}")
        return self.manifest(spec.repository, spec.revision)

    def manifest(self, repository: str, revision: str) -> WorkspaceManifest:
        if not self.root.is_dir():
            raise FileNotFoundError(f"workspace does not exist: {self.root}")
        commit_result = self._git(self.root, "rev-parse", "HEAD")
        if commit_result.returncode != 0:
            raise RuntimeError("workspace is not a readable git repository")
        commit = commit_result.stdout.strip()
        expected = self._git(self.root, "rev-parse", revision)
        if expected.returncode != 0 or expected.stdout.strip() != commit:
            raise ValueError(f"workspace revision mismatch: requested {revision}, checked out {commit}")

        files: list[tuple[str, str]] = []
        digest = sha256()
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or ".git" in path.parts or any(p in {"out", "cache", "broadcast"} for p in path.parts):
                continue
            relative = path.relative_to(self.root).as_posix()
            file_digest = sha256(path.read_bytes()).hexdigest()
            files.append((relative, file_digest))
            digest.update(relative.encode("utf-8"))
            digest.update(file_digest.encode("ascii"))
        fingerprint = f"workspace:{digest.hexdigest()}"
        return WorkspaceManifest(str(self.root), repository, revision, commit, tuple(files), fingerprint)

    def source_files(self, extensions: Iterable[str] = (".sol", ".py", ".rs", ".ts", ".js")) -> dict[str, str]:
        allowed = {ext.lower() for ext in extensions}
        sources: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or ".git" in path.parts or any(p in {"out", "cache", "broadcast", "node_modules"} for p in path.parts):
                continue
            if path.suffix.lower() not in allowed:
                continue
            relative = path.relative_to(self.root).as_posix()
            try:
                sources[relative] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        return sources
