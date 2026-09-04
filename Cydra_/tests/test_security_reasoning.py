from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.evidence_reasoning_provider import CanonicalEvidenceReasoningProvider, EvidenceReasoningPolicy
from cydra.reasoning_graph import ReasoningGraph
from cydra.security_reasoning import SecurityReasoningInputs, persist_security_claims
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


def safe_order_model():
    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 101, (100, 8, 1), 10, 20,
    ))
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "external_call", "token.transfer", 0.95,
        "solc-json-ast:Vault.sol", 100, (120, 10, 1), 10, None,
    ))
    return model


def test_security_reasoner_emits_competing_security_hypotheses_from_multi_edge_evidence():
    inputs = CanonicalEvidenceReasoningProvider().propose(vulnerable_order_model())

    assert isinstance(inputs, SecurityReasoningInputs)
    assert len(inputs.security_claims) == 1
    names = {hypothesis.name for hypothesis in inputs.hypotheses}
    primary = next(h for h in inputs.hypotheses if h.name.startswith("security:reentrancy:"))
    alternative = next(h for h in inputs.hypotheses if h.name.startswith("security:benign-external-interaction:"))
    assert primary.name in names and alternative.name in names
    assert inputs.observations[0].name.startswith("verify:security:reentrancy:")
    assert set(primary.predictions[inputs.observations[0].name]) == {
        "CALLBACK_CONFIRMED", "CALLBACK_NOT_REPRODUCED", "INCONCLUSIVE"
    }
    claim = inputs.security_claims[0].claim
    assert claim["claim_kind"] == "security_hypothesis"
    assert claim["mechanism"] == "external_call_precedes_state_write"
    assert len(claim["evidence_refs"]) == 2
    assert claim["competing_hypothesis_id"] == alternative.hypothesis_id


def test_security_reasoner_does_not_call_safe_order_a_security_claim():
    inputs = CanonicalEvidenceReasoningProvider().propose(safe_order_model())
    assert not isinstance(inputs, SecurityReasoningInputs)
    assert all(not h.name.startswith("security:reentrancy:") for h in inputs.hypotheses)


def test_security_reasoner_is_bounded_and_deterministic():
    policy = EvidenceReasoningPolicy(max_hypotheses=1, max_observations=1, max_security_claims=1)
    provider = CanonicalEvidenceReasoningProvider(policy)
    first = provider.propose(vulnerable_order_model())
    second = provider.propose(vulnerable_order_model())
    assert first.hypotheses[0].name == second.hypotheses[0].name
    assert first.observations[0].name == second.observations[0].name
    assert len(first.hypotheses) == 1
    assert len(first.observations) == 1
    assert not isinstance(first, SecurityReasoningInputs)


def test_security_reasoner_does_not_compose_relationships_without_ordering_evidence():
    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "external_call", "token.transfer", 0.95,
        "solc-json-ast:Vault.sol", 100, None, 10, None,
    ))
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 101, None, 10, 20,
    ))

    inputs = CanonicalEvidenceReasoningProvider().propose(model)
    assert not isinstance(inputs, SecurityReasoningInputs)
    assert all(not h.name.startswith("security:reentrancy:") for h in inputs.hypotheses)


def test_security_reasoner_does_not_compose_relationships_across_functions():
    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "external_call", "token.transfer", 0.95,
        "solc-json-ast:Vault.sol", 100, (100, 10, 1), 10, None,
    ))
    model.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "deposit", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 101, (120, 8, 1), 11, 20,
    ))

    inputs = CanonicalEvidenceReasoningProvider().propose(model)
    assert not isinstance(inputs, SecurityReasoningInputs)
    assert all(not h.name.startswith("security:reentrancy:") for h in inputs.hypotheses)


def test_security_claims_persist_as_reasoning_metadata_not_findings():
    inputs = CanonicalEvidenceReasoningProvider().propose(vulnerable_order_model())
    graph = ReasoningGraph(vulnerable_order_model())
    graph.add_hypotheses(list(inputs.hypotheses))
    persist_security_claims(graph, inputs)

    node = graph.model.nodes[next(h.hypothesis_id for h in inputs.hypotheses if h.name.startswith("security:reentrancy:"))]
    assert node.kind == "hypothesis"
    assert node.attributes["security_claim"]["claim_kind"] == "security_hypothesis"
    assert all(item.kind != "finding" for item in graph.model.nodes.values())
