from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .repository_model import RepositoryModel
from .system_model import SystemModel
from .system_model_ingestion import project_repository_model


@dataclass(frozen=True)
class RepositoryGraphRecord:
    """Normalized source observation ready for insertion into the persistent graph."""

    node_type: str
    node_id: str
    attributes: dict[str, Any]


def build_repository_graph_records(model: RepositoryModel) -> list[RepositoryGraphRecord]:
    records: list[RepositoryGraphRecord] = []
    for contract in sorted(model.contracts, key=lambda c: (c.file, c.name)):
        contract_id = f"contract:{contract.file}:{contract.name}"
        records.append(RepositoryGraphRecord("contract", contract_id, {
            "name": contract.name, "file": contract.file,
            "state_variables": list(contract.state_variables),
        }))
        for state_name in sorted(contract.state_variables):
            state_id = f"state:{contract.file}:{contract.name}:{state_name}"
            records.append(RepositoryGraphRecord("state_variable", state_id, {
                "name": state_name, "contract": contract_id, "file": contract.file,
            }))
        for function in sorted(contract.functions, key=lambda f: (f.line or 0, f.name)):
            function_id = f"function:{function.file}:{function.line}:{contract.name}:{function.name}"
            records.append(RepositoryGraphRecord("function", function_id, {
                "name": function.name, "contract": contract_id, "file": function.file,
                "line": function.line, "visibility": function.visibility,
                "modifiers": list(function.modifiers),
                "external_calls": list(function.external_calls),
            }))
    return records


def project_repository_into_system_model(model: RepositoryModel, system: SystemModel) -> None:
    """Insert repository structure through the canonical SystemModel ingestion boundary."""
    project_repository_model(model, system)
