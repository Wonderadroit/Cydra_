from dataclasses import dataclass, field
from typing import Dict, List
import json

from .ast_dataflow import SemanticRelationshipEvidence

KINDS = frozenset({"asset", "identity", "trust_boundary", "data_flow", "invariant", "evidence", "hypothesis", "observation", "causal_chain", "belief", "finding", "security_claim", "security_predicate", "contract", "function", "state_variable", "file", "module", "class", "import", "entry_point", "authorization", "audit_session", "execution_request", "execution_result", "poc", "learning", "program", "resource", "workspace", "build"})

@dataclass(frozen=True)
class Node:
    node_id: str
    kind: str
    label: str
    attributes: Dict[str, object] = field(default_factory=dict)

@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    attributes: Dict[str, object] = field(default_factory=dict)

class SystemModel:
    SCHEMA_VERSION = "1.22.0"
    KINDS = KINDS

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    def add_node(self, node: Node) -> None:
        if node.kind not in KINDS:
            raise ValueError(f"unsupported node kind: {node.kind}")
        if not node.node_id.strip() or not node.label.strip():
            raise ValueError("node_id and label cannot be empty")
        existing = self.nodes.get(node.node_id)
        if existing is None:
            self.nodes[node.node_id] = node
            return
        if existing != node:
            raise ValueError(f"node ID conflicts with existing canonical node: {node.node_id}")

    def update_node_attributes(self, node_id: str, updates: Dict[str, object]) -> None:
        existing = self.nodes.get(node_id)
        if existing is None:
            raise KeyError(f"missing canonical node: {node_id}")
        if not isinstance(updates, dict):
            raise TypeError("node attribute updates must be a mapping")
        attributes = dict(existing.attributes)
        attributes.update(updates)
        self.nodes[node_id] = Node(existing.node_id, existing.kind, existing.label, attributes)

    def add_edge(self, edge: Edge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise KeyError("both edge endpoints must exist")
        if edge.relation == "executes_request":
            source = self.nodes[edge.source]
            target = self.nodes[edge.target]
            if source.kind != "observation" or target.kind != "execution_request":
                raise ValueError("executes_request must connect an observation to an execution_request")
            conflicting = [existing for existing in self.edges if existing.relation == "executes_request" and existing.target == edge.target and existing.source != edge.source]
            if conflicting:
                raise ValueError("execution request is already bound to a different canonical observation")
        if edge not in self.edges:
            self.edges.append(edge)

    def connect(self, source: str, relation: str, target: str, **attributes) -> None:
        self.add_edge(Edge(source, relation, target, attributes))

    @staticmethod
    def _ast_node_identity(kind: str, contract: str, label: str, ast_node_id: int | None) -> str:
        return f"{kind}:{contract}:ast:{ast_node_id}" if ast_node_id is not None else f"{kind}:{contract}:{label}"

    def add_ast_evidence(self, evidence: SemanticRelationshipEvidence) -> Edge:
        function_id = self._ast_node_identity("function", evidence.contract, evidence.function, evidence.function_ast_node_id)
        target_kind = "state_variable" if evidence.relation in {"reads", "writes", "transition_expression"} else "data_flow"
        target_id = self._ast_node_identity(target_kind, evidence.contract, evidence.target, evidence.target_ast_node_id)
        function_attributes = {"ast_node_id": evidence.function_ast_node_id, "identity_status": "compiler_declaration" if evidence.function_ast_node_id is not None else "unknown", "provenance": evidence.source}
        target_attributes = {"ast_node_id": evidence.target_ast_node_id, "identity_status": "compiler_declaration" if evidence.target_ast_node_id is not None else "unknown", "provenance": evidence.source}
        if function_id not in self.nodes:
            self.add_node(Node(function_id, "function", evidence.function, function_attributes))
        if target_id not in self.nodes:
            self.add_node(Node(target_id, target_kind, evidence.target, target_attributes))
        attributes = {"confidence": evidence.confidence, "provenance": evidence.source, "ast_node_id": evidence.ast_node_id, "source_location": list(evidence.source_location) if evidence.source_location is not None else None, "function_ast_node_id": evidence.function_ast_node_id, "target_ast_node_id": evidence.target_ast_node_id, "evidence_backed": True, "candidate": True, **(evidence.metadata or {})}
        edge = Edge(function_id, evidence.relation, target_id, attributes)
        self.add_edge(edge)
        return edge

    def project_ast_evidence(self, evidence_items: List[SemanticRelationshipEvidence]) -> List[Edge]:
        return [self.add_ast_evidence(item) for item in evidence_items]

    def neighbors(self, node_id: str, relation: str | None = None) -> List[str]:
        return sorted(e.target for e in self.edges if e.source == node_id and (relation is None or e.relation == relation))

    def _validate_finding_node(self, node: Node) -> list[str]:
        errors: list[str] = []
        attributes = node.attributes
        if not attributes.get("persisted"):
            return errors
        required = ("finding_id", "title", "summary", "severity", "impact", "affected_components", "evidence_ids", "hypothesis_id")
        missing = [name for name in required if name not in attributes]
        if missing:
            errors.append(f"persisted finding missing required fields: {', '.join(missing)}")
            return errors
        if attributes.get("finding_id") != node.node_id:
            errors.append(f"persisted finding identity conflicts with node ID: {node.node_id}")
        if attributes.get("title") != node.label:
            errors.append(f"persisted finding title conflicts with node label: {node.node_id}")
        impact = attributes.get("impact")
        if not isinstance(impact, dict):
            errors.append(f"persisted finding impact is not a mapping: {node.node_id}")
            return errors
        impact_level = impact.get("level")
        severity = attributes.get("severity")
        canonical_levels = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}
        if severity not in canonical_levels:
            errors.append(f"persisted finding severity is not canonical: {node.node_id}")
        if impact_level not in canonical_levels:
            errors.append(f"persisted finding impact level is not canonical: {node.node_id}")
        elif impact_level == "UNKNOWN":
            errors.append(f"persisted finding impact level is unresolved: {node.node_id}")
        elif severity != impact_level:
            errors.append(f"persisted finding severity does not match impact level: {node.node_id}")
        if not isinstance(impact.get("consequence"), str) or not impact.get("consequence", "").strip():
            errors.append(f"persisted finding impact consequence is empty: {node.node_id}")
        evidence_ids = attributes.get("evidence_ids")
        impact_evidence_ids = impact.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
            errors.append(f"persisted finding evidence IDs are malformed: {node.node_id}")
        if not isinstance(impact_evidence_ids, list) or not all(isinstance(item, str) for item in impact_evidence_ids):
            errors.append(f"persisted finding impact evidence IDs are malformed: {node.node_id}")
        if attributes.get("canonical_evidence_ids") != evidence_ids:
            errors.append(f"persisted finding canonical_evidence_ids conflicts with report data: {node.node_id}")
        if attributes.get("canonical_impact_evidence_ids") != impact_evidence_ids:
            errors.append(f"persisted finding canonical_impact_evidence_ids conflicts with report data: {node.node_id}")
        if attributes.get("canonical_hypothesis_id") != attributes.get("hypothesis_id"):
            errors.append(f"persisted finding canonical_hypothesis_id conflicts with report data: {node.node_id}")
        if attributes.get("canonical_causal_chain_id") != attributes.get("causal_chain_id"):
            errors.append(f"persisted finding canonical_causal_chain_id conflicts with report data: {node.node_id}")
        if attributes.get("canonical_audit_session_id") != attributes.get("audit_session_id"):
            errors.append(f"persisted finding canonical_audit_session_id conflicts with report data: {node.node_id}")
        return errors

    def validate(self) -> List[str]:
        errors = []
        for node_id, node in self.nodes.items():
            if node_id != node.node_id:
                errors.append(f"node key mismatch: {node_id}")
            if node.kind not in KINDS:
                errors.append(f"unsupported node kind: {node.node_id}")
            if not node.label.strip():
                errors.append(f"empty label: {node.node_id}")
            if node.kind == "finding":
                errors.extend(self._validate_finding_node(node))
            if node.kind == "execution_request":
                required = ("execution_id", "adapter", "target", "command", "project_fingerprint", "authorization_id", "scope_status", "digest")
                for field_name in required:
                    if field_name not in node.attributes:
                        errors.append(f"execution request missing {field_name}: {node.node_id}")
            if node.kind == "execution_result":
                required = ("execution_id", "request_digest", "adapter", "payload", "fingerprint")
                for field_name in required:
                    if field_name not in node.attributes:
                        errors.append(f"execution result missing {field_name}: {node.node_id}")
                request_digest = node.attributes.get("request_digest")
                request = self.nodes.get(f"execution_request:{request_digest}") if request_digest else None
                if request is None or request.kind != "execution_request":
                    errors.append(f"execution result is not bound to a canonical execution request: {node.node_id}")
                else:
                    if node.attributes.get("execution_id") != request.attributes.get("execution_id"):
                        errors.append(f"execution result execution identity conflicts with request: {node.node_id}")
                    if node.attributes.get("adapter") != request.attributes.get("adapter"):
                        errors.append(f"execution result adapter conflicts with request: {node.node_id}")
                    payload = node.attributes.get("payload")
                    if isinstance(payload, dict):
                        if payload.get("execution_id") != node.attributes.get("execution_id"):
                            errors.append(f"execution result payload execution identity conflicts with receipt: {node.node_id}")
                        if payload.get("request_digest") != request_digest:
                            errors.append(f"execution result payload request digest conflicts with receipt: {node.node_id}")
        request_sources = {}
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"missing source: {edge.source}")
            if edge.target not in self.nodes:
                errors.append(f"missing target: {edge.target}")
            if edge.relation == "executes_request":
                if self.nodes.get(edge.source, Node("", "", "")).kind != "observation":
                    errors.append(f"execution request edge source is not observation: {edge.source}")
                if self.nodes.get(edge.target, Node("", "", "")).kind != "execution_request":
                    errors.append(f"execution request edge target is not execution_request: {edge.target}")
                previous = request_sources.get(edge.target)
                if previous is not None and previous != edge.source:
                    errors.append(f"execution request has multiple observation bindings: {edge.target}")
                request_sources[edge.target] = edge.source
        return errors

    def export(self) -> dict:
        return {"schema_version": self.SCHEMA_VERSION, "nodes": [{"id": n.node_id, "kind": n.kind, "label": n.label, "attributes": n.attributes} for n in sorted(self.nodes.values(), key=lambda x: x.node_id)], "edges": [{"source": e.source, "relation": e.relation, "target": e.target, "attributes": e.attributes} for e in sorted(self.edges, key=lambda x: (x.source, x.relation, x.target))]}

    @classmethod
    def from_dict(cls, payload: dict):
        model = cls()
        for n in payload.get("nodes", []):
            model.add_node(Node(n["id"], n["kind"], n["label"], n.get("attributes", {})))
        for e in payload.get("edges", []):
            model.add_edge(Edge(e["source"], e["relation"], e["target"], e.get("attributes", {})))
        errors = model.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return model

    @classmethod
    def load(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return cls.from_dict(payload)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.export(), f, indent=2, sort_keys=True)
