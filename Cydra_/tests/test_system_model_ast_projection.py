from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.system_model import SystemModel


def test_ast_evidence_projects_as_candidate_with_provenance():
    evidence = SemanticRelationshipEvidence(
        contract="Vault", function="deposit", relation="writes", target="balance",
        confidence=0.95, source="solc-json-ast:Vault.sol", ast_node_id=30,
        source_location=(110, 7, 0),
    )
    model = SystemModel()
    edges = model.project_ast_evidence([evidence])
    assert model.SCHEMA_VERSION == "1.22.0"
    assert model.validate() == []
    assert len(edges) == 1
    edge = edges[0]
    assert edge.relation == "writes"
    assert edge.attributes["confidence"] == 0.95
    assert edge.attributes["provenance"] == "solc-json-ast:Vault.sol"
    assert edge.attributes["ast_node_id"] == 30
    assert edge.attributes["source_location"] == [110, 7, 0]
    assert edge.attributes["evidence_backed"] is True
    assert edge.attributes["candidate"] is True
    assert all(node.kind != "invariant" for node in model.nodes.values())


def test_ast_projection_round_trips_through_export_and_load(tmp_path):
    evidence = SemanticRelationshipEvidence(
        contract="Vault", function="deposit", relation="reads", target="balance",
        confidence=0.91, source="solc-json-ast:Vault.sol", ast_node_id=31,
        source_location=(120, 5, 0),
    )
    model = SystemModel()
    model.project_ast_evidence([evidence])
    path = tmp_path / "system.json"
    model.save(str(path))
    loaded = SystemModel.load(str(path))
    assert loaded.SCHEMA_VERSION == "1.22.0"
    assert loaded.export() == model.export()
    assert loaded.validate() == []
