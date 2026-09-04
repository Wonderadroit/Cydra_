from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.poc import POCArtifact
from cydra.poc_persistence import persist_poc, rehydrate_persisted_poc
from cydra.reasoning_graph import ReasoningGraph
from cydra.system_model import Node
from cydra.counterexample import Counterexample


def graph_with_finding() -> ReasoningGraph:
    graph = ReasoningGraph()
    for node_id, kind in (("hypothesis:h1", "hypothesis"), ("observation:o1", "observation"), ("evidence:e1", "evidence"), ("verification:v1", "evidence"), ("belief_update:b1", "belief")):
        graph.model.add_node(Node(node_id, kind, node_id))
    graph.model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="explicit_test")
    persist_causal_chain(graph.model, CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief_update:b1"))
    finding = Finding(finding_id="finding:1", title="Protected state can be altered", summary="A verified reasoning chain supports the security claim.", severity="HIGH", impact=ImpactAssessment(ImpactLevel.HIGH, "asset:vault", "loss of protected funds", evidence_ids=("evidence:e1",)), affected_components=("contract:Vault",), evidence_ids=("evidence:e1",), hypothesis_id="hypothesis:h1", causal_chain_id="causal:c1")
    persist_finding(graph, finding)
    return graph


def make_poc(**overrides) -> POCArtifact:
    values = dict(poc_id="poc:1", hypothesis_id="hypothesis:h1", counterexample=Counterexample(test_name="test_withdraw", trace=["call", "state_change", "assertion"], invariant="user balance cannot increase without attributable value", expected="invariant holds", actual="invariant violated"), expected_violation="user balance increases without attributable value", finding_id="finding:1", evidence_ids=("evidence:e1",))
    values.update(overrides)
    return POCArtifact(**values)


def test_poc_persistence_creates_canonical_lineage():
    graph = graph_with_finding()
    assert persist_poc(graph, make_poc()) == "poc:1"
    assert graph.model.nodes["poc:1"].kind == "poc"
    assert graph.model.neighbors("poc:1", "demonstrates") == ["finding:1"]
    assert graph.model.neighbors("poc:1", "for_hypothesis") == ["hypothesis:h1"]
    assert graph.model.neighbors("poc:1", "uses_evidence") == ["evidence:e1"]
    assert graph.history[-1]["type"] == "POC_PERSISTED"
    assert graph.validate() == []


def test_poc_recovery_rejects_finding_rebinding():
    graph = graph_with_finding(); persist_poc(graph, make_poc()); graph.model.nodes["poc:1"].attributes["finding_id"] = "finding:other"
    try:
        rehydrate_persisted_poc(graph, "poc:1")
    except (KeyError, ValueError) as exc:
        assert "finding" in str(exc).lower()
    else:
        raise AssertionError("rebinding a PoC to another finding must fail")


def test_poc_recovery_rejects_missing_lineage_edge():
    graph = graph_with_finding(); persist_poc(graph, make_poc())
    graph.model.edges = [edge for edge in graph.model.edges if not (edge.source == "poc:1" and edge.relation == "uses_evidence")]
    try:
        rehydrate_persisted_poc(graph, "poc:1")
    except ValueError as exc:
        assert "audit state" in str(exc).lower() or "edge" in str(exc).lower()
    else:
        raise AssertionError("missing PoC evidence lineage must fail recovery")


def test_poc_recovery_rejects_detached_evidence():
    graph = graph_with_finding(); persist_poc(graph, make_poc()); graph.model.nodes["poc:1"].attributes["evidence_ids"] = ["evidence:other"]
    try:
        rehydrate_persisted_poc(graph, "poc:1")
    except (KeyError, ValueError) as exc:
        assert "audit state" in str(exc).lower() or "evidence" in str(exc).lower()
    else:
        raise AssertionError("detached PoC evidence must fail recovery")


def test_poc_persistence_rejects_duplicate_identity_without_mutation():
    graph = graph_with_finding(); poc = make_poc(); persist_poc(graph, poc); before = graph.model.export(), graph.export_history()
    try:
        persist_poc(graph, poc)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate PoC identity must be rejected")
    assert (graph.model.export(), graph.export_history()) == before
