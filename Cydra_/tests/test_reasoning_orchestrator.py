from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.audit_session import RepositoryAuditSession
from cydra.invariants import candidates_from_system_model
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.planner import Hypothesis, Observation
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.system_model import Node, SystemModel


def test_plan_next_projects_hypotheses_and_persists_selected_plan():
    hypotheses = [Hypothesis("auth-bypass", 0.7, {"role-check": {"allowed": 0.2, "denied": 0.8}}), Hypothesis("secure-path", 0.3, {"role-check": {"allowed": 0.9, "denied": 0.1}})]
    observations = [Observation("role-check", ["allowed", "denied"], 1.0, authorized=True)]
    orchestrator = ReasoningOrchestrator()
    result = orchestrator.plan_next(hypotheses, observations)
    assert result is not None
    assert result.plan.observation == "role-check"
    assert result.persistent_hypothesis_ids == ("hypothesis:auth-bypass", "hypothesis:secure-path")
    observation = orchestrator.model.nodes["observation:role-check"]
    assert observation.attributes["planned"] is True
    assert observation.attributes["expected_information_gain"] == result.plan.expected_information_gain
    assert orchestrator.graph.history[-1]["type"] == "PLAN_RECORDED"
    assert not any(event["type"] == "OBSERVATION_EXECUTED" for event in orchestrator.graph.history)


def _evidence_model(confidence=0.95):
    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence("Vault", "withdraw", "writes", "totalAssets", confidence, "solc-json-ast:Vault.sol", 42, (10, 2, 1)))
    return model


def test_plan_next_persists_derived_invariant_candidates():
    orchestrator = ReasoningOrchestrator(_evidence_model())
    hypotheses = [Hypothesis("accounting-bug", 0.8, {"check": {"yes": 0.8, "no": 0.2}})]
    result = orchestrator.plan_next(hypotheses, [Observation("check", ["yes", "no"], 1.0, True)])
    candidate = result.invariant_candidates[0]
    persisted = orchestrator.model.nodes[candidate.candidate_id]
    assert persisted.kind == "invariant"
    assert persisted.label == candidate.statement
    assert persisted.attributes["status"] == "candidate"
    assert persisted.attributes["source_ids"] == list(candidate.source_ids)
    assert persisted.attributes["confidence"] == candidate.confidence
    assert persisted.attributes["evidence_count"] == candidate.evidence_count
    assert any(event["type"] == "INVARIANT_CANDIDATES_RECORDED" for event in orchestrator.graph.history)
    assert any(event["type"] == "HYPOTHESES_SYNCHRONIZED" for event in orchestrator.graph.history)
    assert orchestrator.graph.history[-1]["type"] == "PLAN_RECORDED"


def test_plan_next_can_persist_explicit_invariant_hypothesis_observation_chain():
    orchestrator = ReasoningOrchestrator(_evidence_model())
    candidate_id = orchestrator.derive_invariants()[0].candidate_id
    hypotheses = [Hypothesis("accounting-bug", 0.8, {"check": {"yes": 0.8, "no": 0.2}}), Hypothesis("safe-path", 0.2, {"check": {"yes": 0.2, "no": 0.8}})]
    observation = Observation("check", ["yes", "no"], 1.0, True)
    result = orchestrator.plan_next(hypotheses, [observation], {candidate_id: ["hypothesis:accounting-bug"]})
    assert result is not None
    assert orchestrator.model.neighbors(candidate_id, "informs") == ["hypothesis:accounting-bug"]
    assert orchestrator.model.neighbors("hypothesis:accounting-bug", "tested_by") == ["observation:check"]
    assert orchestrator.model.neighbors("hypothesis:safe-path", "tested_by") == ["observation:check"]
    assert orchestrator.graph.validate() == []


def test_plan_next_does_not_infer_invariant_hypothesis_links():
    orchestrator = ReasoningOrchestrator(_evidence_model())
    hypotheses = [Hypothesis("accounting-bug", 0.8, {"check": {"yes": 0.8, "no": 0.2}})]
    result = orchestrator.plan_next(hypotheses, [Observation("check", ["yes", "no"], 1.0, True)])
    assert orchestrator.model.neighbors(result.invariant_candidates[0].candidate_id, "informs") == []


def test_plan_next_rejects_unauthorized_observation_by_not_planning_it():
    hypotheses = [Hypothesis("h1", 0.5, {"probe": {"yes": 1.0}}), Hypothesis("h2", 0.5, {"probe": {"no": 1.0}})]
    assert ReasoningOrchestrator().plan_next(hypotheses, [Observation("probe", ["yes", "no"], 1.0, False)]) is None


def test_record_authorized_plan_persists_plan_without_execution():
    hypotheses = [Hypothesis("h1", 0.6, {"probe": {"yes": 0.8, "no": 0.2}}), Hypothesis("h2", 0.4, {"probe": {"yes": 0.2, "no": 0.8}})]
    observation = Observation("probe", ["yes", "no"], 1.0, True)
    orchestrator = ReasoningOrchestrator()
    plan = orchestrator.plan_next(hypotheses, [observation]).plan
    observation_id = orchestrator.record_authorized_plan(plan, hypotheses, observation)
    assert observation_id == "observation:probe"
    assert orchestrator.model.nodes[observation_id].attributes["planned"] is True
    assert not orchestrator.graph.history[-1]["type"] == "OBSERVATION_EXECUTED"


def _verified_candidate_model():
    model = _evidence_model(0.91)
    candidate = candidates_from_system_model(model)[0]
    orchestrator = ReasoningOrchestrator(model)
    orchestrator.persist_invariants([candidate])
    candidate_id = candidate.candidate_id
    evidence_id = "evidence:solc-json-ast:Vault.sol:42"
    model.add_node(Node(evidence_id, "evidence", evidence_id, {"kind": "AST_RELATIONSHIP", "value": "Vault writes totalAssets", "interpretation": "compiler relationship", "confidence": 0.91, "provenance": {"source": "solc-json-ast:Vault.sol", "scope_status": "IN_SCOPE"}}))
    model.connect(candidate_id, "verified_by", evidence_id, provenance="explicit_verification")
    model.update_node_attributes(candidate_id, {"verification_state": "supported", "verified": True, "status": "supported", "verification_confidence": 0.91, "supporting_evidence_ids": ["solc-json-ast:Vault.sol:42"]})
    return model, candidate_id


def test_verified_invariant_bridge_enters_planner_and_preserves_chain():
    model, candidate_id = _verified_candidate_model()
    orchestrator = ReasoningOrchestrator(model)
    hypothesis = Hypothesis("accounting-violation", 0.7, {"accounting-check": {"violated": 0.9, "holds": 0.1}})
    result = orchestrator.plan_next([], [Observation("accounting-check", ["violated", "holds"], 1.0, True)], verified_invariant_hypotheses={candidate_id: hypothesis})
    assert result is not None
    assert result.persistent_hypothesis_ids == ("hypothesis:accounting-violation",)
    assert orchestrator.model.neighbors(candidate_id, "informs") == ["hypothesis:accounting-violation"]
    assert orchestrator.model.neighbors("hypothesis:accounting-violation", "tested_by") == ["observation:accounting-check"]
    node = orchestrator.model.nodes["hypothesis:accounting-violation"]
    assert node.attributes["provenance"] == "verified_invariant"
    assert node.attributes["invariant_id"] == candidate_id
    assert orchestrator.graph.validate() == []


def test_unverified_invariant_is_not_promoted_by_bridge():
    model = _evidence_model(0.99)
    candidate_id = candidates_from_system_model(model)[0].candidate_id
    orchestrator = ReasoningOrchestrator(model)
    fallback = Hypothesis("fallback", 0.5, {"check": {"yes": 0.5, "no": 0.5}})
    result = orchestrator.plan_next([fallback], [Observation("check", ["yes", "no"], 1.0, True)], verified_invariant_hypotheses={candidate_id: Hypothesis("should-not-auto-promote", 0.8, {"check": {"yes": 0.9, "no": 0.1}})})
    assert result is not None
    assert result.persistent_hypothesis_ids == ("hypothesis:fallback",)
    assert "hypothesis:should-not-auto-promote" not in orchestrator.model.nodes
    assert orchestrator.model.neighbors(candidate_id, "informs") == []


def test_verified_bridge_does_not_mutate_when_no_authorized_plan_exists():
    model, candidate_id = _verified_candidate_model()
    original_ids = list(model.nodes)
    orchestrator = ReasoningOrchestrator(model)
    hypothesis = Hypothesis("mapped", 0.5, {"probe": {"yes": 1.0}})
    assert orchestrator.plan_next([], [Observation("probe", ["yes", "no"], 1.0, False)], verified_invariant_hypotheses={candidate_id: hypothesis}) is None
    assert list(orchestrator.model.nodes) == original_ids
    assert orchestrator.model.neighbors(candidate_id, "informs") == []


def _session_result():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target"),
        ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE, "tests excluded"),
    ])
    session = RepositoryAuditSession(policy.decide)
    return session.scan(
        ["src/app.py", "tests/test_app.py"],
        {"src/app.py": "def run():\n    return 1\n", "tests/test_app.py": "def should_not_parse():\n    return 2\n"},
    )


def test_attach_audit_session_establishes_one_canonical_reasoning_boundary():
    result = _session_result()
    orchestrator = ReasoningOrchestrator()
    assert orchestrator.attach_audit_session(result) == result.session_id
    assert orchestrator.model is result.model
    assert orchestrator.model.nodes[result.session_id].kind == "audit_session"
    assert orchestrator.graph.history[-1]["type"] == "AUDIT_SESSION_ATTACHED"
    assert orchestrator.graph.history[-1]["intake_id"] == result.intake_id
    assert "module:tests/test_app.py" not in orchestrator.model.nodes
    assert orchestrator.graph.validate() == []


def test_attach_rejects_tampered_audit_session_before_mutation():
    result = _session_result()
    result.model.nodes[result.session_id].attributes["intake_id"] = "intake:tampered"
    orchestrator = ReasoningOrchestrator()
    try:
        orchestrator.attach_audit_session(result)
    except ValueError as exc:
        assert "provenance is invalid" in str(exc)
    else:
        raise AssertionError("expected provenance validation failure")
    assert orchestrator.model.nodes == {}
    assert orchestrator.model.edges == []
    assert orchestrator.graph.history == []


def test_attach_does_not_replace_existing_reasoning_state():
    result = _session_result()
    existing = SystemModel()
    existing.add_node(Node("hypothesis:H1", "hypothesis", "H1"))
    orchestrator = ReasoningOrchestrator(existing)
    try:
        orchestrator.attach_audit_session(result)
    except ValueError as exc:
        assert "non-empty reasoning graph" in str(exc)
    else:
        raise AssertionError("expected non-empty graph rejection")
    assert list(orchestrator.model.nodes) == ["hypothesis:H1"]
    assert orchestrator.graph.history == []


def test_attach_same_model_is_idempotent_without_duplicate_event():
    result = _session_result()
    orchestrator = ReasoningOrchestrator(result.model)
    first_history = list(orchestrator.graph.history)
    assert orchestrator.attach_audit_session(result) == result.session_id
    assert orchestrator.graph.history == first_history
