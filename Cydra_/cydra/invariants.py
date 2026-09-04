"""Invariant representation, candidate extraction, and evidence-bound verification."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .system_model import SystemModel


class InvariantStatus(str, Enum):
    ASSERTED = "asserted"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"


class VerificationState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class VerificationRole(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    statement: str
    status: InvariantStatus = InvariantStatus.UNKNOWN
    source_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.statement.strip():
            raise ValueError("statement must not be empty")


@dataclass(frozen=True)
class InvariantCandidate:
    """A hypothesis-shaped invariant proposal backed by evidence, not a fact."""
    candidate_id: str
    statement: str
    source_ids: tuple[str, ...]
    confidence: float
    evidence_count: int
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("statement must not be empty")
        if not self.source_ids:
            raise ValueError("candidate requires at least one source")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.evidence_count < 1:
            raise ValueError("evidence_count must be positive")


@dataclass(frozen=True)
class VerificationEvidence:
    """An explicitly classified piece of evidence used to verify a candidate."""
    evidence_id: str
    role: VerificationRole
    confidence: float = 1.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class CandidateVerification:
    candidate_id: str
    state: VerificationState
    evidence_ids: tuple[str, ...]
    supporting_ids: tuple[str, ...]
    contradicting_ids: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        evidence_ids = set(self.evidence_ids)
        if not set(self.supporting_ids).issubset(evidence_ids):
            raise ValueError("supporting evidence IDs must be part of evidence_ids")
        if not set(self.contradicting_ids).issubset(evidence_ids):
            raise ValueError("contradicting evidence IDs must be part of evidence_ids")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.state == VerificationState.SUPPORTED and not self.supporting_ids:
            raise ValueError("supported verification requires supporting evidence")
        if self.state == VerificationState.CONTRADICTED and not self.contradicting_ids:
            raise ValueError("contradicted verification requires contradicting evidence")
        if self.state == VerificationState.UNRESOLVED and (self.supporting_ids or self.contradicting_ids):
            raise ValueError("unresolved verification cannot contain supporting or contradicting evidence")


@dataclass
class InvariantRegistry:
    """Persistent-in-memory registry; storage adapters can be added later."""
    invariants: dict[str, Invariant] = field(default_factory=dict)

    def add(self, invariant: Invariant) -> None:
        if invariant.invariant_id in self.invariants:
            raise ValueError(f"duplicate invariant: {invariant.invariant_id}")
        self.invariants[invariant.invariant_id] = invariant

    def get(self, invariant_id: str) -> Invariant | None:
        return self.invariants.get(invariant_id)

    def by_status(self, status: InvariantStatus) -> list[Invariant]:
        return [i for i in self.invariants.values() if i.status == status]


def candidates_from_system_model(model: SystemModel) -> tuple[InvariantCandidate, ...]:
    """Generate conservative invariant candidates from evidence-backed graph edges."""
    candidates: list[InvariantCandidate] = []
    for edge in sorted(model.edges, key=lambda e: (e.source, e.relation, e.target)):
        if not edge.attributes.get("evidence_backed") or not edge.attributes.get("candidate"):
            continue
        provenance = str(edge.attributes.get("provenance", ""))
        if not provenance:
            continue
        confidence = float(edge.attributes.get("confidence", 0.0))
        source_id = f"{provenance}:{edge.attributes.get('ast_node_id', 'unknown')}"
        candidate_id = f"candidate:{edge.source}:{edge.relation}:{edge.target}"
        if edge.relation in {"precondition", "assertion"} and edge.attributes.get("ast_node_id") is not None:
            candidate_id = f"{candidate_id}:ast:{edge.attributes['ast_node_id']}"
        source_label = model.nodes.get(edge.source).label if edge.source in model.nodes else edge.source
        target_label = model.nodes.get(edge.target).label if edge.target in model.nodes else edge.target
        if edge.relation == "precondition":
            statement = f"successful execution of {source_label} requires {target_label}"
            category = "precondition"
        elif edge.relation == "assertion":
            statement = f"execution of {source_label} asserts {target_label}"
            category = "assertion"
        else:
            statement = f"{source_label} {edge.relation} {target_label}"
            category = "structural_relationship"
        candidates.append(InvariantCandidate(candidate_id, statement, (source_id,), confidence, 1, {"category": category, "relation": edge.relation, "source_edge": f"{edge.source}|{edge.relation}|{edge.target}"}))
    # Preserve compiler-backed update expressions as first-class transition candidates.
    # The expression is evidence about what the implementation computes, not a claim
    # that the computation is correct.
    for edge in sorted(model.edges, key=lambda e: (e.source, e.relation, e.target)):
        if edge.relation != "transition_expression":
            continue
        if not edge.attributes.get("evidence_backed") or not edge.attributes.get("candidate"):
            continue
        expression = edge.attributes.get("expression")
        if not isinstance(expression, str) or not expression:
            continue
        function = model.nodes.get(edge.source)
        state = model.nodes.get(edge.target)
        if function is None or state is None:
            continue
        provenance = str(edge.attributes.get("provenance", ""))
        if not provenance:
            continue
        ast_node_id = edge.attributes.get("ast_node_id", "unknown")
        source_id = f"{provenance}:{ast_node_id}"
        dependency_ids = edge.attributes.get("dependency_ids", [])
        if not isinstance(dependency_ids, list):
            dependency_ids = []
        candidate_id = f"candidate:transition-expression:{edge.source}:{edge.target}:ast:{ast_node_id}"
        candidates.append(InvariantCandidate(
            candidate_id=candidate_id,
            statement=f"execution of {function.label} updates {state.label} using {expression}",
            source_ids=(source_id,),
            confidence=float(edge.attributes.get("confidence", 0.0)),
            evidence_count=1,
            metadata={
                "category": "state_transition_expression",
                "source_function": edge.source,
                "written_state": edge.target,
                "operation": edge.attributes.get("operation"),
                "expression": expression,
                "rhs_expression": edge.attributes.get("rhs_expression"),
                "dependency_ids": dependency_ids,
            },
        ))

    # Derive cross-function state-transition consistency candidates. When multiple
    # independently evidenced functions update the same state variable, the system
    # has a shared transition surface whose combined behavior must be checked for a
    # coherent state relationship. This is deliberately a candidate, not a claim
    # that the updates are inconsistent or vulnerable.
    transition_edges_by_state: dict[str, list] = {}
    for edge in sorted(model.edges, key=lambda e: (e.target, e.source, e.attributes.get("ast_node_id", -1))):
        if edge.relation != "transition_expression":
            continue
        if not edge.attributes.get("evidence_backed") or not edge.attributes.get("candidate"):
            continue
        transition_edges_by_state.setdefault(edge.target, []).append(edge)

    for state_id, transitions in sorted(transition_edges_by_state.items()):
        function_ids = sorted({edge.source for edge in transitions})
        if len(function_ids) < 2:
            continue
        state = model.nodes.get(state_id)
        if state is None:
            continue
        source_ids = tuple(
            f"{edge.attributes.get('provenance', '')}:{edge.attributes.get('ast_node_id', 'unknown')}"
            for edge in transitions
        )
        confidence = min(float(edge.attributes.get("confidence", 0.0)) for edge in transitions)
        candidate_id = f"candidate:cross-function-state-consistency:{state_id}:" + ":".join(function_ids)
        candidates.append(InvariantCandidate(
            candidate_id=candidate_id,
            statement=(
                f"updates to shared state {state.label} across {len(function_ids)} functions "
                f"must preserve a coherent state relationship"
            ),
            source_ids=source_ids,
            confidence=confidence,
            evidence_count=len(transitions),
            metadata={
                "category": "cross_function_state_consistency",
                "shared_state": state_id,
                "function_ids": function_ids,
                "transition_ast_node_ids": [edge.attributes.get("ast_node_id") for edge in transitions],
                "transition_operations": [edge.attributes.get("operation") for edge in transitions],
                "transition_expressions": [edge.attributes.get("expression") for edge in transitions],
            },
        ))

        # If multiple transitions of the same shared state depend on a common
        # state variable, preserve that coupling as a more specific candidate.
        # This is the first useful bridge toward accounting/economic reasoning:
        # the property is discovered from the implementation's dependency graph,
        # not from a hardcoded "vault invariant" catalogue.
        dependency_sets = [
            {int(value) for value in edge.attributes.get("dependency_ids", []) if isinstance(value, int)}
            for edge in transitions
        ]
        common_dependencies = set.intersection(*dependency_sets) if dependency_sets else set()
        # The written state commonly appears on its own RHS (for example
        # ``shares = shares + delta``). That self-reference is a transition
        # baseline, not a cross-function coupling signal.
        try:
            shared_state_ast_id = int(state.attributes.get("ast_node_id"))
        except (TypeError, ValueError):
            shared_state_ast_id = None
        if shared_state_ast_id is not None:
            common_dependencies.discard(shared_state_ast_id)
        for dependency_id in sorted(common_dependencies):
            dependency_state = next(
                (node for node in model.nodes.values() if node.attributes.get("ast_node_id") == dependency_id and node.kind == "state_variable"),
                None,
            )
            if dependency_state is None:
                continue
            pair_id = (
                f"candidate:cross-function-transition-coupling:{state_id}:"
                f"dependency:{dependency_id}:" + ":".join(function_ids)
            )
            pair_sources = tuple(
                f"{edge.attributes.get('provenance', '')}:{edge.attributes.get('ast_node_id', 'unknown')}"
                for edge in transitions
            )
            candidates.append(InvariantCandidate(
                candidate_id=pair_id,
                statement=(
                    f"updates to shared state {state.label} across {len(function_ids)} functions "
                    f"depend on {dependency_state.label}; investigate whether those transitions "
                    f"preserve the same relationship between {state.label} and {dependency_state.label}"
                ),
                source_ids=pair_sources,
                confidence=confidence,
                evidence_count=len(transitions),
                metadata={
                    "category": "cross_function_transition_coupling",
                    "shared_state": state_id,
                    "dependency_state": dependency_state.node_id,
                    "function_ids": function_ids,
                    "transition_ast_node_ids": [edge.attributes.get("ast_node_id") for edge in transitions],
                    "common_dependency_ast_node_id": dependency_id,
                    "transition_expressions": [edge.attributes.get("expression") for edge in transitions],
                },
            ))

    # Derive state-dependency transition candidates from combinations of canonical
    # relationships. These are semantic transition facts, not vulnerability labels:
    # a function reads one state variable while changing another. This gives later
    # reasoning an explicit dependency to test for stale, missing, or inconsistent
    # state relationships without asserting that any defect exists.
    for function_id in sorted(model.nodes):
        function = model.nodes[function_id]
        if function.kind != "function":
            continue
        reads = [
            edge for edge in model.edges
            if edge.source == function_id and edge.relation == "reads"
            and edge.attributes.get("evidence_backed") and edge.attributes.get("candidate")
        ]
        writes = [
            edge for edge in model.edges
            if edge.source == function_id and edge.relation == "writes"
            and edge.attributes.get("evidence_backed") and edge.attributes.get("candidate")
        ]
        for read in reads:
            for write in writes:
                if read.target == write.target:
                    continue
                source_node = model.nodes.get(read.target)
                target_node = model.nodes.get(write.target)
                if source_node is None or target_node is None:
                    continue
                read_source = f"{read.attributes.get('provenance', '')}:{read.attributes.get('ast_node_id', 'unknown')}"
                write_source = f"{write.attributes.get('provenance', '')}:{write.attributes.get('ast_node_id', 'unknown')}"
                candidate_id = (
                    f"candidate:state-dependency:{function_id}:"
                    f"reads:{read.target}:writes:{write.target}"
                )
                confidence = min(
                    float(read.attributes.get("confidence", 0.0)),
                    float(write.attributes.get("confidence", 0.0)),
                )
                candidates.append(InvariantCandidate(
                    candidate_id=candidate_id,
                    statement=(
                        f"execution of {function.label} changes {target_node.label} "
                        f"using information read from {source_node.label}"
                    ),
                    source_ids=(read_source, write_source),
                    confidence=confidence,
                    evidence_count=2,
                    metadata={
                        "category": "state_dependency_transition",
                        "source_function": function_id,
                        "read_state": read.target,
                        "written_state": write.target,
                    },
                ))

    # Derive transition obligations from combinations of canonical relationships.
    # These are still candidates, not verified facts: the graph only proves that the
    # implementation contains the stated precondition/assertion and state write.
    for function_id in sorted(model.nodes):
        function = model.nodes[function_id]
        if function.kind != "function":
            continue
        preconditions = [
            edge for edge in model.edges
            if edge.source == function_id and edge.relation in {"precondition", "assertion"}
            and edge.attributes.get("evidence_backed") and edge.attributes.get("candidate")
        ]
        writes = [
            edge for edge in model.edges
            if edge.source == function_id and edge.relation == "writes"
            and edge.attributes.get("evidence_backed") and edge.attributes.get("candidate")
        ]
        for obligation in preconditions:
            predicate_node = model.nodes.get(obligation.target)
            if predicate_node is None:
                continue
            for write in writes:
                state_node = model.nodes.get(write.target)
                if state_node is None:
                    continue
                obligation_id = (
                    f"candidate:transition:{function_id}:"
                    f"{obligation.relation}:{obligation.target}:writes:{write.target}"
                )
                source_ids = (
                    f"{obligation.attributes.get('provenance', '')}:{obligation.attributes.get('ast_node_id', 'unknown')}",
                    f"{write.attributes.get('provenance', '')}:{write.attributes.get('ast_node_id', 'unknown')}",
                )
                confidence = min(
                    float(obligation.attributes.get("confidence", 0.0)),
                    float(write.attributes.get("confidence", 0.0)),
                )
                predicate_label = predicate_node.label
                state_label = state_node.label
                candidates.append(InvariantCandidate(
                    candidate_id=obligation_id,
                    statement=(
                        f"successful execution of {function.label} requires "
                        f"{predicate_label} before changing {state_label}"
                    ),
                    source_ids=source_ids,
                    confidence=confidence,
                    evidence_count=2,
                    metadata={
                        "category": "transition_obligation",
                        "precondition_relation": obligation.relation,
                        "source_function": function_id,
                        "predicate_node": obligation.target,
                        "written_state": write.target,
                    },
                ))
    return tuple(candidates)


def verify_candidate(candidate: InvariantCandidate, evidence: Iterable[VerificationEvidence]) -> CandidateVerification:
    """Classify a candidate from explicitly labelled evidence without asserting truth.

    Any contradiction dominates support. With neither support nor contradiction, the
    result remains unresolved. This keeps absence of evidence distinct from evidence of
    absence and makes the decision auditable through evidence IDs.
    """
    items = tuple(evidence)
    supporting = tuple(e.evidence_id for e in items if e.role == VerificationRole.SUPPORTS)
    contradicting = tuple(e.evidence_id for e in items if e.role == VerificationRole.CONTRADICTS)
    if contradicting:
        state = VerificationState.CONTRADICTED
    elif supporting:
        state = VerificationState.SUPPORTED
    else:
        state = VerificationState.UNRESOLVED
    relevant = [e.confidence for e in items if e.role != VerificationRole.NEUTRAL]
    confidence = max(relevant) if relevant else 0.0
    return CandidateVerification(
        candidate_id=candidate.candidate_id,
        state=state,
        evidence_ids=tuple(e.evidence_id for e in items),
        supporting_ids=supporting,
        contradicting_ids=contradicting,
        confidence=confidence,
    )


def infer_invariants_from_metadata(records: Iterable[dict[str, str]]) -> InvariantRegistry:
    """Convert explicitly supplied recon metadata into *inferred* invariants."""
    registry = InvariantRegistry()
    for record in records:
        statement = record.get("statement", "").strip()
        invariant_id = record.get("invariant_id", "").strip()
        source_id = record.get("source_id", "").strip()
        if not statement or not invariant_id:
            continue
        registry.add(Invariant(
            invariant_id=invariant_id,
            statement=statement,
            status=InvariantStatus.INFERRED,
            source_ids=(source_id,) if source_id else (),
            confidence=float(record.get("confidence", "0.5")),
        ))
    return registry
