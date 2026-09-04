from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.system_model import SystemModel


def test_compiler_ast_function_identity_keeps_overloads_distinct():
    model = SystemModel()
    first = SemanticRelationshipEvidence(contract="Vault", function="deposit", relation="writes", target="balance", confidence=0.95, source="solc-json-ast:Vault.sol", ast_node_id=40, function_ast_node_id=10, target_ast_node_id=20)
    second = SemanticRelationshipEvidence(contract="Vault", function="deposit", relation="writes", target="balance", confidence=0.95, source="solc-json-ast:Vault.sol", ast_node_id=41, function_ast_node_id=11, target_ast_node_id=20)
    model.add_ast_evidence(first)
    model.add_ast_evidence(second)
    function_nodes = [node for node in model.nodes.values() if node.kind == "function"]
    assert {node.attributes["ast_node_id"] for node in function_nodes} == {10, 11}
    assert len([edge for edge in model.edges if edge.relation == "writes"]) == 2
    assert model.validate() == []


def test_compiler_ast_missing_function_identity_does_not_guess_identity():
    model = SystemModel()
    evidence = SemanticRelationshipEvidence(contract="Vault", function="deposit", relation="writes", target="balance", confidence=0.95, source="solc-json-ast:Vault.sol", ast_node_id=40, target_ast_node_id=20)
    model.add_ast_evidence(evidence)
    function_nodes = [node for node in model.nodes.values() if node.kind == "function"]
    assert len(function_nodes) == 1
    assert function_nodes[0].attributes.get("identity_status") == "unknown"
    assert model.validate() == []
