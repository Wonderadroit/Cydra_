"""Join passive recon and compiler-resolved AST evidence in one canonical model."""
from __future__ import annotations
from pathlib import PurePosixPath
from typing import Any

from .ast_dataflow import extract_ast_relationships
from .recon_bridge import scan_into_system_model
from .scope import ScopeState
from .system_model import SystemModel


def ingest_repository_security_evidence(
    paths: list[str],
    sources: dict[str, str],
    scope_resolver,
    compiler_asts: dict[str, dict[str, Any]] | None = None,
) -> SystemModel:
    """Build the canonical model from scoped recon, then add scoped AST evidence.

    Recon remains passive and scope-aware. Compiler-produced AST relationships are
    evidence only for paths that are explicitly in scope. This second scope check is
    deliberate: AST artifacts must not reintroduce structure from paths that passive
    recon correctly excluded.
    """
    normalized_paths = {PurePosixPath(path).as_posix() for path in paths}
    model = scan_into_system_model(paths, sources, scope_resolver)
    for raw_path, ast_payload in (compiler_asts or {}).items():
        path = PurePosixPath(raw_path).as_posix()
        if path not in normalized_paths:
            continue
        decision = scope_resolver(path)
        if decision.state is not ScopeState.IN_SCOPE:
            continue
        relationships = extract_ast_relationships(ast_payload, path)
        model.project_ast_evidence(relationships)
    errors = model.validate()
    if errors:
        raise ValueError("invalid security model: " + "; ".join(errors))
    return model
