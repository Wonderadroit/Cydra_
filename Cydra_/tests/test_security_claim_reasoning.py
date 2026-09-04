from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding_gate import FindingCandidate
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.reasoning_graph import ReasoningGraph
from cydra.security_claim_reasoning import (
    ClaimDecision,
    SecurityClaimDraftProvider,
    SecurityClaimReasoner,
    SecurityClaimRule,
)
from cydra.system_model import Node


def _graph(
    *,
    hypothesis_state="supported",
    invariant_state="supported",
    bind_invariant=True,
    add_predicate=True,
    predicate_state="verified",
    predicate_hypothesis="hypothesis:h1",
    predicate_invariants=("invariant:i1",),
    predicate_trace="causal:c1",
    bind_predicate_hypothesis=True,
    bind_predicate_invariant=True,
    bind_predicate_trace=True,
    add_wrong_trace=False,
):
    graph = ReasoningGraph()
    nodes = (
        ("hypothesis:h1", "hypothesis", {"state": hypothesis_state}),
        ("hypothesis:other", "hypothesis", {"state": "supported"}),
        ("observation:o1", "observation", {}),
        ("evidence:e1", "evidence", {}),
        ("evidence:v1", "evidence", {}),
        ("evidence:e2", "evidence", {}),
        ("belief_update:b1", "belief", {"hypothesis_id": "hypothesis:h1"}),
        ("invariant:i1", "invariant", {"verification_state": invariant_state}),
    )
    if add_wrong_trace:
        nodes += (
            ("observation:o2", "observation", {}),
            ("belief_update:b2", "belief", {"hypothesis_id": "hypothesis:other"}),
        )
    if add_predicate:
        nodes += (
            (
                "security_predicate:p1",
                "security_predicate",
                {
                    "verification_state": predicate_state,
                    "hypothesis_id": predicate_hypothesis,
                    "invariant_ids": list(predicate_invariants),
                    "causal_chain_id": predicate_trace,
                },
            ),
        )
    for node_id, kind, attrs in nodes:
        graph.model.add_node(Node(node_id, kind, node_id, attrs))

    graph.model.connect("evidence:e1", "supports", "hypothesis:h1")
    graph.model.connect("evidence:v1", "supports", "hypothesis:h1")
    graph.model.connect("evidence:e2", "supports", "hypothesis:other")
    if bind_invariant:
        graph.model.connect("invariant:i1", "informs", "hypothesis:h1")
    persist_causal_chain(
        graph.model,
        CausalChain(
            "causal:c1",
            "hypothesis:h1",
            "observation:o1",
            "evidence:e1",
            "evidence:v1",
            "belief_update:b1",
        ),
    )
    if add_wrong_trace:
        persist_causal_chain(
            graph.model,
            CausalChain(
                "causal:c2",
                "hypothesis:other",
                "observation:o2",
                "evidence:e2",
                "evidence:e2",
                "belief_update:b2",
            ),
        )
    if add_predicate and bind_predicate_hypothesis:
        graph.model.connect(predicate_hypothesis, "asserts_security_predicate", "security_predicate:p1")
    if add_predicate and bind_predicate_invariant:
        for invariant_id in predicate_invariants:
            graph.model.connect("security_predicate:p1", "grounds_invariant", invariant_id)
    if add_predicate and bind_predicate_trace:
        graph.model.connect("security_predicate:p1", "verified_by_trace", predicate_trace)
    return graph


def _rule(**overrides):
    values = dict(
        finding_id="finding:f1",
        title="Explicit security claim",
        summary="The verified invariant permits the claimed security consequence.",
        severity="HIGH",
        impact=ImpactAssessment(
            ImpactLevel.HIGH,
            "asset:a1",
            "an explicitly demonstrated security consequence",
            evidence_ids=("evidence:e1",),
        ),
        affected_components=("contract:C",),
        hypothesis_id="hypothesis:h1",
        causal_chain_id="causal:c1",
        evidence_ids=("evidence:e1",),
        candidate=FindingCandidate(True, False, True, True, True, True, True),
        required_invariant_ids=("invariant:i1",),
        predicate_id="security_predicate:p1",
    )
    values.update(overrides)
    return SecurityClaimRule(**values)


def test_emits_only_after_canonical_predicate_binds_supported_state():
    result = SecurityClaimReasoner().evaluate(_graph(), [_rule()])[0]
    assert result.decision == ClaimDecision.EMITTED
    assert result.draft is not None
    assert result.draft.hypothesis_id == "hypothesis:h1"


def test_missing_security_predicate_blocks_claim():
    result = SecurityClaimReasoner().evaluate(_graph(add_predicate=False), [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "security predicate" in result.reasons[0]


def test_missing_predicate_hypothesis_edge_blocks_claim():
    result = SecurityClaimReasoner().evaluate(_graph(bind_predicate_hypothesis=False), [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "claim hypothesis" in result.reasons[0]


def test_predicate_bound_to_wrong_hypothesis_blocks_claim():
    result = SecurityClaimReasoner().evaluate(
        _graph(predicate_hypothesis="hypothesis:other", bind_predicate_hypothesis=False),
        [_rule()],
    )[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "wrong claim hypothesis" in result.reasons[0]


def test_missing_predicate_invariant_edge_blocks_claim():
    result = SecurityClaimReasoner().evaluate(_graph(bind_predicate_invariant=False), [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "required invariant" in result.reasons[0]


def test_predicate_bound_to_wrong_invariant_blocks_claim():
    graph = _graph(bind_predicate_invariant=False)
    graph.model.add_node(Node("invariant:i2", "invariant", "invariant:i2", {"verification_state": "supported"}))
    graph.model.nodes["security_predicate:p1"].attributes["invariant_ids"] = ["invariant:i2"]
    graph.model.connect("security_predicate:p1", "grounds_invariant", "invariant:i2")
    result = SecurityClaimReasoner().evaluate(graph, [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "invariant binding" in result.reasons[0]


def test_missing_predicate_trace_edge_blocks_claim():
    result = SecurityClaimReasoner().evaluate(_graph(bind_predicate_trace=False), [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "causal trace" in result.reasons[0]


def test_predicate_bound_to_wrong_causal_trace_blocks_claim():
    graph = _graph(add_wrong_trace=True, bind_predicate_trace=False)
    graph.model.nodes["security_predicate:p1"].attributes["causal_chain_id"] = "causal:c2"
    graph.model.connect("security_predicate:p1", "verified_by_trace", "causal:c2")
    result = SecurityClaimReasoner().evaluate(graph, [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "wrong causal trace" in result.reasons[0]


def test_unverified_security_predicate_blocks_claim():
    result = SecurityClaimReasoner().evaluate(_graph(predicate_state="unverified"), [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "predicate is not verified" in result.reasons[0]


def test_legacy_informs_edge_does_not_replace_predicate_binding():
    graph = _graph(bind_predicate_invariant=False)
    graph.model.connect("invariant:i1", "informs", "hypothesis:other")
    result = SecurityClaimReasoner().evaluate(graph, [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert result.draft is None


def test_invariant_contradiction_must_target_claim_hypothesis():
    graph = _graph()
    graph.model.connect("invariant:i1", "contradicts", "hypothesis:other")
    result = SecurityClaimReasoner().evaluate(graph, [_rule()])[0]
    assert result.decision == ClaimDecision.EMITTED


def test_direct_invariant_contradiction_blocks_claim():
    graph = _graph()
    graph.model.connect("invariant:i1", "contradicts", "hypothesis:h1")
    result = SecurityClaimReasoner().evaluate(graph, [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "contradicts the exact claim hypothesis" in result.reasons[0]


def test_unresolved_hypothesis_does_not_become_security_claim():
    result = SecurityClaimReasoner().evaluate(_graph(hypothesis_state="unresolved"), [_rule()])[0]
    assert result.decision == ClaimDecision.UNRESOLVED
    assert result.draft is None


def test_contradicted_invariant_blocks_claim():
    result = SecurityClaimReasoner().evaluate(_graph(invariant_state="contradicted"), [_rule()])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "contradicted" in result.reasons[0]


def test_untrusted_evidence_cannot_support_claim():
    graph = _graph()
    rule = _rule(evidence_ids=("evidence:e2",))
    result = SecurityClaimReasoner().evaluate(graph, [rule])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert result.draft is None


def test_claim_severity_must_match_impact():
    result = SecurityClaimReasoner().evaluate(_graph(), [_rule(severity="MEDIUM")])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "impact level" in result.reasons[0]


def test_autonomous_provider_requires_explicit_claim_contract_and_predicate():
    graph = _graph()
    graph.model.nodes["hypothesis:h1"].attributes["security_claim"] = {
        "claim_kind": "finding",
        "finding_id": "finding:f1",
        "title": "Explicit security claim",
        "summary": "The verified invariant permits the claimed security consequence.",
        "severity": "HIGH",
        "asset_at_risk": "asset:a1",
        "consequence": "an explicitly demonstrated security consequence",
        "affected_components": ["contract:C"],
        "evidence_ids": ["evidence:e1"],
        "impact_evidence_ids": ["evidence:e1"],
        "required_invariant_ids": ["invariant:i1"],
        "predicate_id": "security_predicate:p1",
        "in_scope": True,
        "reproducible": True,
        "hypothesis_resolved": True,
    }
    drafts = SecurityClaimDraftProvider().propose(graph, None)
    assert len(drafts) == 1
    assert drafts[0].finding_id == "finding:f1"


def test_autonomous_provider_does_not_infer_from_relationships_without_claim_contract():
    graph = _graph()
    assert SecurityClaimDraftProvider().propose(graph, None) == ()
