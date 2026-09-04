from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .ast_dataflow import SemanticRelationshipEvidence
from .repository_model import RepositoryModel, SourceContract, SourceFunction


@dataclass(frozen=True)
class SemanticFunction:
    contract: str
    name: str
    visibility: str | None
    modifiers: tuple[str, ...]
    external_calls: tuple[str, ...]
    state_candidates: tuple[str, ...] = ()
    ast_evidence: tuple[SemanticRelationshipEvidence, ...] = ()


@dataclass(frozen=True)
class SemanticContract:
    name: str
    file: str
    state_variables: tuple[str, ...]
    functions: tuple[SemanticFunction, ...]


@dataclass
class SemanticRepositoryModel:
    contracts: list[SemanticContract] = field(default_factory=list)
    ast_evidence: tuple[SemanticRelationshipEvidence, ...] = ()


def _evidence_by_function(
    evidence: Iterable[SemanticRelationshipEvidence],
) -> dict[tuple[str, str], tuple[SemanticRelationshipEvidence, ...]]:
    grouped: dict[tuple[str, str], list[SemanticRelationshipEvidence]] = {}
    for item in evidence:
        grouped.setdefault((item.contract, item.function), []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def derive_semantic_model(
    repository: RepositoryModel,
    ast_evidence: Iterable[SemanticRelationshipEvidence] = (),
) -> SemanticRepositoryModel:
    """Derive a conservative semantic model and preserve AST-backed evidence.

    Structural parsing remains conservative. Security-relevant state relationships are
    populated only from explicit compiler/AST evidence supplied by the caller; this
    function never infers reads or writes from contract-level co-occurrence.
    """
    evidence = tuple(ast_evidence)
    grouped = _evidence_by_function(evidence)
    contracts: list[SemanticContract] = []
    for contract in sorted(repository.contracts, key=lambda c: (c.file, c.name)):
        functions = []
        for function in sorted(contract.functions, key=lambda f: (f.line or 0, f.name)):
            function_evidence = grouped.get((contract.name, function.name), ())
            state_targets = tuple(sorted({
                item.target
                for item in function_evidence
                if item.relation in {"reads", "writes"}
            }))
            functions.append(
                SemanticFunction(
                    contract=contract.name,
                    name=function.name,
                    visibility=function.visibility,
                    modifiers=function.modifiers,
                    external_calls=function.external_calls,
                    state_candidates=state_targets,
                    ast_evidence=function_evidence,
                )
            )
        contracts.append(
            SemanticContract(
                name=contract.name,
                file=contract.file,
                state_variables=contract.state_variables,
                functions=tuple(functions),
            )
        )
    return SemanticRepositoryModel(contracts, evidence)
