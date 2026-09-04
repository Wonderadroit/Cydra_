"""Canonical persistence and recovery boundary for finding PoCs."""
from __future__ import annotations

from .causal_reconstruction import reconstruct_causal_chain
from .finding_recovery import rehydrate_persisted_finding
from .graph_semantics import validate_graph
from .poc import POCArtifact
from .reasoning_graph import ReasoningGraph
from .system_model import Edge, Node, SystemModel


def _require_poc_node(graph: ReasoningGraph, poc_id: str) -> Node:
    node = graph.model.nodes.get(poc_id)
    if node is None:
        raise KeyError(f"persisted PoC missing: {poc_id}")
    if node.kind != "poc":
        raise ValueError(f"node is not a PoC: {poc_id}")
    if node.attributes.get("persisted") is not True:
        raise ValueError(f"PoC is not marked as canonical persisted state: {poc_id}")
    return node


def _validate_poc(graph: ReasoningGraph, poc: POCArtifact) -> None:
    if not poc.poc_id or not poc.poc_id.strip():
        raise ValueError("PoC requires a canonical PoC identity")
    if not poc.finding_id:
        raise ValueError("PoC requires a finding identity")

    finding = rehydrate_persisted_finding(graph, poc.finding_id)
    trace = reconstruct_causal_chain(graph.model, finding.causal_chain_id)
    errors = poc.validation_errors(
        finding_id=finding.finding_id,
        hypothesis_id=finding.hypothesis_id,
        trace_evidence_ids=set(trace.evidence_ids),
    )
    if errors:
        raise ValueError(errors[0])

    if poc.execution_request_id:
        request = graph.model.nodes.get(poc.execution_request_id)
        if request is None or request.kind != "execution_request":
            raise KeyError(f"PoC execution request missing: {poc.execution_request_id}")
        if not any(
            edge.source == trace.observation_id
            and edge.relation == "executes_request"
            and edge.target == poc.execution_request_id
            for edge in graph.model.edges
        ):
            raise ValueError("PoC execution request is not canonical for the causal observation")

    graph_errors = validate_graph(graph.model)
    if graph_errors:
        raise ValueError(f"canonical graph is invalid: {graph_errors[0]}")
    audit_errors = graph.verify_history_integrity()
    if audit_errors:
        raise ValueError("reasoning audit history is invalid")


def persist_poc(graph: ReasoningGraph, poc: POCArtifact) -> str:
    """Persist a PoC only after canonical finding/trace validation."""
    _validate_poc(graph, poc)
    assert poc.poc_id is not None
    if poc.poc_id in graph.model.nodes:
        raise ValueError(f"PoC already exists: {poc.poc_id}")

    node = Node(
        poc.poc_id,
        "poc",
        f"PoC for {poc.finding_id}",
        {"persisted": True, **poc.as_dict()},
    )
    prospective_nodes = dict(graph.model.nodes)
    prospective_edges = list(graph.model.edges)
    prospective_nodes[node.node_id] = node
    prospective_edges.extend([
        Edge(poc.poc_id, "demonstrates", poc.finding_id, {"provenance": "poc_persistence"}),
        Edge(poc.poc_id, "for_hypothesis", poc.hypothesis_id, {"provenance": "poc_persistence"}),
    ])
    prospective_edges.extend(
        Edge(poc.poc_id, "uses_evidence", evidence_id, {"provenance": "poc_persistence"})
        for evidence_id in poc.evidence_ids
    )
    if poc.execution_request_id:
        prospective_edges.append(
            Edge(poc.poc_id, "derived_from_request", poc.execution_request_id, {"provenance": "poc_persistence"})
        )

    prospective = SystemModel()
    prospective.nodes = prospective_nodes
    prospective.edges = prospective_edges
    semantic_errors = validate_graph(prospective)
    if semantic_errors:
        raise ValueError(f"PoC violates graph semantics: {semantic_errors[0]}")

    graph.model.add_node(node)
    for edge in prospective_edges[len(graph.model.edges):]:
        graph.model.add_edge(edge)
    graph._event(
        "POC_PERSISTED",
        poc=poc.poc_id,
        finding=poc.finding_id,
        hypothesis=poc.hypothesis_id,
        evidence=list(poc.evidence_ids),
        execution_request=poc.execution_request_id,
    )
    return poc.poc_id


def rehydrate_persisted_poc(graph: ReasoningGraph, poc_id: str) -> POCArtifact:
    """Recover a PoC only from canonical persisted state and its lineage."""
    node = _require_poc_node(graph, poc_id)
    attrs = node.attributes
    counterexample_data = attrs.get("counterexample")
    if not isinstance(counterexample_data, dict):
        raise ValueError("persisted PoC counterexample is malformed")
    if counterexample_data.get("type") != "COUNTEREXAMPLE":
        raise ValueError("persisted PoC counterexample type is invalid")

    from .counterexample import Counterexample

    try:
        counterexample = Counterexample(
            test_name=counterexample_data["test_name"],
            input_data=dict(counterexample_data.get("input_data", {})),
            trace=list(counterexample_data["trace"]),
            invariant=counterexample_data.get("invariant", ""),
            expected=counterexample_data.get("expected"),
            actual=counterexample_data.get("actual"),
            reproducible=bool(counterexample_data.get("reproducible", False)),
        )
        poc = POCArtifact(
            hypothesis_id=attrs["hypothesis_id"],
            counterexample=counterexample,
            expected_violation=attrs["expected_violation"],
            reproducibility_notes=attrs.get("reproducibility_notes", ""),
            finding_id=attrs.get("finding_id"),
            evidence_ids=tuple(attrs.get("evidence_ids", [])),
            execution_request_id=attrs.get("execution_request_id"),
            poc_id=attrs.get("poc_id"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"persisted PoC is malformed: {exc}") from exc

    if poc.poc_id != poc_id:
        raise ValueError("persisted PoC ID does not match canonical node identity")
    _validate_poc(graph, poc)

    actual_edges = {(e.source, e.relation, e.target) for e in graph.model.edges}
    required = {
        (poc_id, "demonstrates", poc.finding_id),
        (poc_id, "for_hypothesis", poc.hypothesis_id),
    }
    required.update((poc_id, "uses_evidence", evidence_id) for evidence_id in poc.evidence_ids)
    if poc.execution_request_id:
        required.add((poc_id, "derived_from_request", poc.execution_request_id))
    missing = sorted(required - actual_edges)
    if missing:
        raise ValueError(f"persisted PoC is missing canonical graph edge: {missing[0]}")
    return poc


def validate_persisted_pocs(graph: ReasoningGraph) -> list[str]:
    """Return PoC recovery errors without mutating canonical state."""
    errors: list[str] = []
    for node_id, node in sorted(graph.model.nodes.items()):
        if node.kind != "poc" or node.attributes.get("persisted") is not True:
            continue
        try:
            rehydrate_persisted_poc(graph, node_id)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{node_id}: {exc}")
    return errors
