from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple
from .system_model import SystemModel

RELATION_RULES: Dict[str, Tuple[FrozenSet[str], FrozenSet[str]]] = {
    "supports": (frozenset({"evidence", "causal_chain"}), frozenset({"hypothesis", "evidence"})),
    "contradicts": (frozenset({"evidence", "hypothesis", "causal_chain", "invariant"}), frozenset({"evidence", "hypothesis", "causal_chain", "invariant"})),
    "explains": (frozenset({"causal_chain"}), frozenset({"evidence", "hypothesis"})),
    "derived_from": (frozenset({"evidence"}), frozenset({"observation", "evidence"})),
    "produced": (frozenset({"observation", "build"}), frozenset({"evidence", "audit_session"})),
    "tests": (frozenset({"observation"}), frozenset({"hypothesis"})),
    "targets": (frozenset({"observation"}), frozenset({"invariant"})),
    "tested_by": (frozenset({"hypothesis", "invariant"}), frozenset({"observation"})),
    "informs": (frozenset({"invariant", "evidence"}), frozenset({"hypothesis", "evidence", "invariant"})),
    "verified_by": (frozenset({"invariant"}), frozenset({"evidence"})),
    "contradicted_by": (frozenset({"invariant"}), frozenset({"evidence"})),
    "updates": (frozenset({"observation", "evidence", "invariant", "causal_chain"}), frozenset({"belief"})),
    "updated_to": (frozenset({"hypothesis"}), frozenset({"belief"})),
    "constrains": (frozenset({"invariant"}), frozenset({"asset", "data_flow", "identity"})),
    "crosses": (frozenset({"identity"}), frozenset({"trust_boundary"})),
    "reads": (frozenset({"function"}), frozenset({"state_variable", "data_flow"})),
    "writes": (frozenset({"function"}), frozenset({"state_variable", "data_flow"})),
    "transition_expression": (frozenset({"function"}), frozenset({"state_variable"})),
    "external_call": (frozenset({"function"}), frozenset({"data_flow", "function"})),
    "defined_in": (frozenset({"function", "state_variable"}), frozenset({"contract"})),
    "updated_by": (frozenset({"evidence", "belief", "hypothesis", "causal_chain"}), frozenset({"evidence"})),
    "based_on": (frozenset({"evidence"}), frozenset({"evidence", "observation"})),
    "motivates": (frozenset({"hypothesis"}), frozenset({"causal_chain"})),
    "plans": (frozenset({"causal_chain"}), frozenset({"observation"})),
    "produced_evidence": (frozenset({"observation"}), frozenset({"evidence"})),
    "executes_request": (frozenset({"observation"}), frozenset({"execution_request"})),
    "supported_by": (frozenset({"finding"}), frozenset({"evidence"})),
    "traced_by": (frozenset({"finding"}), frozenset({"causal_chain"})),
    "about": (frozenset({"finding"}), frozenset({"hypothesis"})),
    "derived_from_security_claim": (frozenset({"finding"}), frozenset({"security_claim"})),
    "originates_from": (frozenset({"finding"}), frozenset({"audit_session"})),
    "demonstrates": (frozenset({"poc"}), frozenset({"finding"})),
    "for_hypothesis": (frozenset({"poc"}), frozenset({"hypothesis"})),
    "uses_evidence": (frozenset({"poc"}), frozenset({"evidence"})),
    "derived_from_request": (frozenset({"poc"}), frozenset({"execution_request"})),
    "derived_from_finding": (frozenset({"learning"}), frozenset({"finding"})),
    "contains": (frozenset({"audit_session", "file", "module", "workspace"}), frozenset({"file", "module", "function", "class", "audit_session", "build"})),
    "imports": (frozenset({"module"}), frozenset({"import"})),
    "exposes": (frozenset({"function"}), frozenset({"entry_point"})),
    "uses_authorization": (frozenset({"module"}), frozenset({"authorization"})),
    "asserts_security_predicate": (frozenset({"hypothesis"}), frozenset({"security_predicate"})),
    "grounds_invariant": (frozenset({"security_predicate"}), frozenset({"invariant"})),
    "verified_by_trace": (frozenset({"security_predicate"}), frozenset({"causal_chain"})),
    "competes_with": (frozenset({"hypothesis"}), frozenset({"hypothesis"})),
    "contains_resource": (frozenset({"program", "resource"}), frozenset({"resource"})),
    "references_resource": (frozenset({"program", "resource"}), frozenset({"resource"})),
}

@dataclass(frozen=True)
class SemanticIssue:
    source: str
    relation: str
    target: str
    reason: str


def validate_semantics(model: SystemModel) -> List[SemanticIssue]:
    issues: List[SemanticIssue] = []
    for edge in model.edges:
        source = model.nodes.get(edge.source)
        target = model.nodes.get(edge.target)
        if source is None or target is None:
            continue
        rule = RELATION_RULES.get(edge.relation)
        if rule is None:
            issues.append(SemanticIssue(edge.source, edge.relation, edge.target, "unknown relationship type"))
            continue
        allowed_sources, allowed_targets = rule
        if source.kind not in allowed_sources:
            issues.append(SemanticIssue(edge.source, edge.relation, edge.target, f"source kind '{source.kind}' is not allowed"))
        if target.kind not in allowed_targets:
            issues.append(SemanticIssue(edge.source, edge.relation, edge.target, f"target kind '{target.kind}' is not allowed"))
    return issues


def validate_graph(model: SystemModel) -> List[str]:
    errors = list(model.validate())
    errors.extend(f"{i.source} -[{i.relation}]-> {i.target}: {i.reason}" for i in validate_semantics(model))
    return errors


def contradiction_pairs(model: SystemModel) -> List[Tuple[str, str]]:
    pairs = set()
    for edge in model.edges:
        if edge.relation == "contradicts":
            pairs.add(tuple(sorted((edge.source, edge.target))))
    return sorted(pairs)
