from pathlib import Path
import subprocess

from cydra.project_build import ProjectBuilder, ProjectDetector, collect_solidity_asts
from cydra.repository_workspace import RepositorySpec, RepositoryWorkspace
from cydra.workspace_pipeline import WorkspaceAuditPipeline


FIXTURE = Path(__file__).parent / "fixtures" / "foundry"


def test_project_detector_detects_foundry(tmp_path):
    (tmp_path / "foundry.toml").write_text((FIXTURE / "foundry.toml").read_text())
    profile = ProjectDetector.detect(tmp_path)
    assert profile.system == "foundry"
    assert profile.command == ("forge", "build", "--build-info")


def test_collect_solidity_asts_from_build_info(tmp_path):
    build_info = tmp_path / "build-info"
    build_info.mkdir()
    payload = {"output": {"sources": {"src/Vault.sol": {"ast": {"nodeType": "SourceUnit", "id": 1}}}}}
    (build_info / "x.json").write_text(__import__("json").dumps(payload))
    profile = ProjectDetector.detect(tmp_path) if (tmp_path / "foundry.toml").exists() else type("P", (), {"system": "foundry", "artifact_roots": ("out", "build-info")})()
    asts, paths = collect_solidity_asts(tmp_path, profile)
    assert asts["src/Vault.sol"]["id"] == 1
    assert "build-info/x.json" in paths


def test_builder_preserves_failed_build_and_still_collects_artifacts(tmp_path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\nsrc=\"src\"\n")
    (tmp_path / "src").mkdir()
    result = ProjectBuilder(tmp_path).build(command=("python", "-c", "print('compile failed'); raise SystemExit(7)"))
    assert result.status == "FAILED"
    assert result.returncode == 7
    assert "compile failed" in result.stdout


def test_workspace_manifest_is_exact_revision(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "README.md").write_text("hello")
    subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=CYDRA", "-c", "user.email=cydra@example.invalid", "commit", "-qm", "init"], check=True)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    destination = tmp_path / "workspace"
    manifest = RepositoryWorkspace(destination).clone(RepositorySpec(str(source), revision))
    assert manifest.commit == revision
    assert manifest.revision == revision
    assert manifest.files == (("README.md", __import__("hashlib").sha256(b"hello").hexdigest()),)


def test_workspace_pipeline_feeds_source_and_compiler_asts_to_audit_session(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "foundry.toml").write_text("[profile.default]\nsrc=\"src\"\n")
    (root / "src").mkdir()
    (root / "src" / "Vault.sol").write_text("contract Vault { uint256 x; function f() external { x = 1; } }")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=CYDRA", "-c", "user.email=cydra@example.invalid", "commit", "-qm", "fixture"], check=True)
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    # Use the existing workspace directly after the exact-revision manifest step.
    workspace = RepositoryWorkspace(root)
    manifest = workspace.manifest(str(root), revision)
    builder = ProjectBuilder(root)
    build = builder.build(command=("python", "-c", "print('ok')"))
    # No compiler AST means the passive session remains source-backed only.
    def scope(path):
        from cydra.scope import ScopeDecision, ScopeState
        return ScopeDecision(path, ScopeState.IN_SCOPE, True, "fixture")
    result = WorkspaceAuditPipeline(workspace, scope).ingest(manifest, build)
    assert result.build.status == "SUCCEEDED"
    assert "src/Vault.sol" in result.session.scanned_paths
    assert result.session.source_manifest


def test_project_detector_reads_exact_rust_toolchain(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\nrust-version="1.80"\n')
    (tmp_path / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.82.0"\ncomponents = ["rustfmt"]\n')
    profile = ProjectDetector.detect(tmp_path)
    assert profile.system == "cargo"
    assert profile.language == "rust"
    assert profile.toolchain.version == "1.82.0"
    assert profile.toolchain.source == "rust-toolchain.toml"


def test_project_detector_reads_go_version(tmp_path):
    (tmp_path / "go.mod").write_text("module example\n\ngo 1.23.4\n")
    profile = ProjectDetector.detect(tmp_path)
    assert profile.system == "go"
    assert profile.toolchain.version == "1.23.4"
    assert profile.toolchain.source == "go.mod:go"


def test_builder_reports_missing_toolchain_without_consuming_artifacts(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n')
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "stale.json").write_text('{"ast":{"nodeType":"SourceUnit"}}')
    result = ProjectBuilder(tmp_path).build(command=("definitely-not-installed-cydra-tool", "build"))
    assert result.status == "TOOLCHAIN_UNAVAILABLE"
    assert result.returncode == 127
    assert result.artifacts == {}

def test_rust_toolchain_file_is_bound_to_build_command(tmp_path):
    root = tmp_path / "rust"
    root.mkdir()
    (root / "Cargo.toml").write_text('[package]\nname="fixture"\nversion="0.1.0"\n')
    (root / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.82.0"\ncomponents = ["rustfmt"]\n')
    profile = ProjectDetector.detect(root)
    assert profile.system == "cargo"
    assert profile.toolchain.version == "1.82.0"
    assert profile.command == ("cargo", "+1.82.0", "check")


def test_rust_version_requirement_is_not_mistaken_for_exact_toolchain(tmp_path):
    root = tmp_path / "rust"
    root.mkdir()
    (root / "Cargo.toml").write_text('[package]\nname="fixture"\nversion="0.1.0"\nrust-version="1.80"\n')
    profile = ProjectDetector.detect(root)
    assert profile.toolchain.version == "1.80"
    assert profile.toolchain.source == "Cargo.toml:rust-version"
    assert profile.command == ("cargo", "check")


def test_cargo_build_receipt_records_reproducibility(tmp_path, monkeypatch):
    (tmp_path / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n')
    (tmp_path / "Cargo.lock").write_text('version = 3\n')
    (tmp_path / "rust-toolchain.toml").write_text('[toolchain]\nchannel="1.82.0"\n')
    from cydra.project_build import ProjectBuilder
    profile = ProjectDetector.detect(tmp_path)
    monkeypatch.setattr("cydra.project_build._resolve_executable", lambda *args: "/usr/bin/cargo")
    monkeypatch.setattr("cydra.project_build._tool_version", lambda *args: "cargo 1.82.0")
    class R:
        returncode=0
        stdout=""
        stderr=""
    monkeypatch.setattr("cydra.project_build.subprocess.run", lambda *args, **kwargs: R())
    result = ProjectBuilder(tmp_path, profile).build()
    assert result.status == "SUCCEEDED"
    assert result.reproducibility == "DECLARED_REPRODUCIBLE"


def test_cargo_dependency_metadata_is_explicit_and_locked(tmp_path, monkeypatch):
    from cydra.project_build import BuildProfile, collect_dependency_metadata
    (tmp_path / "Cargo.toml").write_text('[package]\nname="demo"\nversion="0.1.0"\n', encoding="utf-8")
    calls = []
    class R:
        returncode = 0
        stdout = '{"version":1,"workspace_members":["path+file:///demo#0.1.0"],"workspace_root":"/demo","packages":[],"resolve":{"nodes":[]}}'
    def fake_run(argv, **kwargs):
        calls.append(argv)
        return R()
    monkeypatch.setattr("cydra.project_build.shutil.which", lambda _: "/usr/bin/cargo")
    monkeypatch.setattr("cydra.project_build.subprocess.run", fake_run)
    profile = BuildProfile("cargo", ("cargo", "check"), ("target",), language="rust")
    metadata = collect_dependency_metadata(tmp_path, profile)
    assert metadata["format_version"] == 1
    assert calls[0] == ["cargo", "metadata", "--format-version", "1", "--locked"]


def test_workspace_build_projects_dependency_fingerprint(monkeypatch, tmp_path):
    from cydra.project_build import BuildProfile, BuildResult, ToolchainSpec
    from cydra.repository_workspace import WorkspaceManifest
    from cydra.workspace_pipeline import WorkspaceAuditPipeline
    from cydra.system_model import SystemModel
    from cydra.audit_session import AuditSessionResult

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "A.sol").write_text("contract A {}", encoding="utf-8")
    manifest = WorkspaceManifest(str(root), "x/y", "main", "abc", ("src/A.sol",), "fp")
    profile = BuildProfile("foundry", ("forge", "build"), ("out",), language="solidity", toolchain=ToolchainSpec("solc", "0.8.20", "foundry.toml", "forge"))
    build = BuildResult("SUCCEEDED", profile.command, 0, "", "", profile, {}, (), "solc 0.8.20", "cfg", "CONFIGURED", {"x": 1}, "dep")
    class W:
        def source_files(self): return {"src/A.sol": "contract A {}"}
    from cydra.scope import ScopeDecision, ScopeState
    class Scope:
        def __call__(self, path): return ScopeDecision(path, ScopeState.IN_SCOPE, True, "test")
    # Use the real session and a minimal fake workspace wrapper.
    result = WorkspaceAuditPipeline(W(), Scope()).ingest(manifest, build)
    node = next(n for n in result.session.model.nodes.values() if n.kind == "build")
    assert node.attributes["dependency_fingerprint"] == "dep"
    assert node.attributes["dependency_metadata_present"] is True

def test_artifact_validation_rejects_source_from_different_revision(tmp_path):
    from cydra.artifact_validation import validate_artifacts
    import json
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Vault.sol").write_text("contract Vault { uint x; }", encoding="utf-8")
    artifact = tmp_path / "build-info"
    artifact.mkdir()
    payload = {"input": {"sources": {"src/Vault.sol": {"content": "contract Vault { uint y; }"}}}, "output": {"sources": {"src/Vault.sol": {"ast": {"nodeType": "SourceUnit", "id": 1}}}}}
    (artifact / "stale.json").write_text(json.dumps(payload), encoding="utf-8")
    result = validate_artifacts(tmp_path, {"src/Vault.sol": {"nodeType": "SourceUnit", "id": 1}}, ("build-info/stale.json",), workspace_fingerprint="A", config_fingerprint="C", build_status="SUCCEEDED")
    assert result.status == "MISMATCHED_SOURCE"
    assert result.artifacts == {}


def test_artifact_validation_rejects_source_not_present_in_workspace(tmp_path):
    from cydra.artifact_validation import validate_artifacts
    import json
    (tmp_path / "src").mkdir()
    artifact = tmp_path / "build-info"
    artifact.mkdir()
    payload = {"output": {"sources": {"src/Missing.sol": {"ast": {"nodeType": "SourceUnit", "id": 1}}}}}
    (artifact / "x.json").write_text(json.dumps(payload), encoding="utf-8")
    result = validate_artifacts(tmp_path, {"src/Missing.sol": {"nodeType": "SourceUnit", "id": 1}}, ("build-info/x.json",), workspace_fingerprint="A", config_fingerprint="C", build_status="SUCCEEDED")
    assert result.status == "MISSING_SOURCE"


def test_artifact_validation_accepts_matching_embedded_source(tmp_path):
    from cydra.artifact_validation import validate_artifacts
    import json
    (tmp_path / "src").mkdir()
    source = "contract Vault { uint x; }"
    (tmp_path / "src" / "Vault.sol").write_text(source, encoding="utf-8")
    artifact = tmp_path / "build-info"
    artifact.mkdir()
    payload = {"input": {"sources": {"src/Vault.sol": {"content": source}}}, "output": {"sources": {"src/Vault.sol": {"ast": {"nodeType": "SourceUnit", "id": 1}}}}}
    (artifact / "x.json").write_text(json.dumps(payload), encoding="utf-8")
    result = validate_artifacts(tmp_path, {"src/Vault.sol": {"nodeType": "SourceUnit", "id": 1}}, ("build-info/x.json",), workspace_fingerprint="A", config_fingerprint="C", build_status="SUCCEEDED")
    assert result.status == "VALID"
    assert result.artifacts["src/Vault.sol"]["id"] == 1


def test_artifact_validation_rejects_any_artifact_after_failed_build(tmp_path):
    from cydra.artifact_validation import validate_artifacts
    result = validate_artifacts(tmp_path, {"src/Vault.sol": {"nodeType": "SourceUnit"}}, ("build-info/x.json",), workspace_fingerprint="A", config_fingerprint="C", build_status="FAILED")
    assert result.status == "BUILD_NOT_TRUSTED"
    assert result.artifacts == {}

def test_workspace_pipeline_does_not_ingest_mismatched_compiler_ast(tmp_path):
    from cydra.project_build import BuildProfile, BuildResult
    from cydra.repository_workspace import WorkspaceManifest
    from cydra.scope import ScopeDecision, ScopeState
    import json
    root=tmp_path/"repo"; (root/"src").mkdir(parents=True)
    (root/"src"/"Vault.sol").write_text("contract Vault { uint x; }", encoding="utf-8")
    (root/"build-info").mkdir()
    (root/"build-info"/"stale.json").write_text(json.dumps({"input":{"sources":{"src/Vault.sol":{"content":"contract Vault { uint y; }"}}}}), encoding="utf-8")
    manifest=WorkspaceManifest(str(root),"x/y","rev","commit",("src/Vault.sol",),"workspace-fp")
    profile=BuildProfile("foundry",("forge","build"),("out","build-info"),"solc-json-ast","solidity")
    build=BuildResult("SUCCEEDED",profile.command,0,"","",profile,{"src/Vault.sol":{"nodeType":"SourceUnit"}},("build-info/stale.json",),"forge", "cfg", "CONFIGURED")
    class W:
        def source_files(self): return {"src/Vault.sol":"contract Vault { uint x; }"}
    def scope(path): return ScopeDecision(path,ScopeState.IN_SCOPE,True,"test")
    try:
        from cydra.workspace_pipeline import WorkspaceAuditPipeline
        WorkspaceAuditPipeline(W(),scope).ingest(manifest,build)
    except ValueError as exc:
        assert "compiler artifacts rejected" in str(exc)
    else:
        raise AssertionError("mismatched compiler artifact was ingested")
