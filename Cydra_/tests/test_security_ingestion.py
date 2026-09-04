from cydra.security_ingestion import ingest_repository_security_evidence
from cydra.scope import ScopeState


class Decision:
    def __init__(self, state):
        self.state = state


def resolver(path):
    return Decision(ScopeState.IN_SCOPE)


def test_ingests_recon_and_ast_evidence_into_one_model():
    ast_payload = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Vault",
            "nodes": [{
                "nodeType": "VariableDeclaration", "id": 2, "name": "balance", "stateVariable": True, "scope": 1
            }, {
                "nodeType": "FunctionDefinition", "id": 3, "name": "deposit", "scope": 1,
                "body": {"nodeType": "Block", "statements": [{
                    "nodeType": "Assignment",
                    "leftHandSide": {"nodeType": "Identifier", "referencedDeclaration": 2, "id": 4}
                }]}
            }]
        }]
    }
    model = ingest_repository_security_evidence(
        ["Vault.sol"], {"Vault.sol": "contract Vault {}"}, resolver, {"Vault.sol": ast_payload}
    )
    assert model.validate() == []
    assert any(edge.relation == "writes" for edge in model.edges)
    assert any(node.attributes.get("ast_node_id") == 3 for node in model.nodes.values() if node.kind == "function")


def test_ignores_ast_for_paths_outside_requested_set():
    model = ingest_repository_security_evidence([], {}, resolver, {"Other.sol": {"nodeType": "SourceUnit"}})
    assert model.validate() == []
    assert model.nodes == {}


def test_never_projects_ast_evidence_for_out_of_scope_path():
    def out_of_scope_resolver(path):
        return Decision(ScopeState.OUT_OF_SCOPE)

    ast_payload = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "OutOfScopeVault",
            "nodes": [{
                "nodeType": "VariableDeclaration", "id": 2, "name": "balance", "stateVariable": True, "scope": 1
            }, {
                "nodeType": "FunctionDefinition", "id": 3, "name": "deposit", "scope": 1,
                "body": {"nodeType": "Block", "statements": [{
                    "nodeType": "Assignment",
                    "leftHandSide": {"nodeType": "Identifier", "referencedDeclaration": 2, "id": 4}
                }]}
            }]
        }]
    }
    model = ingest_repository_security_evidence(
        ["OutOfScope.sol"],
        {"OutOfScope.sol": "contract OutOfScopeVault {}"},
        out_of_scope_resolver,
        {"OutOfScope.sol": ast_payload},
    )
    assert model.validate() == []
    assert model.nodes["file:OutOfScope.sol"].attributes["scope"] == "OUT_OF_SCOPE"
    assert not any(edge.relation in {"writes", "reads", "external_call"} for edge in model.edges)
    assert not any(node.kind == "function" for node in model.nodes.values())
