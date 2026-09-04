"""Provenance validation for compiler artifacts before semantic ingestion."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, subprocess
from pathlib import Path
from typing import Any, Mapping

@dataclass(frozen=True)
class ValidatedArtifactSet:
    status: str
    artifacts: Mapping[str, dict[str, Any]]
    artifact_manifest: tuple[tuple[str, str], ...]
    source_bindings: tuple[tuple[str, str, str], ...]
    reason: str
    workspace_fingerprint: str
    config_fingerprint: str | None

def _sha(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def _keccak256(value: bytes) -> str | None:
    """Return Ethereum Keccak-256, never NIST SHA3-256."""
    # Python's hashlib.sha3_256 is a different padding variant and must not be
    # used for Solidity's source `keccak256` field. Prefer OpenSSL's native
    # KECCAK-256 when available; otherwise report that the hash cannot be
    # independently verified.
    try:
        completed = subprocess.run(
            ["openssl", "dgst", "-keccak-256"],
            input=value,
            capture_output=True,
            check=False,
            timeout=5,
        )
        if completed.returncode == 0:
            text = completed.stdout.decode("ascii", errors="ignore").strip()
            if "=" in text:
                digest = text.rsplit("=", 1)[1].strip().lower()
                if len(digest) == 64:
                    return digest
    except (OSError, subprocess.SubprocessError):
        pass
    return None

def _source_hashes(root: Path) -> dict[str, tuple[str, str]]:
    out={}
    for p in root.rglob("*.sol"):
        if any(part in {".git","out","build-info","cache","node_modules"} for part in p.parts): continue
        data=p.read_bytes(); rel=p.relative_to(root).as_posix()
        out[rel]=(_sha(data), _keccak256(data) or "")
    return out

def validate_artifacts(root: str | Path, artifacts: Mapping[str, dict[str, Any]], artifact_paths: tuple[str, ...], *, workspace_fingerprint: str, config_fingerprint: str | None, build_status: str) -> ValidatedArtifactSet:
    """Validate every compiler source binding before AST ingestion.

    An artifact is trusted only when the build succeeded and every source
    reference embedded in the artifact can be bound to the exact workspace
    contents. This prevents a stale artifact from contributing an otherwise
    plausible AST to the reasoning graph.
    """
    root = Path(root)
    manifest: list[tuple[str, str]] = []
    bindings: list[tuple[str, str, str]] = []
    if build_status != "SUCCEEDED":
        return ValidatedArtifactSet(
            "BUILD_NOT_TRUSTED", {}, (), (), "build did not succeed",
            workspace_fingerprint, config_fingerprint,
        )

    source_hashes = _source_hashes(root)
    embedded: dict[str, dict[str, str | None]] = {}

    for ap in artifact_paths:
        p = root / ap
        if not p.is_file():
            return ValidatedArtifactSet(
                "INVALID_ARTIFACT", {}, tuple(manifest), tuple(bindings),
                f"artifact missing: {ap}", workspace_fingerprint, config_fingerprint,
            )
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ValidatedArtifactSet(
                "INVALID_ARTIFACT", {}, tuple(manifest), tuple(bindings),
                f"artifact unreadable: {ap}: {exc}", workspace_fingerprint, config_fingerprint,
            )
        manifest.append((ap, _sha(p.read_bytes())))

        if not isinstance(payload, dict):
            continue
        containers = []
        if isinstance(payload.get("input"), dict):
            containers.append(payload["input"].get("sources", {}))
        if isinstance(payload.get("output"), dict):
            containers.append(payload["output"].get("sources", {}))
        for srcs in containers:
            if not isinstance(srcs, dict):
                continue
            for source_path, rec in srcs.items():
                if not isinstance(source_path, str) or not isinstance(rec, dict):
                    continue
                normalized = Path(source_path).as_posix().lstrip("./")
                item = embedded.setdefault(normalized, {"content": None, "keccak256": None})
                if isinstance(rec.get("content"), str):
                    item["content"] = rec["content"]
                if isinstance(rec.get("keccak256"), str):
                    item["keccak256"] = rec["keccak256"].lower().removeprefix("0x")

    # Validate every source named by the compiler artifact, not only sources
    # that happen to expose an AST.
    for normalized, rec in sorted(embedded.items()):
        workspace_path = root / normalized
        if normalized not in source_hashes or not workspace_path.is_file():
            return ValidatedArtifactSet(
                "MISSING_SOURCE", {}, tuple(manifest), tuple(bindings),
                f"artifact source absent from workspace: {normalized}",
                workspace_fingerprint, config_fingerprint,
            )
        workspace_bytes = workspace_path.read_bytes()
        content = rec.get("content")
        if isinstance(content, str):
            if workspace_bytes != content.encode("utf-8"):
                return ValidatedArtifactSet(
                    "MISMATCHED_SOURCE", {}, tuple(manifest), tuple(bindings),
                    f"compiler source content mismatch: {normalized}",
                    workspace_fingerprint, config_fingerprint,
                )
        compiler_hash = rec.get("keccak256")
        if isinstance(compiler_hash, str):
            actual_keccak = _keccak256(workspace_bytes)
            if actual_keccak is None:
                return ValidatedArtifactSet(
                    "INVALID_ARTIFACT", {}, tuple(manifest), tuple(bindings),
                    f"cannot independently verify compiler keccak256: {normalized}",
                    workspace_fingerprint, config_fingerprint,
                )
            if actual_keccak != compiler_hash:
                return ValidatedArtifactSet(
                    "MISMATCHED_SOURCE", {}, tuple(manifest), tuple(bindings),
                    f"compiler source hash mismatch: {normalized}",
                    workspace_fingerprint, config_fingerprint,
                )
        sha, _ = source_hashes[normalized]
        bindings.append((normalized, sha, compiler_hash or ""))

    accepted: dict[str, dict[str, Any]] = {}
    for source_path, ast in artifacts.items():
        normalized = Path(source_path).as_posix().lstrip("./")
        if normalized not in source_hashes:
            return ValidatedArtifactSet(
                "MISSING_SOURCE", {}, tuple(manifest), tuple(bindings),
                f"artifact source absent from workspace: {source_path}",
                workspace_fingerprint, config_fingerprint,
            )
        # If the artifact exposes source records, that source must have passed
        # the complete provenance check above. Otherwise reject rather than
        # silently trusting an AST detached from compiler source metadata.
        if embedded and normalized not in embedded:
            return ValidatedArtifactSet(
                "INVALID_ARTIFACT", {}, tuple(manifest), tuple(bindings),
                f"AST source lacks compiler source binding: {source_path}",
                workspace_fingerprint, config_fingerprint,
            )
        accepted[normalized] = ast

    return ValidatedArtifactSet(
        "VALID", accepted, tuple(manifest), tuple(bindings),
        "artifact provenance validated", workspace_fingerprint, config_fingerprint,
    )
