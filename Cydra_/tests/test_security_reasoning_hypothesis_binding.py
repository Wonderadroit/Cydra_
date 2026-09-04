from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.security_reasoning import SecurityReasoningInputs, security_reasoning_inputs
from cydra.system_model import SystemModel


def vulnerable_order_model():
    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "external_call", "token.transfer", 0.95,
        "solc-json-ast:Vault.sol", 100, (100, 10, 1), 10, None,
    ))
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 101, (120, 8, 1), 10, 20,
    ))
    return model


def test_security_reasoner_binds_verification_observation_to_exact_competing_pair():
    inputs = security_reasoning_inputs(vulnerable_order_model())
    assert isinstance(inputs, SecurityReasoningInputs)
    assert len(inputs.hypotheses) == 2
    assert len(inputs.observations) == 1

    primary, alternative = inputs.hypotheses
    observation = inputs.observations[0]

    assert observation.discriminates_hypothesis_ids == (
        primary.hypothesis_id,
        alternative.hypothesis_id,
    )
    assert observation.hypothesis_pair == observation.discriminates_hypothesis_ids


def test_security_reasoner_pair_is_stable_for_same_canonical_input():
    first = security_reasoning_inputs(vulnerable_order_model())
    second = security_reasoning_inputs(vulnerable_order_model())
    assert first.observations[0].discriminates_hypothesis_ids == second.observations[0].discriminates_hypothesis_ids
