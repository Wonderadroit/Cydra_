#!/usr/bin/env python3
"""Run CYDRA's oracle-free reasoning lifecycle on a materialized benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import MaterializedBenchmarkInput, validate_materialized_input
from cydra.benchmark_verifier import make_ast_replay_verifier
from cydra.blind_reasoning import run_blind_reasoning


def _load_entry(path: Path) -> BenchmarkCorpusEntry:
    data = json.loads(path.read_text(encoding="utf-8"))
    return BenchmarkCorpusEntry(
        case_id=data["case_id"],
        contest_name=data["contest_name"],
        repository=data["repository"],
        revision=data["revision"],
        input_paths=tuple(data["input_paths"]),
        excluded_paths=tuple(data.get("excluded_paths", ())),
    )


def _load_receipt(path: Path) -> MaterializedBenchmarkInput:
    data = json.loads(path.read_text(encoding="utf-8"))
    return MaterializedBenchmarkInput(
        case_id=data["case_id"],
        corpus_fingerprint=data["corpus_fingerprint"],
        repository=data["repository"],
        revision=data["revision"],
        selected_paths=tuple(data["selected_paths"]),
        file_manifest=tuple((item["path"], item["sha256"]) for item in data["file_manifest"]),
    )


def _normalize_source_identity(value: str) -> str:
    """Normalize compiler source identities without guessing contract filenames."""
    return Path(value.replace("\\", "/")).as_posix().lstrip("./")


def _ast_identity_candidates(source_name: str, ast: Mapping[str, object]) -> set[str]:
    """Return identities emitted by the compiler for one source unit."""
    identities = {_normalize_source_identity(source_name)}
    absolute_path = ast.get("absolutePath")
    if isinstance(absolute_path, str) and absolute_path.strip():
        identities.add(_normalize_source_identity(absolute_path))
    return identities


def _record_ast(found: dict[str, dict], path: str, ast: dict) -> None:
    """Record one compiler AST and reject ambiguous compiler identities."""
    existing = found.get(path)
    if existing is None:
        found[path] = ast
        return
    if existing != ast:
        raise RuntimeError(f"conflicting compiler ASTs for source identity: {path}")


def _load_solidity_asts(
    root: Path,
    selected_paths: tuple[str, ...],
    source_contents: Mapping[str, str] | None = None,
) -> dict[str, dict]:
    """Load compiler ASTs using emitted source identity, with content as identity fallback.

    Foundry artifacts are not guaranteed to expose the source identity in the same
    shape across versions/build modes. Build-info contains the compiler's canonical
    ``output.sources`` source-unit map, so it is preferred. When a source name is
    relocated or otherwise normalized by the compiler, the exact source contents in
    ``input.sources`` provide a second identity check. No contract filename guessing
    or basename matching is used.
    """
    selected = {
        _normalize_source_identity(path): path
        for path in selected_paths
        if path.lower().endswith(".sol")
    }
    if not selected:
        return {}

    contents = {
        _normalize_source_identity(path): value
        for path, value in (source_contents or {}).items()
        if path.lower().endswith(".sol")
    }
    found: dict[str, dict] = {}
    content_matches: dict[str, dict] = {}

    for artifact in sorted(root.rglob("*.json")):
        try:
            data = json.loads(artifact.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

        output = data.get("output")
        if isinstance(output, dict) and isinstance(output.get("sources"), dict):
            input_sources = data.get("input", {}).get("sources", {}) if isinstance(data.get("input"), dict) else {}
            if not isinstance(input_sources, dict):
                input_sources = {}
            for source_name, source_data in output["sources"].items():
                if not isinstance(source_name, str) or not isinstance(source_data, dict):
                    continue
                ast = source_data.get("ast")
                if not isinstance(ast, dict):
                    continue
                identities = _ast_identity_candidates(source_name, ast)
                for selected_identity, original_path in selected.items():
                    if selected_identity in identities:
                        _record_ast(found, original_path, ast)
                compiler_input = input_sources.get(source_name)
                compiler_content = compiler_input.get("content") if isinstance(compiler_input, dict) else None
                if isinstance(compiler_content, str):
                    for selected_identity, original_path in selected.items():
                        if contents.get(selected_identity) == compiler_content:
                            _record_ast(content_matches, original_path, ast)
            continue

        source_name = data.get("sourceName")
        ast = data.get("ast")
        if isinstance(source_name, str) and isinstance(ast, dict):
            identities = _ast_identity_candidates(source_name, ast)
            for selected_identity, original_path in selected.items():
                if selected_identity in identities:
                    _record_ast(found, original_path, ast)

    for selected_identity, original_path in selected.items():
        if original_path not in found:
            matched = content_matches.get(original_path)
            if matched is not None:
                found[original_path] = matched

    missing = sorted(original_path for original_path in selected.values() if original_path not in found)
    if missing:
        raise RuntimeError(f"compiler AST missing for selected Solidity path: {missing[0]}")
    return {selected_identity: found[original_path] for selected_identity, original_path in selected.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ast-root", type=Path, default=None)
    args = parser.parse_args()

    case = _load_entry(args.manifest)
    receipt = _load_receipt(args.staging / ".cydra-blind-receipt.json")
    validate_materialized_input(case, args.staging, receipt)

    source_contents = {
        path: (args.staging / path).read_text(encoding="utf-8")
        for path in receipt.selected_paths
        if path.lower().endswith(".sol")
    }
    ast_root = args.ast_root.resolve() if args.ast_root else None
    solidity_asts = (
        _load_solidity_asts(ast_root, receipt.selected_paths, source_contents=source_contents)
        if ast_root
        else {}
    )
    observation_replayer = make_ast_replay_verifier(solidity_asts) if solidity_asts else None
    result = run_blind_reasoning(
        case,
        receipt,
        args.staging,
        solidity_asts=solidity_asts,
        observation_replayer=observation_replayer,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.to_json(), encoding="utf-8")

    print(f"case_id={result.case_id}")
    print(f"materialization_fingerprint={result.materialization_fingerprint}")
    print(f"model_fingerprint={result.model_fingerprint}")
    print(f"hypotheses={len(result.hypothesis_names)}")
    print(f"observations={len(result.observation_names)}")
    print(f"selected_observation={result.selected_observation or 'NONE'}")
    print(f"rounds_used={result.rounds_used}")
    print(f"planning_steps_used={result.planning_steps_used}")
    print(f"observations_used={result.observations_used}")
    print(f"finding_candidates_considered={len(result.promotion_attempts)}")
    print(f"findings_promoted={len(result.findings)}")
    print(f"candidate_output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
