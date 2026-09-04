from cydra.security_claim_reasoning import ClaimDecision, SecurityClaimReasoner
from test_security_claim_reasoning import _graph, _rule


def _competing_graph(state="supported"):
    graph = _graph()
    graph.model.nodes["hypothesis:other"].attributes["state"] = state
    graph.model.connect("hypothesis:h1", "competes_with", "hypothesis:other", provenance="explicit_security_reasoning")
    return graph


def test_supported_competing_hypothesis_blocks_security_claim():
    result = SecurityClaimReasoner().evaluate(_competing_graph("supported"), [_rule(competing_hypothesis_id="hypothesis:other")])[0]
    assert result.decision == ClaimDecision.UNRESOLVED
    assert "remains supported" in result.reasons[0]


def test_unresolved_competing_hypothesis_blocks_security_claim():
    result = SecurityClaimReasoner().evaluate(_competing_graph("unresolved"), [_rule(competing_hypothesis_id="hypothesis:other")])[0]
    assert result.decision == ClaimDecision.UNRESOLVED
    assert "remains unresolved" in result.reasons[0]


def test_contradicted_competing_hypothesis_allows_security_claim():
    result = SecurityClaimReasoner().evaluate(_competing_graph("contradicted"), [_rule(competing_hypothesis_id="hypothesis:other")])[0]
    assert result.decision == ClaimDecision.EMITTED


def test_competing_hypothesis_requires_canonical_binding():
    graph = _graph()
    graph.model.nodes["hypothesis:other"].attributes["state"] = "contradicted"
    result = SecurityClaimReasoner().evaluate(graph, [_rule(competing_hypothesis_id="hypothesis:other")])[0]
    assert result.decision == ClaimDecision.BLOCKED
    assert "canonically bound" in result.reasons[0]


def test_probability_ranking_does_not_resolve_competitor():
    graph = _competing_graph("unresolved")
    graph.model.nodes["hypothesis:h1"].attributes["probability"] = 0.99
    graph.model.nodes["hypothesis:other"].attributes["probability"] = 0.01
    result = SecurityClaimReasoner().evaluate(graph, [_rule(competing_hypothesis_id="hypothesis:other")])[0]
    assert result.decision == ClaimDecision.UNRESOLVED


def test_claim_without_competing_hypothesis_preserves_existing_behavior():
    result = SecurityClaimReasoner().evaluate(_graph(), [_rule()])[0]
    assert result.decision == ClaimDecision.EMITTED
