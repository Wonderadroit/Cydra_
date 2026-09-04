"""Repository workspace -> build -> parser -> canonical model pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import hashlib
import json

from .graph_semantics import validate_graph
from .system_model import Node

from .audit_session import AuditSessionResult, RepositoryAuditSession
from .project_build import BuildResult, ProjectBuilder
from .artifact_validation import validate_artifacts
from .repository_workspace import RepositorySpec, RepositoryWorkspace, WorkspaceManifest
from .system_model import SystemModel


@dataclass(frozen=True)
class WorkspaceAuditResult:
    workspace: WorkspaceManifest
    build: BuildResult
    session: AuditSessionResult


class WorkspaceAuditPipeline:
    """Own the missing production bridge between acquisition and CYDRA reasoning."""

    def __init__(self, workspace: RepositoryWorkspace, scope_resolver: Callable[[str], object], model: SystemModel | None = None):
        self.workspace = workspace
        self.scope_resolver = scope_resolver
        self.model = model or SystemModel()

    def acquire_and_build(self, spec: RepositorySpec, *, command: tuple[str, ...] | None = None) -> tuple[WorkspaceManifest, BuildResult]:
        manifest = self.workspace.clone(spec)
        build = ProjectBuilder(manifest.root).build(command=command)
        return manifest, build

    @staticmethod
    def _fingerprint(value: object) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def ingest(self, manifest: WorkspaceManifest, build: BuildResult) -> WorkspaceAuditResult:
        sources = self.workspace.source_files()
        paths = tuple(sources)
        validated = validate_artifacts(manifest.root, build.artifacts, build.artifact_paths, workspace_fingerprint=manifest.fingerprint, config_fingerprint=build.config_fingerprint, build_status=build.status)
        if validated.status != "VALID" and build.artifacts:
            raise ValueError(f"compiler artifacts rejected: {validated.reason}")
        session = RepositoryAuditSession(self.scope_resolver).scan(
            paths,
            sources,
            solidity_asts=validated.artifacts,
            canonical=self.model,
        )
        model = session.model
        workspace_id = f"workspace:{manifest.fingerprint}"
        build_id = f"build:{self._fingerprint({"workspace": manifest.fingerprint, "command": build.command, "status": build.status, "tool_version": build.tool_version, "config": build.config_fingerprint, "artifacts": build.artifact_paths})}"
        model.add_node(Node(workspace_id, "workspace", manifest.repository, {
            "root": manifest.root,
            "repository": manifest.repository,
            "revision": manifest.revision,
            "commit": manifest.commit,
            "fingerprint": manifest.fingerprint,
            "file_count": len(manifest.files),
        }))
        model.add_node(Node(build_id, "build", build.profile.system, {
            "status": build.status,
            "command": list(build.command),
            "returncode": build.returncode,
            "language": build.profile.language,
            "requested_tool": build.profile.toolchain.tool if build.profile.toolchain else None,
            "requested_tool_version": build.profile.toolchain.version if build.profile.toolchain else None,
            "toolchain_source": build.profile.toolchain.source if build.profile.toolchain else None,
            "observed_tool_version": build.tool_version,
            "config_fingerprint": build.config_fingerprint,
            "artifact_paths": list(build.artifact_paths),
            "artifact_count": len(validated.artifacts),
            "artifact_validation_status": validated.status,
            "artifact_validation_reason": validated.reason,
            "artifact_manifest": [{"path": path, "sha256": digest} for path, digest in validated.artifact_manifest],
            "artifact_source_bindings": [{"path": path, "sha256": sha, "keccak256": keccak} for path, sha, keccak in validated.source_bindings],
            "reproducibility": build.reproducibility,
            "dependency_fingerprint": build.dependency_fingerprint,
            "dependency_metadata_present": build.dependency_metadata is not None,
            "preparation_only": True,
        }))
        model.connect(workspace_id, "contains", session.session_id, provenance="workspace_audit")
        model.connect(workspace_id, "contains", build_id, provenance="workspace_build")
        model.connect(build_id, "produced", session.session_id, provenance="build_receipt")
        errors = validate_graph(model)
        if errors:
            raise ValueError(f"workspace/build projection is invalid: {errors[0]}")
        return WorkspaceAuditResult(manifest, build, AuditSessionResult(
            model=model, session_id=session.session_id, intake_id=session.intake_id,
            scanned_paths=session.scanned_paths, solidity_paths=session.solidity_paths,
            out_of_scope_paths=session.out_of_scope_paths, scope_decisions=session.scope_decisions,
            source_manifest=session.source_manifest, solidity_artifact_manifest=session.solidity_artifact_manifest,
        ))
