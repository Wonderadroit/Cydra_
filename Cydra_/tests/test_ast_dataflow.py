from cydra.ast_dataflow import extract_ast_relationships


def _ast():
    return {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [
                {"nodeType": "VariableDeclaration", "id": 10, "name": "balance", "stateVariable": True, "scope": 1},
                {"nodeType": "FunctionDefinition", "id": 20, "name": "deposit", "scope": 1,
                 "body": {"nodeType": "Block", "src": "100:20:0", "statements": [{
                     "nodeType": "Assignment", "operator": "+=",
                     "leftHandSide": {"nodeType": "Identifier", "id": 30, "name": "balance",
                                      "referencedDeclaration": 10, "src": "110:7:0"},
                     "rightHandSide": {"nodeType": "Literal", "value": "1"},
                 }]}}
            ],
        }]
    }


def test_ast_dataflow_uses_compiler_declaration_identity():
    relationships = extract_ast_relationships(_ast(), "Vault.sol")
    state = [r for r in relationships if r.target == "balance" and r.relation == "writes"]
    assert len(state) == 1
    assert state[0].relation == "writes"
    assert state[0].confidence == 0.95
    assert state[0].source == "solc-json-ast:Vault.sol"
    assert state[0].ast_node_id == 30
    assert state[0].source_location == (110, 7, 0)
    assert state[0].function_ast_node_id == 20
    assert state[0].target_ast_node_id == 10


def test_ast_dataflow_does_not_infer_state_from_contract_cooccurrence():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [
                {"nodeType": "VariableDeclaration", "id": 10, "name": "balance", "stateVariable": True, "scope": 1},
                {"nodeType": "FunctionDefinition", "id": 20, "name": "ping", "scope": 1,
                 "body": {"nodeType": "Block", "statements": [{"nodeType": "Literal", "value": "1"}]}}
            ],
        }]
    }
    assert extract_ast_relationships(ast, "Vault.sol") == []


def test_ast_dataflow_requires_typed_receiver_for_external_call():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [
                {"nodeType": "VariableDeclaration", "id": 10, "name": "token", "stateVariable": True, "scope": 1,
                 "typeDescriptions": {"typeIdentifier": "t_contract$_IERC20_$1"}},
                {"nodeType": "FunctionDefinition", "id": 20, "name": "deposit", "scope": 1,
                 "body": {"nodeType": "Block", "statements": [{
                     "nodeType": "FunctionCall", "id": 40, "src": "120:15:0",
                     "expression": {"nodeType": "MemberAccess", "memberName": "transfer", "expression": {
                         "nodeType": "Identifier", "id": 41, "name": "token", "referencedDeclaration": 10,
                         "typeDescriptions": {"typeIdentifier": "t_contract$_IERC20_$1"}
                     }}
                 }]}}
            ],
        }]
    }
    relationships = extract_ast_relationships(ast, "Vault.sol")
    calls = [r for r in relationships if r.relation == "external_call"]
    assert len(calls) == 1
    assert calls[0].target == "token.transfer"
    assert calls[0].function_ast_node_id == 20


def test_ast_dataflow_rejects_member_access_on_library_or_unresolved_receiver():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [
                {"nodeType": "ContractDefinition", "id": 2, "name": "Math"},
                {"nodeType": "FunctionDefinition", "id": 20, "name": "ping", "scope": 1,
                 "body": {"nodeType": "Block", "statements": [{
                     "nodeType": "FunctionCall", "id": 40, "src": "120:15:0",
                     "expression": {"nodeType": "MemberAccess", "memberName": "mulDiv", "expression": {
                         "nodeType": "Identifier", "id": 41, "name": "Math", "referencedDeclaration": 2,
                         "typeDescriptions": {"typeIdentifier": "t_contract$_Math_$2"}
                     }}
                 }]}}
            ],
        }]
    }
    assert [r for r in extract_ast_relationships(ast, "Vault.sol") if r.relation == "external_call"] == []


def test_ast_dataflow_extracts_compiler_backed_preconditions():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [{
                "nodeType": "FunctionDefinition", "id": 20, "name": "withdraw", "scope": 1,
                "body": {"nodeType": "Block", "statements": [{
                    "nodeType": "FunctionCall", "id": 40, "src": "120:24:0",
                    "expression": {"nodeType": "Identifier", "name": "require"},
                    "arguments": [{
                        "nodeType": "BinaryOperation", "operator": ">",
                        "leftExpression": {"nodeType": "Identifier", "name": "amount", "referencedDeclaration": 30},
                        "rightExpression": {"nodeType": "Literal", "value": "0"},
                    }],
                }]},
            }],
        }]
    }
    relationships = extract_ast_relationships(ast, "Vault.sol")
    preconditions = [r for r in relationships if r.relation == "precondition"]
    assert len(preconditions) == 1
    assert preconditions[0].target == "(amount > 0)"
    assert preconditions[0].confidence == 0.98
    assert preconditions[0].function_ast_node_id == 20
    assert preconditions[0].ast_node_id == 40


def test_ast_dataflow_preserves_read_and_write_when_one_state_variable_is_both():
    ast = {
        "nodeType": "SourceUnit", "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault", "nodes": [{
                "nodeType": "VariableDeclaration", "id": 2, "name": "balance", "stateVariable": True,
            }, {
                "nodeType": "FunctionDefinition", "id": 3, "name": "update", "scope": 1,
                "body": {"nodeType": "Block", "statements": [{
                    "nodeType": "ExpressionStatement", "expression": {
                        "nodeType": "Assignment", "id": 4,
                        "leftHandSide": {"nodeType": "Identifier", "id": 5, "name": "balance", "referencedDeclaration": 2},
                        "rightHandSide": {"nodeType": "BinaryOperation", "operator": "+",
                            "leftExpression": {"nodeType": "Identifier", "id": 6, "name": "balance", "referencedDeclaration": 2},
                            "rightExpression": {"nodeType": "Literal", "id": 7, "value": "1"}},
                    }
                }]}
            }]
        }]
    }
    relationships = extract_ast_relationships(ast, "Vault.sol")
    relations = [item.relation for item in relationships if item.target == "balance"]
    assert "reads" in relations
    assert "writes" in relations


def test_ast_dataflow_extracts_compiler_backed_transition_expression():
    ast = {
        "nodeType": "SourceUnit", "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault", "nodes": [
                {"nodeType": "VariableDeclaration", "id": 10, "name": "totalShares", "stateVariable": True, "scope": 1},
                {"nodeType": "VariableDeclaration", "id": 11, "name": "totalAssets", "stateVariable": True, "scope": 1},
                {"nodeType": "FunctionDefinition", "id": 20, "name": "deposit", "scope": 1,
                 "body": {"nodeType": "Block", "statements": [{
                     "nodeType": "Assignment", "id": 30, "src": "100:30:0", "operator": "=",
                     "leftHandSide": {"nodeType": "Identifier", "name": "totalShares", "referencedDeclaration": 10},
                     "rightHandSide": {"nodeType": "BinaryOperation", "operator": "+",
                         "leftExpression": {"nodeType": "Identifier", "name": "totalShares", "referencedDeclaration": 10},
                         "rightExpression": {"nodeType": "Identifier", "name": "totalAssets", "referencedDeclaration": 11}},
                 }]}}
            ]
        }]
    }
    relationships = extract_ast_relationships(ast, "Vault.sol")
    transitions = [r for r in relationships if r.relation == "transition_expression"]
    assert len(transitions) == 1
    assert transitions[0].target == "totalShares"
    assert transitions[0].target_ast_node_id == 10
    assert transitions[0].ast_node_id == 30
    assert transitions[0].metadata == {
        "operation": "=",
        "expression": "totalShares = (totalShares + totalAssets)",
        "rhs_expression": "(totalShares + totalAssets)",
        "dependency_ids": [10, 11],
        "dependency_labels": ["totalShares", "totalAssets"],
    }

def test_ast_dataflow_omits_unsupported_transition_expression():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [
                {"nodeType": "VariableDeclaration", "id": 10, "name": "balance", "stateVariable": True},
                {
                    "nodeType": "FunctionDefinition", "id": 20, "name": "update", "scope": 1,
                    "body": {
                        "nodeType": "Block",
                        "statements": [{
                            "nodeType": "Assignment", "id": 30, "operator": "=",
                            "leftHandSide": {"nodeType": "Identifier", "name": "balance", "referencedDeclaration": 10},
                            "rightHandSide": {"nodeType": "TupleExpression", "components": []},
                        }]
                    }
                },
            ]
        }]
    }
    assert [r for r in extract_ast_relationships(ast, "Vault.sol") if r.relation == "transition_expression"] == []
