"""Canonical graph persistence and recovery for finding-derived learning."""
from __future__ import annotations

from .finding import Finding
from .finding_recovery import rehydrate_persisted_finding
from .graph_semantics import validate_graph
from .learning import FindingLearningContribution, LearningLimits, LearningRecord, LearningStore
from .reasoning_graph import ReasoningGraph
from .system_model import Edge, Node, SystemModel


def _validate_record(record: LearningRecord) -> None:
    if not record.learning_id:
        raise ValueError("learning record requires a deterministic identity")


def persist_learning_records(
    graph: ReasoningGraph,
    store: LearningStore,
    records: tuple[LearningRecord, ...],
) -> tuple[str, ...]:
    """Persist learning only when its source finding and store state are canonical."""
    if not records:
        return ()
    limits = store.export()["limits"]
    for record in records:
        _validate_record(record)
        rehydrate_persisted_finding(graph, record.finding_id)
        canonical = store.records.get(record.learning_id)
        if canonical != record:
            raise ValueError("learning store must contain the exact canonical record before graph persistence")

    prospective_nodes = dict(graph.model.nodes)
    prospective_edges = list(graph.model.edges)
    new_ids: list[str] = []
    for record in records:
        node_id = f"learning:{record.learning_id}"
        attrs = {
            "persisted": True,
            "learning_id": record.learning_id,
            "finding_id": record.finding_id,
            "category": record.category,
            "key": record.key,
            "value": record.value,
            "confidence": record.confidence,
            "limits": limits,
        }
        existing = prospective_nodes.get(node_id)
        lineage = any(
            edge.source == node_id
            and edge.relation == "derived_from_finding"
            and edge.target == record.finding_id
            for edge in prospective_edges
        )
        if existing is None:
            prospective_nodes[node_id] = Node(node_id, "learning", record.category, attrs)
            prospective_edges.append(
                Edge(node_id, "derived_from_finding", record.finding_id, {"provenance": "learning_persistence"})
            )
            new_ids.append(node_id)
        elif existing.kind != "learning" or existing.attributes != attrs:
            raise ValueError("learning identity conflicts with canonical persisted state")
        elif not lineage:
            raise ValueError("existing learning is missing canonical finding lineage")

    prospective = SystemModel()
    prospective.nodes = prospective_nodes
    prospective.edges = prospective_edges
    errors = validate_graph(prospective)
    if errors:
        raise ValueError(f"learning violates graph semantics: {errors[0]}")

    for node_id in new_ids:
        graph.model.add_node(prospective_nodes[node_id])
        graph.model.add_edge(next(edge for edge in prospective_edges if edge.source == node_id))
    for record in records:
        graph._event(
            "LEARNING_PERSISTED",
            learning=f"learning:{record.learning_id}",
            finding=record.finding_id,
            category=record.category,
            confidence=record.confidence,
        )
    return tuple(f"learning:{record.learning_id}" for record in records)


def persist_verified_finding_learning(
    graph: ReasoningGraph,
    store: LearningStore,
    finding: Finding,
    contribution: FindingLearningContribution,
) -> tuple[str, ...]:
    """Canonical post-gate learning transaction for one verified finding."""
    rehydrate_persisted_finding(graph, finding.finding_id)
    records = contribution.records_for(finding.finding_id)
    staged = LearningStore(limits=store.limits, records=dict(store.records))
    staged.learn_many(records)
    persisted_ids = persist_learning_records(graph, staged, records)
    store.records = staged.records
    return persisted_ids


def rehydrate_persisted_learning(
    graph: ReasoningGraph,
    limits: LearningLimits,
) -> LearningStore:
    """Recover all canonical learning nodes using externally supplied limits."""
    store = LearningStore(limits=limits)
    nodes = [
        node for node in graph.model.nodes.values()
        if node.kind == "learning" and node.attributes.get("persisted") is True
    ]
    for node in sorted(nodes, key=lambda item: item.node_id):
        attrs = node.attributes
        try:
            record = LearningRecord(
                finding_id=attrs["finding_id"],
                category=attrs["category"],
                key=attrs["key"],
                value=attrs["value"],
                confidence=attrs["confidence"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"persisted learning is malformed: {exc}") from exc
        if attrs.get("learning_id") != record.learning_id or node.node_id != f"learning:{record.learning_id}":
            raise ValueError("persisted learning identity is not canonical")
        if attrs.get("limits") != store.export()["limits"]:
            raise ValueError("persisted learning limits do not match externally supplied limits")
        finding = rehydrate_persisted_finding(graph, record.finding_id)
        if finding.finding_id != record.finding_id:
            raise ValueError("learning finding provenance is not canonical")
        if not any(
            edge.source == node.node_id
            and edge.relation == "derived_from_finding"
            and edge.target == record.finding_id
            for edge in graph.model.edges
        ):
            raise ValueError("persisted learning is missing canonical finding lineage")
        store.learn(record)

    errors = validate_graph(graph.model)
    if errors:
        raise ValueError(f"canonical graph is invalid: {errors[0]}")
    audit_errors = graph.verify_history_integrity()
    if audit_errors:
        raise ValueError("reasoning audit history is invalid")
    return store
