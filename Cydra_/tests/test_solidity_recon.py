from cydra.ast_dataflow import extract_ast_relationships
from cydra.graph_semantics import validate_graph
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.solidity_recon import SolidityRecon
from cydra.system_model import SystemModel


AST = {
    "nodeType": "SourceUnit",
    "nodes": [{
        "nodeType": "ContractDefinition",
        "id": 1,
        "name": "Vault",
        "nodes": [
            {"nodeType": "VariableDeclaration", "id": 10, "name": "balance", "stateVariable": True, "scope": 1},
            {"nodeType": "FunctionDefinition", "id": 20, "name": "deposit", "scope": 1,
             "body": {"nodeType": "Block", "statements": [{
                 "nodeType": "Assignment", "operator": "+=",
                 "leftHandSide": {"nodeType": "Identifier", "id": 30, "name": "balance",
                                  "referencedDeclaration": 10, "src": "110:7:0"},
                 "rightHandSide": {"nodeType": "Literal", "value": "1"},
             }]}}
        ],
    }]
}


def test_solidity_recon_projects_compiler_backed_structure():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    recon = SolidityRecon(policy.decide)
    model = recon.project_ast("src/Vault.sol", AST)

    assert model.nodes["contract:Vault"].kind == "contract"
    assert model.nodes["function:Vault.deposit:20"].kind == "function"
    assert model.nodes["state_variable:Vault.balance:10"].kind == "state_variable"
    writes = [e for e in model.edges if e.relation == "writes" and e.source == "function:Vault.deposit:20"]
    assert len(writes) == 1
    assert writes[0].target == "state_variable:Vault.balance:10"
    assert writes[0].attributes["target_ast_node_id"] == 10
    assert writes[0].attributes["function_ast_node_id"] == 20
    assert writes[0].attributes["evidence_backed"] is True
    assert validate_graph(model) == []


def test_ast_evidence_preserves_distinct_compiler_identities():
    evidence = extract_ast_relationships(AST, "src/Vault.sol")
    state = next(item for item in evidence if item.relation == "writes")
    assert state.function_ast_node_id == 20
    assert state.target_ast_node_id == 10
    assert state.ast_node_id == 30
    assert state.target_ast_node_id != state.ast_node_id


def test_solidity_recon_does_not_guess_missing_declaration_identity():
    broken = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [{"nodeType": "FunctionDefinition", "id": 20, "name": "deposit", "scope": 1,
                        "body": {"nodeType": "Block", "statements": [{
                            "nodeType": "Assignment", "operator": "=",
                            "leftHandSide": {"nodeType": "Identifier", "id": 30, "name": "balance",
                                             "referencedDeclaration": 999},
                            "rightHandSide": {"nodeType": "Literal", "value": "1"},
                        }]}}]
        }]
    }
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    model = SolidityRecon(policy.decide).project_ast("src/Vault.sol", broken)
    assert not any(edge.relation == "writes" for edge in model.edges)
    assert not any(edge.relation == "reads" for edge in model.edges)
    assert validate_graph(model) == []


def test_solidity_recon_is_scope_fail_closed_for_active_projection():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.OUT_OF_SCOPE)])
    recon = SolidityRecon(policy.decide)
    model = recon.project_ast("src/Vault.sol", AST)

    assert list(model.nodes) == ["file:src/Vault.sol"]
    assert model.nodes["file:src/Vault.sol"].attributes["scope_state"] == "OUT_OF_SCOPE"
    assert validate_graph(model) == []


def test_solidity_recon_does_not_infer_findings_or_hypotheses():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    recon = SolidityRecon(policy.decide)
    model = recon.project_ast("src/Vault.sol", AST)

    assert all(node.kind not in {"hypothesis", "invariant", "finding"} for node in model.nodes.values())
    assert isinstance(model, SystemModel)
