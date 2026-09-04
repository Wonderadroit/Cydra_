from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from .benchmark_corpus import BenchmarkCorpusEntry, BenchmarkCorpusError, _ORACLE_PATH_RE


class BenchmarkMaterializationError(BenchmarkCorpusError):
    """Raised when a blind benchmark snapshot cannot be safely materialized."""


@dataclass(frozen=True)
class MaterializedBenchmarkInput:
    """Immutable receipt describing exactly what entered a blind run.

    The receipt contains source provenance and file digests only. It deliberately
    contains no historical findings, issue IDs, report text, or evaluator oracle.
    """

    case_id: str
    corpus_fingerprint: str
    repository: str
    revision: str
    selected_paths: tuple[str, ...]
    file_manifest: tuple[tuple[str, str], ...]

    def fingerprint(self) -> str:
        payload = {
            "case_id": self.case_id,
            "corpus_fingerprint": self.corpus_fingerprint,
            "repository": self.repository,
            "revision": self.revision,
            "selected_paths": list(self.selected_paths),
            "file_manifest": list(self.file_manifest),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_json(self) -> str:
        return json.dumps(
            {
                "case_id": self.case_id,
                "corpus_fingerprint": self.corpus_fingerprint,
                "repository": self.repository,
                "revision": self.revision,
                "selected_paths": list(self.selected_paths),
                "file_manifest": [
                    {"path": path, "sha256": digest} for path, digest in self.file_manifest
                ],
                "snapshot_fingerprint": self.fingerprint(),
            },
            sort_keys=True,
            indent=2,
        )


def _git_revision(source_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BenchmarkMaterializationError(
            "source root must be a readable git checkout at the pinned revision"
        ) from exc
    revision = result.stdout.strip()
    if not revision:
        raise BenchmarkMaterializationError("git checkout returned an empty revision")
    return revision


def _require_clean_checkout(source_root: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BenchmarkMaterializationError("unable to verify historical checkout cleanliness") from exc
    if result.stdout.strip():
        raise BenchmarkMaterializationError("source checkout is dirty; uncommitted/untracked content is forbidden")


def _safe_relative(root: Path, path: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise BenchmarkMaterializationError(f"path escapes benchmark root: {path}") from exc


def _expand_path(root: Path, declared: str) -> list[Path]:
    relative = Path(declared)
    candidate = root / relative
    if not candidate.exists():
        raise BenchmarkMaterializationError(f"declared benchmark path is missing: {declared}")
    if candidate.is_symlink():
        raise BenchmarkMaterializationError(f"symlinked benchmark input is forbidden: {declared}")
    if candidate.is_file():
        return [candidate]
    if candidate.is_dir():
        paths: list[Path] = []
        for item in sorted(candidate.rglob("*")):
            if item.is_symlink():
                raise BenchmarkMaterializationError(
                    f"symlinked benchmark input is forbidden: {_safe_relative(root, item).as_posix()}"
                )
            if item.is_file():
                paths.append(item)
        return paths
    raise BenchmarkMaterializationError(f"unsupported benchmark input: {declared}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_blind_input(
    entry: BenchmarkCorpusEntry,
    source_root: str | Path,
    destination_root: str | Path,
) -> MaterializedBenchmarkInput:
    """Copy exactly the frozen blind inputs into a clean staging directory.

    The source checkout must be at the manifest's exact commit and have no
    uncommitted or untracked content. Every selected file is checked against the
    corpus path contract before copying. Existing destination content is removed
    so stale files cannot contaminate a run.
    """
    root = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    if not root.is_dir():
        raise BenchmarkMaterializationError(f"source root is not a directory: {root}")
    if root == destination or root in destination.parents:
        raise BenchmarkMaterializationError("destination must not be inside source root")

    actual_revision = _git_revision(root)
    if actual_revision.lower() != entry.revision.lower():
        raise BenchmarkMaterializationError(
            f"source revision mismatch: expected {entry.revision}, got {actual_revision}"
        )
    _require_clean_checkout(root)

    selected: dict[str, Path] = {}
    for declared in entry.input_paths:
        entry.validate_selected_paths((declared,))
        for path in _expand_path(root, declared):
            relative = _safe_relative(root, path).as_posix()
            if _ORACLE_PATH_RE.search(relative):
                raise BenchmarkMaterializationError(f"oracle-like source path cannot enter blind input: {relative}")
            if any(
                relative == excluded or relative.startswith(excluded.rstrip("/") + "/")
                for excluded in entry.excluded_paths
            ):
                raise BenchmarkMaterializationError(f"excluded path selected by manifest: {relative}")
            if relative in selected:
                raise BenchmarkMaterializationError(f"duplicate materialized path: {relative}")
            selected[relative] = path

    if not selected:
        raise BenchmarkMaterializationError("blind input manifest selected no files")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    manifest: list[tuple[str, str]] = []
    for relative, source in sorted(selected.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest.append((relative, _sha256_file(target)))

    receipt = MaterializedBenchmarkInput(
        case_id=entry.case_id,
        corpus_fingerprint=entry.fingerprint(),
        repository=entry.repository,
        revision=entry.revision,
        selected_paths=tuple(relative for relative, _ in manifest),
        file_manifest=tuple(manifest),
    )
    (destination / ".cydra-blind-receipt.json").write_text(receipt.to_json() + "\n", encoding="utf-8")
    return receipt


def validate_materialized_input(
    entry: BenchmarkCorpusEntry,
    materialized_root: str | Path,
    receipt: MaterializedBenchmarkInput,
) -> None:
    """Revalidate a staged blind input before handing it to CYDRA."""
    root = Path(materialized_root).resolve()
    if not root.is_dir():
        raise BenchmarkMaterializationError(f"materialized root is not a directory: {root}")
    if receipt.case_id != entry.case_id or receipt.corpus_fingerprint != entry.fingerprint():
        raise BenchmarkMaterializationError("materialized receipt is bound to a different corpus entry")
    if receipt.repository != entry.repository or receipt.revision.lower() != entry.revision.lower():
        raise BenchmarkMaterializationError("materialized receipt provenance does not match corpus")
    if tuple(sorted(receipt.selected_paths)) != receipt.selected_paths:
        raise BenchmarkMaterializationError("materialized paths are not canonicalized")
    if tuple(sorted(receipt.file_manifest)) != receipt.file_manifest:
        raise BenchmarkMaterializationError("materialized file manifest is not canonicalized")
    entry.validate_selected_paths(receipt.selected_paths)

    expected = set(receipt.selected_paths)
    actual_files: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BenchmarkMaterializationError(
                f"symlinked materialized content is forbidden: {_safe_relative(root, path).as_posix()}"
            )
        if not path.is_file():
            continue
        relative = _safe_relative(root, path).as_posix()
        if relative == ".cydra-blind-receipt.json":
            continue
        if _ORACLE_PATH_RE.search(relative):
            raise BenchmarkMaterializationError(f"oracle-like materialized path detected: {relative}")
        actual_files.add(relative)

    if actual_files != expected:
        extras = sorted(actual_files - expected)
        missing = sorted(expected - actual_files)
        detail = extras[0] if extras else missing[0]
        raise BenchmarkMaterializationError(f"materialized file set differs from receipt: {detail}")

    actual: list[tuple[str, str]] = []
    for relative in receipt.selected_paths:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise BenchmarkMaterializationError(f"materialized input missing or unsafe: {relative}")
        actual.append((relative, _sha256_file(path)))
    if tuple(actual) != receipt.file_manifest:
        raise BenchmarkMaterializationError("materialized file manifest does not match receipt")

    receipt_path = root / ".cydra-blind-receipt.json"
    if not receipt_path.is_file():
        raise BenchmarkMaterializationError("blind receipt is missing")
    try:
        stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkMaterializationError("blind receipt is unreadable") from exc
    if stored.get("snapshot_fingerprint") != receipt.fingerprint():
        raise BenchmarkMaterializationError("blind receipt fingerprint mismatch")


def _git_blob_sha256_compatible(path: str, content: bytes) -> str:
    """Return Git's SHA-1 blob object identity for connector-supplied bytes."""
    import hashlib as _hashlib
    header = f"blob {len(content)}\0".encode("ascii")
    return _hashlib.sha1(header + content).hexdigest()


def materialize_blind_snapshot(
    entry: BenchmarkCorpusEntry,
    repository: str,
    revision: str,
    files: Sequence[tuple[str, str, bytes]],
    destination_root: str | Path,
) -> MaterializedBenchmarkInput:
    """Materialize an exact Git-object snapshot without requiring a local clone.

    ``files`` contains ``(path, git_blob_sha, content)`` tuples obtained from a
    trusted repository API/connector. Every selected file is verified against its
    Git blob identity before entering the blind staging area. This preserves the
    benchmark's exact-revision contract when the execution environment cannot
    perform a networked ``git clone``.

    The caller must obtain the file list from the pinned commit's tree. This
    function never treats filenames, current branches, or content similarity as
    proof of revision identity.
    """
    if repository != entry.repository:
        raise BenchmarkMaterializationError("snapshot repository does not match corpus entry")
    if revision.lower() != entry.revision.lower():
        raise BenchmarkMaterializationError("snapshot revision does not match corpus entry")

    destination = Path(destination_root).resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    selected: dict[str, bytes] = {}
    manifest: list[tuple[str, str]] = []
    seen: set[str] = set()
    for relative, expected_blob_sha, content in files:
        if relative in seen:
            raise BenchmarkMaterializationError(f"duplicate snapshot path: {relative}")
        seen.add(relative)
        entry.validate_selected_paths((relative,))
        if _ORACLE_PATH_RE.search(relative):
            raise BenchmarkMaterializationError(f"oracle-like source path cannot enter blind input: {relative}")
        if not isinstance(content, bytes):
            raise BenchmarkMaterializationError(f"snapshot content must be bytes: {relative}")
        actual_blob_sha = _git_blob_sha256_compatible(relative, content)
        if actual_blob_sha.lower() != expected_blob_sha.lower():
            raise BenchmarkMaterializationError(
                f"Git blob mismatch for {relative}: expected {expected_blob_sha}, got {actual_blob_sha}"
            )
        selected[relative] = content

    expected_paths = set()
    for declared in entry.input_paths:
        if not declared.endswith("/"):
            expected_paths.add(declared)
        else:
            expected_paths.update(path for path in selected if path.startswith(declared))
    if not selected:
        raise BenchmarkMaterializationError("snapshot selected no files")

    for relative, content in sorted(selected.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        manifest.append((relative, _sha256_file(target)))

    receipt = MaterializedBenchmarkInput(
        case_id=entry.case_id,
        corpus_fingerprint=entry.fingerprint(),
        repository=entry.repository,
        revision=entry.revision,
        selected_paths=tuple(path for path, _ in manifest),
        file_manifest=tuple(manifest),
    )
    (destination / ".cydra-blind-receipt.json").write_text(receipt.to_json() + "\n", encoding="utf-8")
    validate_materialized_input(entry, destination, receipt)
    return receipt
