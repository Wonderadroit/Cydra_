from pathlib import Path

from cydra.audit_session import RepositoryAuditSession
from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_verification import CausalVerificationState, verify_persisted_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.finding_persistence import persist_finding
from cydra.foundry import FoundryAuthorization, FoundryResult, result_to_evidence
from cydra.impact import ImpactLevel, assess_impact
from cydra.planner import Hypothesis, Observation, Plan
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.updater import EvidencePolarity

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "foundry"
SOURCE = (FIXTURE_ROOT / "src" / "InvariantVault.sol").read_text(encoding="utf-8")
AUTHORIZATION = FoundryAuthorization("test-authorized-foundry")


def test_foundry_fixture_flows_from_authorized_intake_to_persisted_finding():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE, "authorized audit target"),
        ScopeRule("test/**", ScopeState.OUT_OF_SCOPE, "tests are not audit targets"),
    ])
    intake = RepositoryAuditSession(policy.decide).scan(
        ["src/InvariantVault.sol"], {"src/InvariantVault.sol": SOURCE}
    )

    orchestrator = ReasoningOrchestrator()
    orchestrator.attach_audit_session(intake)

    hypothesis = Hypothesis(
        "accounting invariant can be violated", 0.25,
        {"check accounting": {"COUNTEREXAMPLE": 0.8, "NO_COUNTEREXAMPLE": 0.2}},
    )
    observation = Observation("check accounting", ["COUNTEREXAMPLE", "NO_COUNTEREXAMPLE"], 1.0, authorized=True)
    plan = Plan("check accounting", 0.6, 0.6, "Fixture invariant test is an authorized high-information observation.")
    orchestrator.record_authorized_plan(plan, [hypothesis], observation)

    result = FoundryResult(
        ("forge", "test", "--match-test", "testFuzz_TotalDepositsMustTrackOutstandingBalance"),
        1, "Failing invariant: totalDeposits diverges from account balance", "counterexample trace",
        authorization_id=AUTHORIZATION.authorization_id, scope_status=AUTHORIZATION.scope_status,
        execution_id=observation.planned_execution_id,
    )
    update = orchestrator.ingest_observation_result(
        result, observation, [hypothesis], "foundry:accounting-counterexample",
        evidence_polarity={hypothesis.name: EvidencePolarity.SUPPORTS},
    )
    outcome_evidence_id = update.evidence_node_id
    assert outcome_evidence_id is not None

    replay_execution_id = "execution:accounting-replay"
    verification_evidence_id = orchestrator.graph.add_evidence(result_to_evidence(
        FoundryResult(
            ("forge", "test", "--match-test", "testFuzz_TotalDepositsMustTrackOutstandingBalance"),
            1, "Independent replay reproduced the counterexample", "replay trace",
            authorization_id=AUTHORIZATION.authorization_id, scope_status=AUTHORIZATION.scope_status,
            execution_id=replay_execution_id,
        ), "foundry:accounting-replay"
    ))
    orchestrator.model.connect(
        verification_evidence_id,
        "supports",
        hypothesis.hypothesis_id,
        provenance="independent_verification",
    )
    chain = CausalChain(
        "causal:accounting-invariant", hypothesis.hypothesis_id,
        update.observation_node_id, outcome_evidence_id, verification_evidence_id,
        update.belief_node_ids[0], intake.session_id,
    )
    persist_causal_chain(orchestrator.model, chain)
    causal = verify_persisted_causal_chain(orchestrator.model, chain.chain_id)
    assert causal.state is CausalVerificationState.VERIFIED

    finding = Finding(
        "finding:accounting-invariant", "Accounting invariant can be violated",
        "The authorized Foundry observation produced and independently reproduced a counterexample.",
        ImpactLevel.HIGH.value,
        assess_impact(
            level=ImpactLevel.HIGH, asset_at_risk="vault accounting",
            consequence="accounting state can diverge from the expected outstanding balance",
            evidence_ids=(outcome_evidence_id, verification_evidence_id),
        ),
        ("InvariantVault",), (outcome_evidence_id, verification_evidence_id),
        hypothesis.hypothesis_id, causal_chain_id=chain.chain_id, audit_session_id=intake.session_id,
    )
    candidate = FindingCandidate(True, False, True, True, True, True, True)
    gate = evaluate_finding_graph(orchestrator.graph, candidate, finding)
    assert gate.decision is GateDecision.READY, gate.reasons

    assert persist_finding(orchestrator.graph, finding) == finding.finding_id
    assert orchestrator.model.nodes[finding.finding_id].kind == "finding"
    assert orchestrator.model.nodes[finding.finding_id].attributes["canonical_audit_session_id"] == intake.session_id
    assert orchestrator.graph.verify_history_integrity() == []
