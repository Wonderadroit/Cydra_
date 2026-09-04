"""Oracle-free AST verifier for planner-selected relationship observations.

The verifier answers a semantic relationship question from compiler-resolved AST
 evidence only. It never consumes historical findings, contest annotations, or
 vulnerability labels.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Mapping

from .ast_dataflow import SemanticRelationshipEvidence, extract_ast_relationships
from .benchmark_replay import ReplayObservationResult, ReplayVerifier
from .planner import Observation
from .updater import EvidencePolarity


_RELATIONSHIP_RE = re.compile(
    r"^verify:(?P<source>function:[^:]+(?:\.[^:]+):(?P<function_id>\d+)):(?P<relation>external_call):"
    r"data_flow:(?P<path>.+):(?P<target>[^:]+)$"
)


def _normalize(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix().lstrip("./")


def _parse_observation(name: str) -> tuple[str, int, str, str, str]:
    match = _RELATIONSHIP_RE.fullmatch(name)
    if match is None:
        raise ValueError("unsupported AST replay observation format")
    source = match.group("source")
    function_id = int(match.group("function_id"))
    relation = match.group("relation")
    path = _normalize(match.group("path"))
    target = match.group("target")
    if not path or not target:
        raise ValueError("AST replay observation contains an empty identity component")
    return source, function_id, relation, path, target


def _matching_evidence(
    observation: Observation,
    ast: Mapping[str, dict],
) -> tuple[SemanticRelationshipEvidence, ...]:
    source, function_id, relation, path, target = _parse_observation(observation.name)
    function_label = source.removeprefix("function:").rsplit(":", 1)[0]
    contract, _, function_name = function_label.partition(".")
    expected_target = target.removeprefix(f"{contract}.")

    selected_ast = ast.get(path)
    if not isinstance(selected_ast, dict):
        raise ValueError(f"compiler AST missing for selected replay source: {path}")

    matches = []
    for evidence in extract_ast_relationships(selected_ast, path):
        if (
            evidence.function_ast_node_id == function_id
            and evidence.contract == contract
            and evidence.function == function_name
            and evidence.relation == relation
            and evidence.target == expected_target
        ):
            matches.append(evidence)
    return tuple(matches)


def verify_ast_relationship_observation(
    observation: Observation,
    root: Path,
    solidity_asts: Mapping[str, dict],
) -> ReplayObservationResult:
    """Verify one selected external-call relationship against compiler AST evidence."""
    if not isinstance(observation, Observation):
        raise TypeError("AST replay verifier requires an Observation")
    if not isinstance(root, Path):
        root = Path(root)
    if not root.is_dir():
        raise ValueError("AST replay verifier requires a materialized benchmark root")

    source, function_id, relation, path, target = _parse_observation(observation.name)
    source_identity = _normalize(path)
    source_file = root / source_identity
    if not source_file.is_file():
        raise ValueError(f"selected replay source is not materialized: {source_identity}")

    matches = _matching_evidence(observation, solidity_asts)
    hypothesis_name = f"relationship:{observation.name.removeprefix('verify:')}"
    details = {
        "verifier": "solc-ast-relationship",
        "source": source_identity,
        "function": source,
        "function_ast_node_id": function_id,
        "relation": relation,
        "target": target,
        "matches": len(matches),
        "provenance": [item.source for item in matches],
        "ast_node_ids": [item.ast_node_id for item in matches],
        "source_locations": [list(item.source_location) for item in matches if item.source_location is not None],
    }
    if matches:
        return ReplayObservationResult(
            "CONFIRMED",
            {hypothesis_name: EvidencePolarity.SUPPORTS},
            details,
        )
    return ReplayObservationResult(
        "REFUTED",
        {hypothesis_name: EvidencePolarity.CONTRADICTS},
        details,
    )


def make_ast_replay_verifier(solidity_asts: Mapping[str, dict]) -> ReplayVerifier:
    """Create a verifier closure bound only to compiler ASTs loaded for this run."""
    if not isinstance(solidity_asts, Mapping):
        raise TypeError("solidity_asts must be a mapping")
    frozen = dict(solidity_asts)

    def verifier(observation: Observation, root: Path) -> ReplayObservationResult:
        return verify_ast_relationship_observation(observation, root, frozen)

    return verifier
