from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.repository_model import RepositoryModel, SourceContract, SourceFunction
from cydra.semantic_model import derive_semantic_model


def test_semantic_model_preserves_ast_evidence_and_state_candidates():
    repository = RepositoryModel(
        root=".",
        contracts=[
            SourceContract(
                name="Vault",
                file="Vault.sol",
                state_variables=("balance",),
                functions=(SourceFunction(name="deposit", file="Vault.sol"),),
            )
        ],
    )
    evidence = SemanticRelationshipEvidence(
        contract="Vault",
        function="deposit",
        relation="writes",
        target="balance",
        confidence=0.95,
        source="solc-json-ast:Vault.sol",
        ast_node_id=30,
        source_location=(110, 7, 0),
    )

    model = derive_semantic_model(repository, [evidence])
    function = model.contracts[0].functions[0]

    assert function.state_candidates == ("balance",)
    assert function.ast_evidence == (evidence,)
    assert model.ast_evidence == (evidence,)


def test_semantic_model_does_not_infer_state_without_ast_evidence():
    repository = RepositoryModel(
        root=".",
        contracts=[
            SourceContract(
                name="Vault",
                file="Vault.sol",
                state_variables=("balance",),
                functions=(SourceFunction(name="ping", file="Vault.sol"),),
            )
        ],
    )

    model = derive_semantic_model(repository)
    function = model.contracts[0].functions[0]

    assert function.state_candidates == ()
    assert function.ast_evidence == ()
    assert model.ast_evidence == ()
