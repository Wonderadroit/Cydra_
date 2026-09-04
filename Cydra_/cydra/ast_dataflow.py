from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class SemanticRelationshipEvidence:
    """A compiler-AST-backed relationship; never inferred from co-occurrence."""

    contract: str
    function: str
    relation: str
    target: str
    confidence: float
    source: str
    ast_node_id: int | None = None
    source_location: tuple[int, int, int] | None = None
    function_ast_node_id: int | None = None
    target_ast_node_id: int | None = None
    metadata: dict[str, Any] | None = None


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if isinstance(node.get("nodeType"), str):
            yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _children(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for value in node.values():
        if isinstance(value, dict) and isinstance(value.get("nodeType"), str):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("nodeType"), str):
                    yield item


def _location(node: dict[str, Any]) -> tuple[int, int, int] | None:
    src = node.get("src")
    if not isinstance(src, str):
        return None
    parts = src.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _identifiers(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for item in _walk(node):
        if item.get("nodeType") == "Identifier" and isinstance(item.get("referencedDeclaration"), int):
            yield item


def _write_ids(node: dict[str, Any]) -> set[int]:
    writes: set[int] = set()
    for item in _walk(node):
        kind = item.get("nodeType")
        if kind == "Assignment":
            lhs = item.get("leftHandSide")
            if isinstance(lhs, dict):
                writes.update(ident["referencedDeclaration"] for ident in _identifiers(lhs))
        elif kind == "UnaryOperation" and item.get("operator") in {"++", "--"}:
            operand = item.get("subExpression")
            if isinstance(operand, dict):
                writes.update(ident["referencedDeclaration"] for ident in _identifiers(operand))
    return writes


def _read_ids(node: dict[str, Any]) -> set[int]:
    """Return state declarations used as inputs, excluding write targets.

    Assignment LHS expressions and increment/decrement operands are writes, not
    reads. For ``x = x + 1`` the RHS occurrence remains a read, while the LHS
    occurrence remains a write. This preserves the data dependency needed for
    transition-derived invariant discovery without inventing reads from syntax.
    """
    reads: set[int] = set()

    def visit(current: Any, write_context: bool = False) -> None:
        if isinstance(current, dict):
            kind = current.get("nodeType")
            if kind == "Identifier" and not write_context and isinstance(current.get("referencedDeclaration"), int):
                reads.add(current["referencedDeclaration"])
                return
            if kind == "Assignment":
                lhs = current.get("leftHandSide")
                rhs = current.get("rightHandSide")
                visit(lhs, True)
                visit(rhs, False)
                return
            if kind == "UnaryOperation" and current.get("operator") in {"++", "--"}:
                visit(current.get("subExpression"), True)
                return
            for value in current.values():
                visit(value, write_context)
        elif isinstance(current, list):
            for value in current:
                visit(value, write_context)

    visit(node)
    return reads


def _transition_expressions(node: dict[str, Any], state_ids: dict[int, tuple[str, int | None]], declarations: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract compiler-linked state update expressions conservatively."""
    transitions: list[dict[str, Any]] = []
    for item in _walk(node):
        kind = item.get("nodeType")
        if kind == "Assignment":
            lhs = item.get("leftHandSide")
            rhs = item.get("rightHandSide")
            operator = item.get("operator")
            if not isinstance(lhs, dict) or not isinstance(rhs, dict) or not isinstance(operator, str):
                continue
            lhs_ids = [ident["referencedDeclaration"] for ident in _identifiers(lhs) if ident["referencedDeclaration"] in state_ids]
            if len(lhs_ids) != 1:
                continue
            rendered_lhs = _render_expression(lhs, declarations)
            rendered_rhs = _render_expression(rhs, declarations)
            if rendered_lhs is None or rendered_rhs is None:
                continue
            state_id = lhs_ids[0]
            state_name = state_ids[state_id][0]
            transitions.append({
                "state_id": state_id,
                "state_name": state_name,
                "operator": operator,
                "expression": f"{rendered_lhs} {operator} {rendered_rhs}",
                "rhs_expression": rendered_rhs,
                "dependency_ids": sorted(
                    ref for ref in _read_ids(rhs) if ref in state_ids
                ),
                "ast_node_id": item.get("id") if isinstance(item.get("id"), int) else None,
                "source_location": _location(item),
            })
        elif kind == "UnaryOperation" and item.get("operator") in {"++", "--"}:
            operand = item.get("subExpression")
            if not isinstance(operand, dict):
                continue
            ids = [ident["referencedDeclaration"] for ident in _identifiers(operand) if ident["referencedDeclaration"] in state_ids]
            if len(ids) != 1:
                continue
            rendered = _render_expression(operand, declarations)
            if rendered is None:
                continue
            state_id = ids[0]
            transitions.append({
                "state_id": state_id,
                "state_name": state_ids[state_id][0],
                "operator": item["operator"],
                "expression": f"{rendered}{item['operator']}",
                "rhs_expression": "1",
                "dependency_ids": [],
                "ast_node_id": item.get("id") if isinstance(item.get("id"), int) else None,
                "source_location": _location(item),
            })
    return transitions

def _type_identifier(node: dict[str, Any]) -> str:
    descriptions = node.get("typeDescriptions")
    if not isinstance(descriptions, dict):
        return ""
    value = descriptions.get("typeIdentifier")
    return value if isinstance(value, str) else ""


def _is_external_receiver(base: dict[str, Any], declarations: dict[int, dict[str, Any]]) -> bool:
    """Require compiler type/declaration evidence before labelling a call external.

    A MemberAccess such as ``Math.mulDiv`` is not an external call merely because it
    contains a dot. We only accept an Identifier whose compiler declaration is a local,
    parameter, or state variable and whose type is an address/contract. This keeps the
    relationship conservative while still recognizing interface/contract receivers.
    """
    if base.get("nodeType") != "Identifier":
        return False
    reference = base.get("referencedDeclaration")
    if not isinstance(reference, int):
        return False
    declaration = declarations.get(reference)
    if declaration is None or declaration.get("nodeType") not in {"VariableDeclaration", "Parameter"}:
        return False
    type_identifier = _type_identifier(base) or _type_identifier(declaration)
    return type_identifier.startswith("t_address") or type_identifier.startswith("t_contract")



def _render_expression(node: dict[str, Any], declarations: dict[int, dict[str, Any]]) -> str | None:
    """Render a conservative, compiler-linked expression for semantic obligations.

    This is intentionally not a Solidity pretty-printer. Unsupported expressions are
    omitted rather than guessed, because invariant discovery must preserve semantic
    uncertainty instead of manufacturing predicates from partial syntax.
    """
    kind = node.get("nodeType")
    if kind == "Identifier":
        name = node.get("name")
        return name if isinstance(name, str) and name.strip() else None
    if kind == "Literal":
        value = node.get("value")
        if isinstance(value, str):
            return value
        return None
    if kind == "MemberAccess":
        base = node.get("expression")
        member = node.get("memberName")
        if isinstance(base, dict) and isinstance(member, str):
            rendered = _render_expression(base, declarations)
            if rendered is not None:
                return f"{rendered}.{member}"
        return None
    if kind == "IndexAccess":
        base = node.get("baseExpression")
        index = node.get("indexExpression")
        if isinstance(base, dict) and isinstance(index, dict):
            left = _render_expression(base, declarations)
            right = _render_expression(index, declarations)
            if left is not None and right is not None:
                return f"{left}[{right}]"
        return None
    if kind == "UnaryOperation":
        operand = node.get("subExpression")
        operator = node.get("operator")
        if isinstance(operand, dict) and isinstance(operator, str):
            rendered = _render_expression(operand, declarations)
            if rendered is not None:
                return f"{operator}{rendered}"
        return None
    if kind == "BinaryOperation":
        left = node.get("leftExpression")
        right = node.get("rightExpression")
        operator = node.get("operator")
        if isinstance(left, dict) and isinstance(right, dict) and isinstance(operator, str):
            lhs = _render_expression(left, declarations)
            rhs = _render_expression(right, declarations)
            if lhs is not None and rhs is not None:
                return f"({lhs} {operator} {rhs})"
        return None
    if kind == "FunctionCall":
        expression = node.get("expression")
        arguments = node.get("arguments")
        if isinstance(expression, dict) and isinstance(arguments, list):
            callee = _render_expression(expression, declarations)
            args = [_render_expression(arg, declarations) for arg in arguments if isinstance(arg, dict)]
            if callee is not None and len(args) == len(arguments) and all(arg is not None for arg in args):
                return f"{callee}({', '.join(args)})"
        return None
    return None

def extract_ast_relationships(ast: dict[str, Any], file: str) -> list[SemanticRelationshipEvidence]:
    """Extract conservative function/state relationships from solc JSON AST.

    Compiler declaration IDs are carried separately for the function and target so a
    projection layer can preserve identity without reconstructing IDs from names or
    source locations. Missing IDs remain explicit unknowns and produce no guessed link.
    """
    state_ids: dict[int, tuple[str, int | None]] = {}
    declarations: dict[int, dict[str, Any]] = {}
    for node in _walk(ast):
        node_id = node.get("id")
        if isinstance(node_id, int):
            declarations[node_id] = node
        if node.get("nodeType") == "VariableDeclaration" and node.get("stateVariable") is True:
            name = node.get("name")
            if isinstance(name, str):
                state_ids[node_id] = (name, node_id)

    contracts = {
        node.get("id"): node.get("name", "")
        for node in _walk(ast)
        if node.get("nodeType") == "ContractDefinition" and isinstance(node.get("id"), int)
    }
    evidence: list[SemanticRelationshipEvidence] = []
    for function in _walk(ast):
        if function.get("nodeType") != "FunctionDefinition" or not isinstance(function.get("id"), int):
            continue
        function_id = function["id"]
        function_name = function.get("name") or ("constructor" if function.get("kind") == "constructor" else "fallback")
        scope = function.get("scope")
        contract_name = contracts.get(scope, str(scope) if scope is not None else "unknown")
        body = function.get("body")
        if not isinstance(body, dict):
            continue
        writes = _write_ids(body)
        reads = _read_ids(body)
        transitions = _transition_expressions(body, state_ids, declarations)
        referenced: dict[int, dict[str, Any]] = {}
        for ident in _identifiers(body):
            ref = ident["referencedDeclaration"]
            if ref in state_ids:
                referenced.setdefault(ref, ident)
        for state_id, ident in referenced.items():
            name, target_id = state_ids[state_id]
            base_kwargs = dict(
                contract=contract_name,
                function=str(function_name),
                target=name,
                confidence=0.95,
                source=f"solc-json-ast:{file}",
                ast_node_id=ident.get("id") if isinstance(ident.get("id"), int) else None,
                source_location=_location(ident),
                function_ast_node_id=function_id,
                target_ast_node_id=target_id,
            )
            # A state variable may be both read and written by one transition.
            # Preserve both facts instead of collapsing the transition into only
            # its write side; downstream invariant discovery needs the dependency.
            if state_id in writes:
                evidence.append(SemanticRelationshipEvidence(relation="writes", **base_kwargs))
            if state_id in reads:
                evidence.append(SemanticRelationshipEvidence(relation="reads", **base_kwargs))
        for transition in transitions:
            dependency_labels = [state_ids[dep][0] for dep in transition["dependency_ids"] if dep in state_ids]
            evidence.append(SemanticRelationshipEvidence(
                contract=contract_name,
                function=str(function_name),
                relation="transition_expression",
                target=transition["state_name"],
                confidence=0.98,
                source=f"solc-json-ast:{file}",
                ast_node_id=transition["ast_node_id"],
                source_location=transition["source_location"],
                function_ast_node_id=function_id,
                target_ast_node_id=transition["state_id"],
                metadata={
                    "operation": transition["operator"],
                    "expression": transition["expression"],
                    "rhs_expression": transition["rhs_expression"],
                    "dependency_ids": list(transition["dependency_ids"]),
                    "dependency_labels": dependency_labels,
                },
            ))
        for call in _walk(body):
            if call.get("nodeType") != "FunctionCall":
                continue
            expression = call.get("expression")
            if not isinstance(expression, dict):
                continue

            # A require/assert call is an executable statement of a system
            # obligation. It is not itself a vulnerability signal: the discovered
            # candidate says only that successful execution is constrained by the
            # compiler-resolved predicate. Later reasoning must establish whether
            # the obligation is security-relevant and whether it can be violated.
            callee_name = expression.get("name") if expression.get("nodeType") == "Identifier" else None
            if callee_name in {"require", "assert"}:
                arguments = call.get("arguments")
                if isinstance(arguments, list) and arguments and isinstance(arguments[0], dict):
                    predicate = _render_expression(arguments[0], declarations)
                    if predicate is not None:
                        relation = "precondition" if callee_name == "require" else "assertion"
                        evidence.append(SemanticRelationshipEvidence(
                            contract=contract_name,
                            function=str(function_name),
                            relation=relation,
                            target=predicate,
                            confidence=0.98,
                            source=f"solc-json-ast:{file}",
                            ast_node_id=call.get("id") if isinstance(call.get("id"), int) else None,
                            source_location=_location(call),
                            function_ast_node_id=function_id,
                        ))

            if expression.get("nodeType") != "MemberAccess":
                continue
            member = expression.get("memberName")
            base = expression.get("expression")
            if isinstance(member, str) and isinstance(base, dict) and _is_external_receiver(base, declarations):
                base_name = base.get("name")
                if isinstance(base_name, str):
                    evidence.append(SemanticRelationshipEvidence(
                        contract=contract_name,
                        function=str(function_name),
                        relation="external_call",
                        target=f"{base_name}.{member}",
                        confidence=0.95,
                        source=f"solc-json-ast:{file}",
                        ast_node_id=call.get("id") if isinstance(call.get("id"), int) else None,
                        source_location=_location(call),
                        function_ast_node_id=function_id,
                    ))
    return evidence
