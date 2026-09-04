"""Canonical projection boundary for source observations into SystemModel."""
from __future__ import annotations

from .recon import NodeKind, RepositoryRecon
from .repository_model import RepositoryModel
from .system_model import Edge, Node, SystemModel

_KIND_MAP = {
    NodeKind.FILE: "contract",
    NodeKind.MODULE: "contract",
    NodeKind.FUNCTION: "function",
    NodeKind.CLASS: "contract",
    NodeKind.IMPORT: "data_flow",
    NodeKind.ENTRY_POINT: "function",
    NodeKind.AUTHORIZATION: "identity",
}


def project_recon_model(recon_model, system: SystemModel) -> None:
    """Project passive recon observations into an existing canonical model."""
    for node in recon_model.nodes:
        kind = _KIND_MAP[node.kind]
        attributes = dict(node.metadata)
        attributes["path"] = node.path
        attributes["scope"] = node.scope.value
        attributes["recon_kind"] = node.kind.value
        if node.node_id not in system.nodes:
            system.add_node(Node(node.node_id, kind, node.name, attributes))

    for edge in recon_model.edges:
        if edge.source in system.nodes and edge.target in system.nodes:
            system.add_edge(
                Edge(
                    edge.source,
                    edge.relation,
                    edge.target,
                    {"provenance": "passive_recon"},
                )
            )


def project_repository_model(repository: RepositoryModel, system: SystemModel) -> None:
    """Project repository structure into the same canonical model used by recon."""
    for contract in sorted(repository.contracts, key=lambda c: (c.file, c.name)):
        contract_id = f"contract:{contract.file}:{contract.name}"
        if contract_id not in system.nodes:
            system.add_node(
                Node(
                    contract_id,
                    "contract",
                    contract.name,
                    {
                        "file": contract.file,
                        "state_variables": list(contract.state_variables),
                        "source_kind": "repository_model",
                    },
                )
            )
        for state_name in sorted(contract.state_variables):
            state_id = f"state:{contract.file}:{contract.name}:{state_name}"
            if state_id not in system.nodes:
                system.add_node(
                    Node(
                        state_id,
                        "state_variable",
                        state_name,
                        {
                            "file": contract.file,
                            "contract": contract_id,
                            "source_kind": "repository_model",
                        },
                    )
                )
            system.add_edge(Edge(state_id, "defined_in", contract_id))
        for function in sorted(contract.functions, key=lambda f: (f.line or 0, f.name)):
            function_id = f"function:{function.file}:{function.line}:{contract.name}:{function.name}"
            if function_id not in system.nodes:
                system.add_node(
                    Node(
                        function_id,
                        "function",
                        function.name,
                        {
                            "file": function.file,
                            "line": function.line,
                            "visibility": function.visibility,
                            "modifiers": list(function.modifiers),
                            "external_calls": list(function.external_calls),
                            "source_kind": "repository_model",
                        },
                    )
                )
            system.add_edge(Edge(function_id, "defined_in", contract_id))


def scan_repository_into_system_model(
    paths: list[str],
    sources: dict[str, str],
    scope_resolver,
) -> SystemModel:
    """Run passive recon and project it through the canonical ingestion boundary."""
    recon_model = RepositoryRecon(scope_resolver).scan(paths, sources)
    system = SystemModel()
    project_recon_model(recon_model, system)
    return system
