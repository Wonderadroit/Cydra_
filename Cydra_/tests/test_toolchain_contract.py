from pathlib import Path

import pytest

from cydra.project_build import ProjectDetector, ToolchainSpec, BuildProfile
from cydra.toolchain_contract import ToolchainResolver, ToolchainState, build_command_for_contract


def test_rust_toolchain_file_is_exact_requirement(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n')
    (tmp_path / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.82.0"\n')
    profile = ProjectDetector.detect(tmp_path)
    assert profile.toolchain == ToolchainSpec("rustup", "1.82.0", "rust-toolchain.toml", "cargo")
    assert profile.command == ("cargo", "+1.82.0", "check")


def test_rust_version_is_minimum_requirement():
    profile = BuildProfile("cargo", ("cargo", "check"), ("target",), language="rust", toolchain=ToolchainSpec("rustc", "1.70", "Cargo.toml:rust-version", "cargo"))
    resolver = ToolchainResolver(".")
    assert resolver._version is not None
    # The semantic matcher is tested independently from the host installation.
    from cydra.toolchain_contract import _matches
    assert _matches("1.70", "rustc 1.82.0", minimum=True)
    assert not _matches("1.83", "rustc 1.82.0", minimum=True)


def test_unavailable_toolchain_blocks_build(tmp_path: Path, monkeypatch):
    profile = BuildProfile("cargo", ("cargo", "check"), ("target",), language="rust", toolchain=ToolchainSpec("rustup", "1.82.0", "rust-toolchain.toml", "cargo"))
    resolver = ToolchainResolver(tmp_path)
    monkeypatch.setattr("cydra.toolchain_contract.shutil.which", lambda _: None)
    contract = resolver.resolve(profile)
    assert contract.state == ToolchainState.UNAVAILABLE
    with pytest.raises(RuntimeError):
        build_command_for_contract(profile, contract)


def test_mismatched_exact_toolchain_blocks_build(tmp_path: Path, monkeypatch):
    profile = BuildProfile("cargo", ("cargo", "+1.82.0", "check"), ("target",), language="rust", toolchain=ToolchainSpec("rustup", "1.82.0", "rust-toolchain.toml", "cargo"))
    resolver = ToolchainResolver(tmp_path)
    monkeypatch.setattr("cydra.toolchain_contract.shutil.which", lambda _: "/usr/bin/cargo")
    monkeypatch.setattr(ToolchainResolver, "_rustup_version", staticmethod(lambda _: "rustc 1.83.0 (x)"))
    contract = resolver.resolve(profile)
    assert contract.state == ToolchainState.MISMATCHED


def test_exact_rustup_requirement_checks_rustc_not_cargo(tmp_path: Path, monkeypatch):
    profile = BuildProfile("cargo", ("cargo", "+1.82.0", "check"), ("target",), language="rust", toolchain=ToolchainSpec("rustup", "1.82.0", "rust-toolchain.toml", "cargo"))
    resolver = ToolchainResolver(tmp_path)
    monkeypatch.setattr("cydra.toolchain_contract.shutil.which", lambda name: "/usr/bin/" + name)
    calls = []
    def fake_run(argv, **kwargs):
        calls.append(argv)
        class R:
            returncode = 0
            stdout = "rustc 1.82.0 (x)"
            stderr = ""
        return R()
    monkeypatch.setattr("cydra.toolchain_contract.subprocess.run", fake_run)
    contract = resolver.resolve(profile)
    assert contract.state == ToolchainState.AVAILABLE
    assert tuple(calls[0][:2]) == ("/usr/bin/rustc", "+1.82.0")
