"""Repository-native toolchain requirements and resolution state.

This module only describes and resolves build prerequisites. It never installs
software and never grants permission to execute repository-controlled code.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .project_build import BuildProfile, ToolchainSpec


class ToolchainState:
    AVAILABLE = "AVAILABLE"
    PROVISIONABLE = "PROVISIONABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNDECLARED = "UNDECLARED"
    MISMATCHED = "MISMATCHED"


@dataclass(frozen=True)
class ToolchainContract:
    system: str
    language: str | None
    requested: ToolchainSpec | None
    executable: str | None
    observed_version: str | None
    state: str
    config_fingerprint: str | None = None
    rationale: str = ""


def _version_tokens(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = re.search(r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _matches(requested: str | None, observed: str | None, *, minimum: bool = False) -> bool:
    if not requested:
        return bool(observed)
    req = _version_tokens(requested)
    got = _version_tokens(observed)
    if req is None or got is None:
        return requested.strip() in (observed or "")
    if minimum:
        return got >= req
    return got == req


class ToolchainResolver:
    """Resolve a declared toolchain against the current host without installing."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    @staticmethod
    def _executable(profile: BuildProfile) -> str | None:
        if profile.toolchain is None or not profile.command:
            return None
        executable = profile.command[0]
        if executable.startswith("./"):
            candidate = Path(executable[2:])
            return str(candidate) if candidate.is_file() else None
        return shutil.which(executable)

    @staticmethod
    def _version(executable: str | None) -> str | None:
        if not executable:
            return None
        for args in (("--version",), ("version",)):
            try:
                result = subprocess.run([executable, *args], capture_output=True, text=True, check=False, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0:
                text = (result.stdout or result.stderr).strip()
                if text:
                    return text.splitlines()[0][:1000]
        return None

    @staticmethod
    def _rustup_version(channel: str) -> str | None:
        rustc = shutil.which("rustc")
        if not rustc:
            return None
        try:
            result = subprocess.run([rustc, f"+{channel}", "--version"], capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        text = (result.stdout or result.stderr).strip()
        return text.splitlines()[0][:1000] if text else None

    def resolve(self, profile: BuildProfile, *, config_fingerprint: str | None = None) -> ToolchainContract:
        requested = profile.toolchain
        if requested is None:
            return ToolchainContract(profile.system, profile.language, None, None, None, ToolchainState.UNDECLARED, config_fingerprint, "build system did not declare a toolchain")
        executable = self._executable(profile)
        if executable is None:
            return ToolchainContract(profile.system, profile.language, requested, None, None, ToolchainState.UNAVAILABLE, config_fingerprint, "required executable is not available on the host")
        observed = self._rustup_version(requested.version) if requested.tool == "rustup" and requested.version else self._version(executable)
        if observed is None:
            return ToolchainContract(profile.system, profile.language, requested, executable, None, ToolchainState.UNAVAILABLE, config_fingerprint, "executable exists but its version could not be established")

        # Cargo.toml rust-version is a minimum supported version, unlike an explicit
        # rust-toolchain channel which is an exact repository-selected toolchain.
        minimum = requested.source.startswith("Cargo.toml:rust-version")
        if _matches(requested.version, observed, minimum=minimum):
            return ToolchainContract(profile.system, profile.language, requested, executable, observed, ToolchainState.AVAILABLE, config_fingerprint, "host toolchain satisfies repository declaration")
        return ToolchainContract(profile.system, profile.language, requested, executable, observed, ToolchainState.MISMATCHED, config_fingerprint, "host toolchain does not satisfy repository declaration")


def build_command_for_contract(profile: BuildProfile, contract: ToolchainContract) -> tuple[str, ...]:
    """Return the repository-native build command only when the toolchain is usable."""
    if contract.state != ToolchainState.AVAILABLE:
        raise RuntimeError(f"cannot build with toolchain state {contract.state}")
    return tuple(profile.command)
