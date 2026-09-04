"""Dogfood the repository-recon boundary against CYDRA's own source tree.

This is intentionally passive: it reads source files, builds the same canonical
SystemModel used for security reasoning, and checks architecture invariants. It
does not execute target code or treat static patterns as vulnerabilities.
"""

from __future__ import annotations

import ast
from pathlib import Path

from cydra.graph_semantics import validate_graph
from cydra.recon import RepositoryRecon
from cydra.scope import ScopePolicy, ScopeRule, ScopeState


ROOT = Path(__file__).resolve().parents[1]
CYDRA = ROOT / "cydra"


def _source_files() -> list[Path]:
    return sorted(path for path in CYDRA.glob("*.py") if path.is_file())


def test_cydra_self_recon_projects_its_own_source_into_canonical_model():
    paths = [path.relative_to(ROOT).as_posix() for path in _source_files()]
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    policy = ScopePolicy([ScopeRule("cydra/**", ScopeState.IN_SCOPE, "CYDRA self-audit")])

    canonical = RepositoryRecon(policy.decide).scan_canonical(paths, sources)

    assert len(canonical.nodes) >= len(paths)
    assert all(node.attributes.get("source") == "repository_recon" for node in canonical.nodes.values())
    assert validate_graph(canonical) == []


def test_cydra_self_recon_finds_expected_architecture_anchors():
    paths = [path.relative_to(ROOT).as_posix() for path in _source_files()]
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    policy = ScopePolicy([ScopeRule("cydra/**", ScopeState.IN_SCOPE, "CYDRA self-audit")])
    canonical = RepositoryRecon(policy.decide).scan_canonical(paths, sources)

    functions = {
        node.label
        for node in canonical.nodes.values()
        if node.kind == "function"
    }
    assert {"execute_external_observation", "ingest_observation_result", "persist_execution_request"} <= functions
    assert "record_test_result" in functions


def test_cydra_self_audit_rejects_direct_external_result_ingestion_outside_legacy_boundary():
    violations = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "record_test_result":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert violations == [], f"direct record_test_result calls found: {violations}"


def test_cydra_self_audit_allows_process_execution_only_at_external_adapter_boundary():
    violations = []
    allowed_process_boundaries = {"foundry.py", "benchmark_materialization.py", "benchmark_run.py", "repository_workspace.py", "project_build.py", "toolchain_contract.py", "artifact_validation.py"}
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"run", "run_sync"}:
                if path.name not in allowed_process_boundaries:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.func.attr}")

    assert violations == [], f"unexpected process execution outside approved infrastructure boundary: {violations}"


def test_cydra_self_audit_detects_python_syntax_errors_before_reasoning():
    for path in _source_files():
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
