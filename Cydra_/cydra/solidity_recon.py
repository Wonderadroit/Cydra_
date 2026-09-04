"""Conservative Solidity reconnaissance from compiler-resolved AST artifacts."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable, Iterator

from .ast_dataflow import extract_ast_relationships
from .scope import ScopeState
from .system_model import Node, SystemModel


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if isinstance(node.get("nodeType"), str):
            yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


class SolidityRecon:
    """Project compiler-resolved Solidity structure into the canonical model.

    The adapter consumes an existing solc JSON AST. It never invokes a compiler,
    executes contracts, infers vulnerabilities, or creates hypotheses/findings.
    Compiler declaration IDs are preserved as identity anchors; names and source
    locations are descriptive metadata, not substitutes for declaration identity.
    """

    def __init__(self, scope_resolver: Callable[[str], object]):
        self.scope_resolver = scope_resolver

    def _scope(self, path: str) -> ScopeState:
        decision = self.scope_resolver(path)
        state = getattr(decision, "state", None)
        if not isinstance(state, ScopeState):
            raise ValueError("scope resolver must return a decision with a ScopeState")
        return state

    def project_ast(
        self,
        file: str,
        ast: dict[str, Any],
        canonical: SystemModel | None = None,
    ) -> SystemModel:
        if not isinstance(ast, dict):
            raise TypeError("Solidity AST must be a dictionary")

        path = PurePosixPath(file).as_posix()
        scope = self._scope(path)
        canonical = canonical or SystemModel()
        file_id = f"file:{path}"

        if file_id not in canonical.nodes:
            canonical.add_node(Node(file_id, "file", PurePosixPath(path).name, {
                "source": "solidity_recon",
                "path": path,
                "scope_state": scope.value,
                "artifact": "solc-json-ast",
            }))

        if scope is not ScopeState.IN_SCOPE:
            return canonical

        contracts: dict[int, str] = {}
        functions: dict[int, str] = {}
        states: dict[int, str] = {}

        for node in _walk(ast):
            if node.get("nodeType") != "ContractDefinition":
                continue
            node_id = node.get("id")
            name = node.get("name")
            if not isinstance(node_id, int) or not isinstance(name, str) or not name.strip():
                continue
            contract_id = f"contract:{name}"
            contracts[node_id] = contract_id
            if contract_id not in canonical.nodes:
                canonical.add_node(Node(contract_id, "contract", name, {
                    "source": "solidity_recon",
                    "path": path,
                    "ast_node_id": node_id,
                    "scope_state": scope.value,
                }))

        for node in _walk(ast):
            node_id = node.get("id")
            scope_id = node.get("scope")
            contract_id = contracts.get(scope_id)
            if contract_id is None or not isinstance(node_id, int):
                continue

            if node.get("nodeType") == "FunctionDefinition":
                name = node.get("name") or ("constructor" if node.get("kind") == "constructor" else "fallback")
                function_id = f"function:{contract_id.removeprefix('contract:')}.{name}:{node_id}"
                functions[node_id] = function_id
                if function_id not in canonical.nodes:
                    canonical.add_node(Node(function_id, "function", str(name), {
                        "source": "solidity_recon",
                        "path": path,
                        "ast_node_id": node_id,
                        "contract_id": contract_id,
                        "scope_state": scope.value,
                    }))
                canonical.connect(function_id, "defined_in", contract_id, provenance="solc-json-ast")
            elif node.get("nodeType") == "VariableDeclaration" and node.get("stateVariable") is True:
                name = node.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                state_id = f"state_variable:{contract_id.removeprefix('contract:')}.{name}:{node_id}"
                states[node_id] = state_id
                if state_id not in canonical.nodes:
                    canonical.add_node(Node(state_id, "state_variable", name, {
                        "source": "solidity_recon",
                        "path": path,
                        "ast_node_id": node_id,
                        "contract_id": contract_id,
                        "scope_state": scope.value,
                    }))
                canonical.connect(state_id, "defined_in", contract_id, provenance="solc-json-ast")

        for evidence in extract_ast_relationships(ast, path):
            function_id = functions.get(evidence.function_ast_node_id)
            if function_id is None:
                continue

            if evidence.relation in {"reads", "writes", "transition_expression"}:
                target_id = states.get(evidence.target_ast_node_id)
                if target_id is None:
                    # Do not reconstruct a declaration identity from its name or
                    # identifier/source-location metadata.
                    continue
                target_kind = "state_variable"
            else:
                target_kind = "data_flow"
                target_id = f"data_flow:{path}:{evidence.contract}.{evidence.target}"
                if target_id not in canonical.nodes:
                    canonical.add_node(Node(target_id, target_kind, evidence.target, {
                        "source": evidence.source,
                        "path": path,
                        "ast_node_id": evidence.ast_node_id,
                        "source_location": list(evidence.source_location) if evidence.source_location is not None else None,
                        "evidence_backed": True,
                        "candidate": True,
                    }))

            canonical.connect(
                function_id,
                evidence.relation,
                target_id,
                confidence=evidence.confidence,
                provenance=evidence.source,
                ast_node_id=evidence.ast_node_id,
                function_ast_node_id=evidence.function_ast_node_id,
                target_ast_node_id=evidence.target_ast_node_id,
                source_location=list(evidence.source_location) if evidence.source_location is not None else None,
                evidence_backed=True,
                candidate=True,
                **(evidence.metadata or {}),
            )
        return canonical
