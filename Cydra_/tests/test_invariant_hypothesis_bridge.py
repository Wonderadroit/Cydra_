import pytest

from cydra.invariants import InvariantCandidate, VerificationState
from cydra.invariant_hypothesis_bridge import (
    InvariantHypothesis,
    hypotheses_from_verified_invariants,
    persist_invariant_hypotheses,
)
from cydra.system_model import Node, SystemModel


def candidate(candidate_id, statement, source_id, confidence):
    return InvariantCandidate(candidate_id, statement, (source_id,), confidence, 1)


def supported_model():
    model = SystemModel()
    model.add_node(Node("invariant:i1", "invariant", "balance remains solvent", {
        "verification_state": VerificationState.SUPPORTED.value,
        "verification_confidence": .9,
        "supporting_evidence_ids": ["e1"],
    }))
    model.add_node(Node("evidence:e1", "evidence", "e1", {}))
    model.connect("invariant:i1", "verified_by", "evidence:e1", provenance="explicit_verification")
    return model


def test_only_supported_invariants_with_explicit_proof_become_hypotheses():
    model = supported_model()
    model.add_node(Node("invariant:i2", "invariant", "unverified", {"verified": True, "confidence": .8}))
    results = hypotheses_from_verified_invariants(model, [
        candidate("invariant:i1", "balance remains solvent", "ast:withdraw", .9),
        candidate("invariant:i2", "unverified", "ast:deposit", .8),
    ])
    assert [r.invariant_id for r in results] == ["invariant:i1"]


def test_missing_verification_edge_blocks_bridge_even_if_state_claims_supported():
    model = SystemModel()
    model.add_node(Node("invariant:i1", "invariant", "balance remains solvent", {
        "verification_state": VerificationState.SUPPORTED.value,
        "verification_confidence": .9,
        "supporting_evidence_ids": ["e1"],
    }))
    model.add_node(Node("evidence:e1", "evidence", "e1", {}))
    assert hypotheses_from_verified_invariants(model, [
        candidate("invariant:i1", "balance remains solvent", "ast:withdraw", .9)
    ]) == []


def test_candidate_statement_cannot_substitute_canonical_invariant_statement():
    model = supported_model()
    assert hypotheses_from_verified_invariants(model, [
        candidate("invariant:i1", "attacker controls balance", "ast:withdraw", .9)
    ]) == []


def test_persists_hypothesis_with_canonical_informs_provenance():
    model = supported_model()
    hypotheses = hypotheses_from_verified_invariants(model, [
        candidate("invariant:i1", "balance remains solvent", "ast:withdraw", .9)
    ])
    persist_invariant_hypotheses(model, hypotheses)
    assert model.nodes["hypothesis:invariant:i1"].attributes["invariant_id"] == "invariant:i1"
    assert model.neighbors("invariant:i1", "informs") == ["hypothesis:invariant:i1"]


def test_explicit_hypothesis_id_can_receive_verified_invariant_provenance():
    model = supported_model()
    persist_invariant_hypotheses(model, [
        InvariantHypothesis(
            "hypothesis:solvency-bug",
            "invariant:i1",
            "Violation of invariant: balance remains solvent",
            .9,
        )
    ])
    assert model.nodes["hypothesis:solvency-bug"].attributes["provenance"] == "verified_invariant"
    assert model.neighbors("invariant:i1", "informs") == ["hypothesis:solvency-bug"]


def test_direct_persistence_rejects_unverified_invariant():
    model = SystemModel()
    model.add_node(Node("invariant:i1", "invariant", "balance remains solvent", {
        "verification_state": VerificationState.UNRESOLVED.value,
        "supporting_evidence_ids": ["e1"],
    }))
    model.add_node(Node("evidence:e1", "evidence", "e1", {}))
    model.connect("invariant:i1", "verified_by", "evidence:e1")
    with pytest.raises(ValueError, match="explicitly supported"):
        persist_invariant_hypotheses(model, [
            InvariantHypothesis(
                "hypothesis:solvency-bug",
                "invariant:i1",
                "Violation of invariant: balance remains solvent",
                .9,
            )
        ])


def test_boolean_verified_flag_alone_is_not_verification_evidence():
    model = SystemModel()
    model.add_node(Node("invariant:i1", "invariant", "balance remains solvent", {
        "verified": True,
        "confidence": 1.0,
    }))
    assert hypotheses_from_verified_invariants(model, [
        candidate("invariant:i1", "balance remains solvent", "ast:withdraw", 1.0)
    ]) == []


def test_existing_hypothesis_label_conflict_cannot_be_overwritten():
    model = supported_model()
    model.add_node(Node("hypothesis:h1", "hypothesis", "attacker controls balance", {"probability": .5}))
    before = model.nodes["hypothesis:h1"]
    with pytest.raises(ValueError, match="label conflicts"):
        persist_invariant_hypotheses(model, [
            InvariantHypothesis(
                "hypothesis:h1",
                "invariant:i1",
                "Violation of invariant: balance remains solvent",
                .9,
            )
        ])
    assert model.nodes["hypothesis:h1"] == before


def test_candidate_invariant_produces_explicit_competing_hypotheses():
    from cydra.invariant_hypothesis_bridge import competing_hypotheses_from_candidates

    hypotheses, observations = competing_hypotheses_from_candidates([
        candidate("invariant:i1", "balance remains solvent", "ast:withdraw", .8)
    ])

    assert [h.name for h in hypotheses] == [
        "invariant-holds:invariant:i1",
        "invariant-violated:invariant:i1",
    ]
    assert len(observations) == 1
    observation = observations[0]
    assert observation.discriminates_hypothesis_ids == tuple(h.hypothesis_id for h in hypotheses)
    assert set(observation.outcomes) == {"INVARIANT_PRESERVED", "INVARIANT_VIOLATED", "INCONCLUSIVE"}
    assert hypotheses[0].predictions[observation.name]["INVARIANT_PRESERVED"] > hypotheses[0].predictions[observation.name]["INVARIANT_VIOLATED"]
    assert hypotheses[1].predictions[observation.name]["INVARIANT_VIOLATED"] > hypotheses[1].predictions[observation.name]["INVARIANT_PRESERVED"]


def test_candidate_reasoning_keeps_competing_priors_symmetric_and_binds_targets():
    from cydra.invariants import InvariantCandidate
    from cydra.invariant_hypothesis_bridge import competing_hypotheses_from_candidates

    candidate = InvariantCandidate(
        candidate_id="candidate:transition-expression:fn:state:ast:42",
        statement="execution of deposit updates totalShares using (totalShares + totalAssets)",
        source_ids=("solc-json-ast:Vault.sol:42",),
        confidence=0.98,
        evidence_count=1,
        metadata={
            "category": "state_transition_expression",
            "source_function": "function:Vault:deposit",
            "written_state": "state:Vault:totalShares",
            "ast_node_id": "42",
        },
    )
    hypotheses, observations = competing_hypotheses_from_candidates([candidate])

    assert [h.probability for h in hypotheses] == [0.5, 0.5]
    assert observations[0].discriminates_hypothesis_ids == tuple(h.hypothesis_id for h in hypotheses)
    assert observations[0].target_ids == (
        "function:Vault:deposit",
        "state:Vault:totalShares",
        "42",
    )
    assert "discovery confidence describes evidence quality" in observations[0].rationale
