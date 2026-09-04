from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.evidence_reasoning_provider import CanonicalEvidenceReasoningProvider, EvidenceReasoningPolicy
from cydra.security_reasoning import SecurityReasoningInputs
from cydra.system_model import SystemModel


def model():
    result = SystemModel()
    result.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 42, (10, 2, 1), 12, 20,
    ))
    return result


def test_provider_derives_only_from_evidence_backed_edges():
    inputs = CanonicalEvidenceReasoningProvider().propose(model())
    assert len(inputs.hypotheses) == 1
    assert len(inputs.observations) == 1
    assert inputs.hypotheses[0].name.startswith("relationship:function:Vault:ast:12:writes:")
    assert inputs.observations[0].name.startswith("verify:function:Vault:ast:12:writes:")
    assert set(inputs.hypotheses[0].predictions[inputs.observations[0].name]) == {"CONFIRMED", "REFUTED"}


def test_provider_never_labels_proposal_as_finding_or_authorization():
    inputs = CanonicalEvidenceReasoningProvider().propose(model())
    assert all("finding" not in h.name.lower() for h in inputs.hypotheses)
    # Observation.authorized is the planner's eligibility flag. The provider
    # does not mint an InvestigationExecutionAuthorization or execution request;
    # the live controller creates those only after plan selection.
    assert all(observation.authorized is True for observation in inputs.observations)
    assert all(not hasattr(observation, "authorization") for observation in inputs.observations)
    assert all(observation.execution_request is None for observation in inputs.observations)


def _proposal_signature(inputs):
    return (
        tuple((h.name, h.probability, tuple(sorted((key, tuple(sorted(value.items()))) for key, value in h.predictions.items()))) for h in inputs.hypotheses),
        tuple((o.name, tuple(o.outcomes), o.cost, o.authorized, o.execution_request_digest, o.domain) for o in inputs.observations),
    )


def test_provider_is_bounded_and_deterministic():
    policy = EvidenceReasoningPolicy(max_hypotheses=1, max_observations=1)
    provider = CanonicalEvidenceReasoningProvider(policy)
    first = provider.propose(model())
    second = provider.propose(model())
    assert _proposal_signature(first) == _proposal_signature(second)
    assert len(first.hypotheses) <= 1
    assert len(first.observations) <= 1


def test_provider_ignores_non_evidence_edges_and_low_confidence_edges():
    source = model()
    source.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "deposit", "writes", "shares", 0.2,
        "solc-json-ast:Vault.sol", 43, (11, 2, 1), 13, 21,
    ))
    source.connect("function:Vault:ast:12", "unrelated", "state_variable:Vault:ast:20")
    inputs = CanonicalEvidenceReasoningProvider(EvidenceReasoningPolicy(minimum_confidence=0.9)).propose(source)
    assert len(inputs.hypotheses) == 1
    assert inputs.hypotheses[0].name == "relationship:function:Vault:ast:12:writes:state_variable:Vault:ast:20"


def _reentrancy_model(call_offset=10, write_offset=20):
    result = SystemModel()
    result.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "external_call", "token.transfer", 0.95,
        "solc-json-ast:Vault.sol", 50, (call_offset, 2, 1), 12, None,
    ))
    result.add_ast_evidence(SemanticRelationshipEvidence(
        "Vault", "withdraw", "writes", "totalAssets", 0.95,
        "solc-json-ast:Vault.sol", 51, (write_offset, 2, 1), 12, 20,
    ))
    return result


def test_provider_emits_atomic_competing_security_hypotheses():
    inputs = CanonicalEvidenceReasoningProvider(EvidenceReasoningPolicy(
        max_hypotheses=2, max_observations=1, max_security_claims=1,
    )).propose(_reentrancy_model())

    assert isinstance(inputs, SecurityReasoningInputs)
    assert len(inputs.hypotheses) == 2
    assert len(inputs.observations) == 1
    assert inputs.hypotheses[0].name.startswith("security:reentrancy:")
    assert inputs.hypotheses[1].name.startswith("security:benign-external-interaction:")
    assert inputs.security_claims[0].hypothesis_id == inputs.hypotheses[0].hypothesis_id
    assert inputs.security_claims[0].claim["claim_kind"] == "security_hypothesis"
    assert inputs.security_claims[0].claim["competing_hypothesis_id"] == inputs.hypotheses[1].hypothesis_id


def test_security_pair_is_not_emitted_when_ordering_is_not_supported():
    inputs = CanonicalEvidenceReasoningProvider().propose(_reentrancy_model(call_offset=30, write_offset=20))
    assert not isinstance(inputs, SecurityReasoningInputs)
    assert all(not hypothesis.name.startswith("security:") for hypothesis in inputs.hypotheses)


def test_security_budget_never_splits_competing_pair():
    inputs = CanonicalEvidenceReasoningProvider(EvidenceReasoningPolicy(
        max_hypotheses=1, max_observations=1, max_security_claims=16,
    )).propose(_reentrancy_model())
    assert len(inputs.hypotheses) <= 1
    assert all(not hypothesis.name.startswith("security:") for hypothesis in inputs.hypotheses)


from cydra.evidence_reasoning_provider import EvidenceReasoningPolicy, proposals_from_invariant_candidates
from cydra.invariants import InvariantCandidate

def test_invariant_candidate_proposals_preserve_competing_semantics_and_budget():
    candidates = [
        InvariantCandidate(f"candidate:{i}", f"property {i}", (f"e{i}",), 0.9, 1)
        for i in range(3)
    ]
    inputs = proposals_from_invariant_candidates(
        candidates, policy=EvidenceReasoningPolicy(max_hypotheses=3, max_observations=3)
    )
    assert len(inputs.hypotheses) == 2
    assert len(inputs.observations) == 1
    names = {h.name for h in inputs.hypotheses}
    assert names == {"invariant-holds:candidate:0", "invariant-violated:candidate:0"}
    assert inputs.observations[0].discriminates_hypothesis_ids == tuple(
        h.hypothesis_id for h in inputs.hypotheses
    )

def test_low_confidence_invariant_candidates_are_not_promoted_to_reasoning_inputs():
    candidate = InvariantCandidate("candidate:weak", "weak property", ("e1",), 0.2, 1)
    inputs = proposals_from_invariant_candidates(
        [candidate], policy=EvidenceReasoningPolicy(minimum_confidence=0.5)
    )
    assert inputs.hypotheses == ()
    assert inputs.observations == ()
