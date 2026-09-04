"""Repository build-system detection, toolchain discovery, and artifact collection.

Build is preparation, not authorized security testing.  A build profile describes
what a repository declares/requests; it does not grant permission to execute the
project's code or contact external systems.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ToolchainSpec:
    """Exact or declared toolchain information discovered from the workspace."""

    tool: str
    version: str | None = None
    source: str = "undetermined"
    executable: str | None = None


@dataclass(frozen=True)
class BuildProfile:
    system: str
    command: tuple[str, ...]
    artifact_roots: tuple[str, ...]
    ast_format: str = "none"
    language: str | None = None
    toolchain: ToolchainSpec | None = None
    config_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildResult:
    status: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    profile: BuildProfile
    artifacts: Mapping[str, dict[str, Any]]
    artifact_paths: tuple[str, ...]
    tool_version: str | None = None
    config_fingerprint: str | None = None
    reproducibility: str = "UNKNOWN"
    dependency_metadata: Mapping[str, Any] | None = None
    dependency_fingerprint: str | None = None


_VERSION_RE = re.compile(r"(?i)(?:rustc|cargo|go|forge|hardhat|node|npm|yarn|pnpm)[^\n]*?(\d+\.\d+(?:\.\d+)?(?:[-+][^\s]+)?)")


def _read(root: Path, name: str) -> str | None:
    path = root / name
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _toolchain_from_rust(root: Path) -> ToolchainSpec:
    toml = _read(root, "rust-toolchain.toml")
    if toml is not None:
        match = re.search(r"(?m)^\s*channel\s*=\s*[\"']([^\"']+)", toml)
        if match:
            return ToolchainSpec("rustup", match.group(1), "rust-toolchain.toml", "cargo")
    plain = _read(root, "rust-toolchain")
    if plain is not None:
        channel = plain.strip().splitlines()[0].strip()
        if channel:
            return ToolchainSpec("rustup", channel, "rust-toolchain", "cargo")
    cargo = _read(root, "Cargo.toml") or ""
    match = re.search(r"(?m)^\s*rust-version\s*=\s*[\"']([^\"']+)", cargo)
    if match:
        return ToolchainSpec("rustc", match.group(1), "Cargo.toml:rust-version", "cargo")
    return ToolchainSpec("rustup", None, "repository-default", "cargo")


def _toolchain_from_foundry(root: Path) -> ToolchainSpec:
    text = _read(root, "foundry.toml") or ""
    match = re.search(r"(?m)^\s*solc_version\s*=\s*[\"']([^\"']+)", text)
    if match:
        return ToolchainSpec("solc", match.group(1), "foundry.toml:solc_version", "forge")
    match = re.search(r"(?m)^\s*solc\s*=\s*[\"']([^\"']+)", text)
    if match:
        return ToolchainSpec("solc", match.group(1), "foundry.toml:solc", "forge")
    return ToolchainSpec("forge", None, "repository-default", "forge")


def _toolchain_from_node(root: Path, executable: str = "node") -> ToolchainSpec:
    for name in (".nvmrc", ".node-version"):
        value = _read(root, name)
        if value and value.strip():
            return ToolchainSpec("node", value.strip().splitlines()[0], name, executable)
    package = _read(root, "package.json") or ""
    try:
        payload = json.loads(package)
    except json.JSONDecodeError:
        payload = {}
    engines = payload.get("engines", {}) if isinstance(payload, Mapping) else {}
    if isinstance(engines, Mapping) and isinstance(engines.get("node"), str):
        return ToolchainSpec("node", engines["node"], "package.json:engines.node", executable)
    return ToolchainSpec("node", None, "repository-default", executable)


class ProjectDetector:
    """Detect the repository's declared build ecosystem without executing it."""

    @staticmethod
    def detect(root: str | Path) -> BuildProfile:
        root = Path(root)
        # Prefer explicit smart-contract build systems over generic Node detection.
        if (root / "foundry.toml").is_file():
            return BuildProfile(
                "foundry", ("forge", "build", "--build-info"), ("out", "build-info"),
                "solc-json-ast", "solidity", _toolchain_from_foundry(root), ("foundry.toml",),
            )
        if any((root / name).is_file() for name in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs", "hardhat.config.mjs")):
            config = tuple(name for name in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs", "hardhat.config.mjs") if (root / name).is_file())
            return BuildProfile(
                "hardhat", ("npx", "hardhat", "compile"), ("artifacts", "cache"),
                "solc-json-ast", "solidity", _toolchain_from_node(root, "node"), config,
            )
        if (root / "Cargo.toml").is_file():
            configs = tuple(name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "rust-toolchain") if (root / name).is_file())
            toolchain = _toolchain_from_rust(root)
            command = ("cargo", f"+{toolchain.version}", "check") if toolchain.version and toolchain.source.startswith("rust-toolchain") else ("cargo", "check")
            return BuildProfile("cargo", command, ("target",), "none", "rust", toolchain, configs)
        if (root / "go.mod").is_file():
            text = _read(root, "go.mod") or ""
            match = re.search(r"(?m)^go\s+(\S+)", text)
            toolchain = ToolchainSpec("go", match.group(1) if match else None, "go.mod:go", "go")
            return BuildProfile("go", ("go", "build", "./..."), ("bin",), "none", "go", toolchain, ("go.mod", "go.sum") if (root / "go.sum").is_file() else ("go.mod",))
        if (root / "pom.xml").is_file():
            return BuildProfile("maven", ("mvn", "-B", "package", "-DskipTests"), ("target",), "none", "java", ToolchainSpec("java", None, "repository-default", "java"), ("pom.xml",))
        if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file() or (root / "gradlew").is_file():
            configs = tuple(name for name in ("build.gradle", "build.gradle.kts", "gradlew", "gradle.properties") if (root / name).is_file())
            return BuildProfile("gradle", ("./gradlew", "build", "-x", "test") if (root / "gradlew").is_file() else ("gradle", "build", "-x", "test"), ("build",), "none", "java", ToolchainSpec("java", None, "repository-default", "java"), configs)
        if (root / "package.json").is_file():
            return BuildProfile("node", ("npm", "run", "build"), ("dist", "build"), "none", "javascript", _toolchain_from_node(root, "node"), ("package.json",))
        raise ValueError(f"unsupported or undetected project build system: {root}")


def _config_fingerprint(root: Path, files: Sequence[str]) -> str | None:
    if not files:
        return None
    digest = hashlib.sha256()
    seen = False
    for name in sorted(set(files)):
        path = root / name
        if path.is_file():
            seen = True
            data = path.read_bytes()
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest() if seen else None


def _resolve_executable(argv0: str, root: Path) -> str | None:
    # Local project wrappers (for example ./gradlew) are intentionally resolved only
    # to a path; they are still untrusted project code and must be sandboxed later.
    if argv0.startswith("./"):
        path = (root / argv0[2:]).resolve()
        return str(path) if path.is_file() else None
    return shutil.which(argv0)


def _tool_version(executable: str | None, root: Path, timeout: int = 20) -> str | None:
    if not executable:
        return None
    for args in (("--version",), ("version",)):
        try:
            completed = subprocess.run([executable, *args], cwd=root, capture_output=True, text=True, check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (completed.stdout or completed.stderr).strip()
        if completed.returncode == 0 and text:
            return text.splitlines()[0][:1000]
    return None


class ProjectBuilder:
    """Build a project and collect compiler-produced semantic artifacts.

    This layer deliberately records the requested and observed toolchain. It does
    not silently install a toolchain or fall back to another compiler, because doing
    so can change program semantics. Network/package installation and sandboxing are
    separate authorization-controlled capabilities.
    """

    def __init__(self, root: str | Path, profile: BuildProfile | None = None):
        self.root = Path(root).resolve()
        self.profile = profile or ProjectDetector.detect(self.root)

    def build(self, *, command: Sequence[str] | None = None, timeout: int = 600) -> BuildResult:
        argv = tuple(command or self.profile.command)
        executable = _resolve_executable(argv[0], self.root)
        if argv[0] == "cargo" and len(argv) > 1 and argv[1].startswith("+"):
            executable = _resolve_executable(argv[0], self.root)
        observed = _tool_version(executable, self.root) if executable else None
        config_fp = _config_fingerprint(self.root, self.profile.config_files)
        try:
            completed = subprocess.run(
                list(argv), cwd=self.root, capture_output=True, text=True, check=False, timeout=timeout,
            )
            status = "SUCCEEDED" if completed.returncode == 0 else "FAILED"
            stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
        except FileNotFoundError as exc:
            status, stdout, stderr, returncode = "TOOLCHAIN_UNAVAILABLE", "", str(exc), 127
        except subprocess.TimeoutExpired as exc:
            status, stdout, stderr, returncode = "TIMEOUT", exc.stdout or "", exc.stderr or "", 124
        # Never consume potentially stale compiler artifacts after a failed build.
        artifacts = collect_solidity_asts(self.root, self.profile) if status == "SUCCEEDED" else ({}, ())
        reproducibility = _reproducibility_state(self.root, self.profile, status)
        dependency_metadata = collect_dependency_metadata(self.root, self.profile) if status == "SUCCEEDED" else None
        dependency_fp = _fingerprint_json(dependency_metadata) if dependency_metadata else None
        return BuildResult(status, argv, returncode, stdout, stderr, self.profile, artifacts[0], artifacts[1], observed, config_fp, reproducibility, dependency_metadata, dependency_fp)




def _fingerprint_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def collect_dependency_metadata(root: str | Path, profile: BuildProfile) -> Mapping[str, Any] | None:
    """Collect resolved dependency metadata without mutating the repository.

    Cargo is the first native resolver integration.  Other ecosystems retain an
    explicit ``None`` until they have a trustworthy machine-readable resolver.
    This is intentionally separate from the build result: a successful compile
    does not imply that dependency provenance was resolved.
    """
    root = Path(root)
    if profile.system != "cargo" or shutil.which("cargo") is None:
        return None
    try:
        result = subprocess.run(
            ["cargo", "metadata", "--format-version", "1", "--locked"],
            cwd=root, capture_output=True, text=True, check=False, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    packages = payload.get("packages")
    resolve = payload.get("resolve")
    return {
        "format_version": payload.get("version"),
        "workspace_members": payload.get("workspace_members", []),
        "workspace_root": payload.get("workspace_root"),
        "packages": packages if isinstance(packages, list) else [],
        "resolve": resolve if isinstance(resolve, dict) else None,
    }

def _reproducibility_state(root: Path, profile: BuildProfile, status: str) -> str:
    """Classify build reproducibility from repository-declared controls.

    This is a conservative classification, not a claim of bit-for-bit identity.
    It only records whether CYDRA found the project's principal lock/toolchain
    controls and whether the build actually succeeded.
    """
    if status != "SUCCEEDED":
        return "NOT_ESTABLISHED"
    files = {path.name for path in root.iterdir() if path.is_file()}
    if profile.system == "cargo":
        if "Cargo.lock" in files and ("rust-toolchain.toml" in files or "rust-toolchain" in files):
            return "DECLARED_REPRODUCIBLE"
        if "Cargo.lock" in files:
            return "LOCKED_DEPENDENCIES"
        return "PARTIAL"
    if profile.system == "foundry":
        return "CONFIGURED" if "foundry.toml" in files else "PARTIAL"
    if profile.system == "node":
        if any(name in files for name in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")):
            return "LOCKED_DEPENDENCIES"
        return "PARTIAL"
    if profile.system == "go":
        return "LOCKED_DEPENDENCIES" if "go.sum" in files else "PARTIAL"
    if profile.system in {"maven", "gradle"}:
        return "CONFIGURED"
    return "PARTIAL"

def collect_solidity_asts(root: str | Path, profile: BuildProfile) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    """Collect ASTs without inventing compiler semantics."""
    root = Path(root)
    result: dict[str, dict[str, Any]] = {}
    artifact_paths: list[str] = []
    candidates: list[Path] = []
    if profile.system == "foundry":
        candidates.extend(sorted((root / "out").rglob("*.json")) if (root / "out").exists() else [])
        candidates.extend(sorted((root / "build-info").rglob("*.json")) if (root / "build-info").exists() else [])
    else:
        for directory in profile.artifact_roots:
            base = root / directory
            if base.exists():
                candidates.extend(sorted(base.rglob("*.json")))

    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        artifact_paths.append(path.relative_to(root).as_posix())
        output = payload.get("output") if isinstance(payload, Mapping) else None
        sources = output.get("sources") if isinstance(output, Mapping) else None
        if isinstance(sources, Mapping):
            for source_path, source_data in sources.items():
                ast = source_data.get("ast") if isinstance(source_data, Mapping) else None
                if isinstance(source_path, str) and isinstance(ast, dict):
                    result[source_path] = ast
        ast = payload.get("ast") if isinstance(payload, Mapping) else None
        source_path = payload.get("sourceName") if isinstance(payload, Mapping) else None
        if isinstance(ast, dict) and isinstance(source_path, str):
            result[source_path] = ast

    return result, tuple(dict.fromkeys(artifact_paths))
