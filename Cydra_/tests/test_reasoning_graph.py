from cydra.invariants import (
    CandidateVerification,
    VerificationEvidence,
    VerificationRole,
    VerificationState,
    verify_candidate,
)
from cydra.planner import Hypothesis, HypothesisState, Observation, Plan
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node
from cydra.updater import EvidencePolarity, UpdateResult, update_hypotheses


def make_case():
    hypotheses = [
        Hypothesis("H1", 0.6, {"check": {"yes": 0.9, "no": 0.1}}),
        Hypothesis("H2", 0.4, {"check": {"yes": 0.2, "no": 0.8}}),
    ]
    observation = Observation("check", ["yes", "no"], 1.0, True)
    plan = Plan("check", 0.2, 0.2, "information gain")
    result = update_hypotheses(
        hypotheses,
        "check",
        "yes",
        1.0,
        evidence_polarity={"H1": EvidencePolarity.SUPPORTS, "H2": EvidencePolarity.CONTRADICTS},
    )
    return hypotheses, observation, plan, result


def probs(r):
    return {h.name: h.probability for h in r.hypotheses}


def test_plan_observe_update_is_traceable():
    hypotheses, observation, plan, result = make_case()
    graph = ReasoningGraph()
    observation_id = graph.record_plan(plan, hypotheses, observation)
    evidence_id, causal_id = "evidence:check-result", "cause:authorization"
    graph.model.add_node(Node(evidence_id, "evidence", "Observed check result"))
    graph.model.add_node(Node(causal_id, "causal_chain", "Authorization explanation"))
    update = graph.record_update(result, observation_id, evidence_id, causal_id)
    assert graph.validate() == []
    assert len(update.belief_node_ids) == 2
    assert graph.model.neighbors(observation_id, "updates") == sorted(update.belief_node_ids)
    assert graph.model.neighbors(evidence_id, "derived_from") == [observation_id]
    assert graph.history[-1]["type"] == "UPDATE_RECORDED"
    for h in result.hypotheses:
        node = graph.model.nodes[h.hypothesis_id]
        assert node.attributes["probability"] == h.probability
        assert node.attributes["state"] == h.state.value


def test_update_persists_only_explicit_evidence_polarity():
    hypotheses = [
        Hypothesis("likely", 0.7, {"check": {"yes": 0.9}}, HypothesisState.SUPPORTED),
        Hypothesis("unlikely", 0.3, {"check": {"yes": 0.1}}, HypothesisState.CONTRADICTED),
        Hypothesis("unknown", 0.5, {"check": {"yes": 0.5}}, HypothesisState.UNRESOLVED),
    ]
    observation = Observation("check", ["yes"], 1.0, True)
    plan = Plan("check", 0.5, 0.5, "distinguish competing explanations")
    result = UpdateResult(
        hypotheses,
        "yes",
        1.0,
        "EXPLICIT_STATES",
        "states supplied by verification",
        {"likely": EvidencePolarity.SUPPORTS, "unlikely": EvidencePolarity.CONTRADICTS, "unknown": EvidencePolarity.NEUTRAL},
    )
    graph = ReasoningGraph()
    observation_id = graph.record_plan(plan, hypotheses, observation)
    evidence_id = "evidence:check"
    graph.model.add_node(Node(evidence_id, "evidence", "Observed yes"))
    graph.record_update(result, observation_id, evidence_id)

    supported = [e.target for e in graph.model.edges if e.source == evidence_id and e.relation == "supports"]
    contradicted = [e.target for e in graph.model.edges if e.source == evidence_id and e.relation == "contradicts"]
    assert supported == ["hypothesis:likely"]
    assert contradicted == ["hypothesis:unlikely"]
    assert "hypothesis:unknown" not in supported + contradicted
    beliefs = [graph.model.nodes[belief_id] for belief_id in graph.model.neighbors(observation_id, "updates")]
    polarity = {node.attributes["hypothesis_id"]: node.attributes["evidence_polarity"] for node in beliefs}
    assert polarity == {
        "hypothesis:likely": "supports",
        "hypothesis:unlikely": "contradicts",
        "hypothesis:unknown": "neutral",
    }


def test_graph_does_not_infer_polarity_from_hypothesis_state():
    hypotheses = [
        Hypothesis("supported-state", 0.7, {"check": {"yes": 0.9}}, HypothesisState.SUPPORTED),
        Hypothesis("contradicted-state", 0.3, {"check": {"yes": 0.1}}, HypothesisState.CONTRADICTED),
    ]
    observation = Observation("check", ["yes"], 1.0, True)
    plan = Plan("check", 0.5, 0.5, "explicit test")
    result = UpdateResult(hypotheses, "yes", 1.0, "UPDATED", "No polarity supplied")
    graph = ReasoningGraph()
    observation_id = graph.record_plan(plan, hypotheses, observation)
    evidence_id = "evidence:no-inference"
    graph.model.add_node(Node(evidence_id, "evidence", "Observed yes"))
    graph.record_update(result, observation_id, evidence_id)
    assert [e for e in graph.model.edges if e.source == evidence_id and e.relation in {"supports", "contradicts"}] == []


def test_direct_external_result_recording_is_disabled():
    """The graph cannot bypass authorization, request binding, receipt, or gateway state."""
    hypotheses, observation, plan, _ = make_case()
    graph = ReasoningGraph()
    try:
        graph.record_test_result(object(), observation, hypotheses, plan, "foundry:result")
    except RuntimeError as exc:
        assert "direct test-result recording is disabled" in str(exc)
    else:
        assert False, "direct result ingestion must not bypass the canonical execution gateway"
    assert graph.model.nodes == {}
    assert graph.history == []


def test_hypothesis_projection_synchronizes_changed_persistent_state():
    graph = ReasoningGraph()
    original = Hypothesis("access-control", 0.2, {"role-check": {"allowed": 0.1, "denied": 0.9}})
    updated = Hypothesis("access-control", 0.85, {"role-check": {"allowed": 0.8, "denied": 0.2}}, HypothesisState.SUPPORTED)
    graph.add_hypotheses([original])
    graph.add_hypotheses([updated])
    node = graph.model.nodes["hypothesis:access-control"]
    assert node.attributes["probability"] == 0.85
    assert node.attributes["predictions"] == updated.predictions
    assert node.attributes["state"] == updated.state.value
    assert graph.history[-1]["type"] == "HYPOTHESES_SYNCHRONIZED"


def test_explicit_invariant_hypothesis_link_is_persisted_with_provenance():
    graph = ReasoningGraph()
    graph.model.add_node(Node("candidate:Vault:writes:state_variable:Vault:totalAssets", "invariant", "Vault writes totalAssets", {"status": "candidate"}))
    graph.add_hypotheses([Hypothesis("accounting-bug", 0.7, {"check": {"yes": 0.8, "no": 0.2}})])
    links = graph.record_invariant_hypothesis_links({
        "candidate:Vault:writes:state_variable:Vault:totalAssets": ["hypothesis:accounting-bug"]
    }, rationale="The reviewer explicitly mapped the candidate to the accounting hypothesis.")
    assert links == [("candidate:Vault:writes:state_variable:Vault:totalAssets", "hypothesis:accounting-bug")]
    edge = next(e for e in graph.model.edges if e.relation == "informs")
    assert edge.attributes["provenance"] == "explicit_reasoning_mapping"
    assert "explicitly mapped" in edge.attributes["rationale"]
    assert graph.model.neighbors(edge.source, "informs") == [edge.target]
    assert graph.validate() == []
    assert graph.history[-1]["type"] == "INVARIANT_HYPOTHESIS_LINKS_RECORDED"


def test_invariant_hypothesis_link_does_not_guess_from_names():
    graph = ReasoningGraph()
    graph.model.add_node(Node("candidate:one", "invariant", "Same words as bug"))
    graph.add_hypotheses([Hypothesis("Same words as bug", 0.5, {})])
    assert graph.model.neighbors("candidate:one", "informs") == []


def test_invariant_hypothesis_link_requires_existing_node_types():
    graph = ReasoningGraph()
    graph.model.add_node(Node("candidate:one", "invariant", "Candidate"))
    try:
        graph.record_invariant_hypothesis_links({"candidate:one": ["hypothesis:missing"]})
    except KeyError:
        pass
    else:
        assert False


def test_unauthorized_plan_is_rejected():
    hypotheses, _, plan, _ = make_case()
    unauthorized = Observation("check", ["yes"], 1.0, False)
    try:
        ReasoningGraph().record_plan(plan, hypotheses, unauthorized)
    except ValueError:
        pass
    else:
        assert False


def test_wrong_provenance_node_types_are_rejected():
    hypotheses, observation, plan, result = make_case()
    graph = ReasoningGraph()
    obs_id = graph.record_plan(plan, hypotheses, observation)
    graph.model.add_node(Node("not-evidence", "asset", "Wrong kind"))
    try:
        graph.record_update(result, obs_id, "not-evidence")
    except ValueError:
        pass
    else:
        assert False


def test_unknown_prediction_preserves_beliefs():
    hypotheses = [Hypothesis("H1", 0.5, {"check": {"yes": 1.0}}), Hypothesis("H2", 0.5, {"check": {"no": 1.0}})]
    result = update_hypotheses(hypotheses, "check", "unknown", 1.0)
    assert result.status == "PARTIAL_UPDATE"
    assert [h.probability for h in result.hypotheses] == [0.5, 0.5]


def _verification_graph():
    graph = ReasoningGraph()
    candidate_id = "candidate:Vault:writes:state_variable:Vault:totalAssets"
    graph.model.add_node(Node(candidate_id, "invariant", "Vault writes totalAssets", {"status": "candidate"}))
    graph.model.add_node(Node("evidence:support", "evidence", "Execution supports invariant"))
    graph.model.add_node(Node("evidence:contradiction", "evidence", "Execution contradicts invariant"))
    return graph, candidate_id


def test_verification_state_is_persisted_with_supporting_evidence():
    graph, candidate_id = _verification_graph()
    verification = verify_candidate(
        __import__("cydra.invariants", fromlist=["InvariantCandidate"]).InvariantCandidate(
            candidate_id, "Vault writes totalAssets", ("ast:42",), 0.8, 1
        ),
        [VerificationEvidence("support", VerificationRole.SUPPORTS, 0.93, "Observed preserving behavior")],
    )
    graph.record_invariant_verification(verification)
    node = graph.model.nodes[candidate_id]
    assert verification.state == VerificationState.SUPPORTED
    assert node.attributes["verification_state"] == "supported"
    assert node.attributes["verified"] is True
    assert node.attributes["verification_evidence_ids"] == ["support"]
    assert graph.model.neighbors(candidate_id, "verified_by") == ["evidence:support"]
    assert graph.history[-1]["type"] == "INVARIANT_VERIFICATION_RECORDED"
    assert graph.validate() == []


def test_contradiction_dominates_support_and_blocks_verification():
    graph, candidate_id = _verification_graph()
    candidate_obj = __import__("cydra.invariants", fromlist=["InvariantCandidate"]).InvariantCandidate(
        candidate_id, "Vault writes totalAssets", ("ast:42",), 0.8, 1
    )
    verification = verify_candidate(candidate_obj, [
        VerificationEvidence("support", VerificationRole.SUPPORTS, 0.99),
        VerificationEvidence("contradiction", VerificationRole.CONTRADICTS, 0.4),
    ])
    graph.record_invariant_verification(verification)
    node = graph.model.nodes[candidate_id]
    assert verification.state == VerificationState.CONTRADICTED
    assert node.attributes["verified"] is False
    assert node.attributes["verification_state"] == "contradicted"
    assert graph.model.neighbors(candidate_id, "contradicted_by") == ["evidence:contradiction"]
    assert graph.model.neighbors(candidate_id, "verified_by") == ["evidence:support"]
    assert graph.validate() == []


def test_unresolved_verification_is_explicit_and_not_promoted():
    graph, candidate_id = _verification_graph()
    candidate_obj = __import__("cydra.invariants", fromlist=["InvariantCandidate"]).InvariantCandidate(
        candidate_id, "Vault writes totalAssets", ("ast:42",), 0.8, 1
    )
    verification = verify_candidate(candidate_obj, [VerificationEvidence("support", VerificationRole.NEUTRAL, 0.9)])
    graph.record_invariant_verification(verification)
    node = graph.model.nodes[candidate_id]
    assert verification.state == VerificationState.UNRESOLVED
    assert node.attributes["verified"] is False
    assert node.attributes["verification_state"] == "unresolved"
    assert graph.model.neighbors(candidate_id, "informs") == []


def test_verification_requires_canonical_evidence_nodes():
    graph, candidate_id = _verification_graph()
    verification = CandidateVerification(candidate_id, VerificationState.SUPPORTED, ("missing",), ("missing",), (), 0.9)
    try:
        graph.record_invariant_verification(verification)
    except KeyError:
        pass
    else:
        assert False
