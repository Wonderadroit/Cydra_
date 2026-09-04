"""Canonical repository-audit orchestration boundary for CYDRA."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable, Mapping
import uuid

from .graph_semantics import validate_graph
from .recon import RepositoryRecon
from .scope import ScopeState
from .solidity_recon import SolidityRecon
from .system_model import Node, SystemModel


@dataclass(frozen=True)
class AuditSessionResult:
    """Result of one deterministic passive repository-modeling pass."""

    model: SystemModel
    session_id: str
    intake_id: str
    scanned_paths: tuple[str, ...]
    solidity_paths: tuple[str, ...]
    out_of_scope_paths: tuple[str, ...]
    scope_decisions: tuple[tuple[str, str], ...]
    source_manifest: tuple[tuple[str, str], ...]
    solidity_artifact_manifest: tuple[tuple[str, str], ...]


class RepositoryAuditSession:
    """Compose repository and Solidity recon into one atomic canonical boundary.

    The caller supplies repository observations (source text and, where available,
    compiler JSON AST artifacts). This class does not read the filesystem, invoke
    solc, execute code, or infer hypotheses/invariants/findings.

    Projection is staged on a deep copy of the supplied canonical model. The caller's
    graph is changed only after the complete passive intake has validated successfully.
    """

    def __init__(self, scope_resolver: Callable[[str], object]):
        self.scope_resolver = scope_resolver
        self.repository_recon = RepositoryRecon(scope_resolver)
        self.solidity_recon = SolidityRecon(scope_resolver)
        self.session_id = f"audit-session:{uuid.uuid4()}"

    @staticmethod
    def _digest(value: object) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return sha256(payload).hexdigest()

    @classmethod
    def _intake_fingerprint(
        cls,
        paths: Iterable[str],
        source_manifest: Iterable[tuple[str, str]],
        solidity_artifact_manifest: Iterable[tuple[str, str]],
        scope_decisions: Iterable[tuple[str, str]],
    ) -> str:
        payload = {
            "paths": tuple(paths),
            "sources": tuple(source_manifest),
            "solidity_asts": tuple(solidity_artifact_manifest),
            "scope": tuple(scope_decisions),
        }
        return f"intake:{cls._digest(payload)}"

    @classmethod
    def validate_persisted_provenance(cls, model: SystemModel, session_id: str) -> list[str]:
        """Verify that persisted audit-session provenance is internally consistent."""
        errors: list[str] = []
        node = model.nodes.get(session_id)
        if node is None:
            return [f"audit session missing: {session_id}"]
        if node.kind != "audit_session":
            return [f"node is not an audit session: {session_id}"]

        attributes = node.attributes
        paths = tuple(attributes.get("scanned_paths", ()))
        solidity_paths = tuple(attributes.get("solidity_paths", ()))
        out_of_scope_paths = tuple(attributes.get("out_of_scope_paths", ()))
        raw_scope = attributes.get("scope_decisions", ())
        raw_sources = attributes.get("source_manifest", ())
        raw_asts = attributes.get("solidity_artifact_manifest", ())

        def pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
            if not isinstance(value, (list, tuple)):
                errors.append(f"{label} must be a sequence")
                return ()
            result: list[tuple[str, str]] = []
            for item in value:
                if isinstance(item, dict):
                    expected_key = "state" if label == "scope_decisions" else "sha256"
                    if set(item) == {"path", expected_key}:
                        result.append((str(item["path"]), str(item[expected_key])))
                        continue
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    errors.append(f"invalid {label} entry")
                    continue
                result.append((str(item[0]), str(item[1])))
            return tuple(result)

        scope_decisions = pairs(raw_scope, "scope_decisions")
        source_manifest = pairs(raw_sources, "source_manifest")
        artifact_manifest = pairs(raw_asts, "solidity_artifact_manifest")

        if len(set(paths)) != len(paths):
            errors.append("scanned_paths contains duplicates")
        if set(solidity_paths) - set(paths):
            errors.append("solidity_paths contains an unscanned path")
        if set(out_of_scope_paths) - set(paths):
            errors.append("out_of_scope_paths contains an unscanned path")
        if tuple(path for path, _ in scope_decisions) != paths:
            errors.append("scope_decisions do not match scanned_paths")
        if tuple(path for path, _ in source_manifest) != paths:
            errors.append("source_manifest does not match scanned_paths")
        if tuple(path for path, _ in artifact_manifest) != solidity_paths:
            errors.append("solidity_artifact_manifest does not match solidity_paths")

        for label, manifest in (("source_manifest", source_manifest), ("solidity_artifact_manifest", artifact_manifest)):
            for path, digest in manifest:
                if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
                    errors.append(f"{label} has invalid SHA-256 for {path}")

        expected = cls._intake_fingerprint(paths, source_manifest, artifact_manifest, scope_decisions)
        if attributes.get("intake_id") != expected:
            errors.append("intake_id does not match persisted provenance")

        if attributes.get("passive") is not True:
            errors.append("audit session must remain marked passive")

        for path in paths:
            file_id = f"file:{path}"
            file_node = model.nodes.get(file_id)
            if file_node is None:
                errors.append(f"scanned path missing canonical file node: {file_id}")
            elif file_node.kind != "file":
                errors.append(f"scanned path does not resolve to a file node: {file_id}")

        return errors

    def scan(
        self,
        paths: Iterable[str],
        sources: Mapping[str, str],
        solidity_asts: Mapping[str, dict[str, Any]] | None = None,
        canonical: SystemModel | None = None,
    ) -> AuditSessionResult:
        """Build and atomically commit one provenance-complete passive intake."""
        ordered_paths = tuple(dict.fromkeys(PurePosixPath(path).as_posix() for path in paths))
        normalized_sources = {PurePosixPath(path).as_posix(): source for path, source in sources.items()}
        missing = [path for path in ordered_paths if path not in normalized_sources]
        if missing:
            raise KeyError(f"source missing for repository path: {missing[0]}")

        target = canonical or SystemModel()
        model = deepcopy(target)
        model = self.repository_recon.scan_canonical(ordered_paths, normalized_sources, model)
        normalized_asts = {
            PurePosixPath(path).as_posix(): ast for path, ast in (solidity_asts or {}).items()
        }
        solidity_paths: list[str] = []
        out_of_scope: list[str] = []
        scope_decisions: list[tuple[str, str]] = []

        for path in ordered_paths:
            decision = self.scope_resolver(path)
            state = decision.state
            scope_decisions.append((path, state.value))
            if state is ScopeState.OUT_OF_SCOPE:
                out_of_scope.append(path)
            if not path.lower().endswith(".sol") or path not in normalized_asts:
                continue
            solidity_paths.append(path)
            self.solidity_recon.project_ast(path, normalized_asts[path], model)

        source_manifest = tuple((path, self._digest(normalized_sources[path])) for path in ordered_paths)
        solidity_artifact_manifest = tuple(
            (path, self._digest(normalized_asts[path])) for path in solidity_paths
        )
        intake_id = self._intake_fingerprint(
            ordered_paths, source_manifest, solidity_artifact_manifest, scope_decisions
        )

        session_node = Node(self.session_id, "audit_session", self.session_id, {
            "intake_id": intake_id,
            "scanned_paths": list(ordered_paths),
            "solidity_paths": list(solidity_paths),
            "out_of_scope_paths": list(out_of_scope),
            "scope_decisions": [{"path": path, "state": state} for path, state in scope_decisions],
            "source_manifest": [{"path": path, "sha256": digest} for path, digest in source_manifest],
            "solidity_artifact_manifest": [{"path": path, "sha256": digest} for path, digest in solidity_artifact_manifest],
            "passive": True,
        })
        if self.session_id in model.nodes:
            raise ValueError(f"audit session already exists: {self.session_id}")
        model.add_node(session_node)
        for path in ordered_paths:
            file_id = f"file:{path}"
            if file_id in model.nodes:
                model.connect(self.session_id, "contains", file_id, provenance="audit_session_intake")

        errors = validate_graph(model)
        if errors:
            raise ValueError(f"audit-session projection is invalid: {errors[0]}")
        provenance_errors = self.validate_persisted_provenance(model, self.session_id)
        if provenance_errors:
            raise ValueError(f"audit-session provenance is invalid: {provenance_errors[0]}")

        if canonical is not None:
            canonical.nodes = model.nodes
            canonical.edges = model.edges
            model = canonical

        return AuditSessionResult(
            model=model,
            session_id=self.session_id,
            intake_id=intake_id,
            scanned_paths=ordered_paths,
            solidity_paths=tuple(solidity_paths),
            out_of_scope_paths=tuple(out_of_scope),
            scope_decisions=tuple(scope_decisions),
            source_manifest=source_manifest,
            solidity_artifact_manifest=solidity_artifact_manifest,
        )
