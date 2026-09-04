"""Auditable causal-chain persistence for CYDRA reasoning cycles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .system_model import Edge, Node, SystemModel
from .graph_semantics import validate_graph


@dataclass(frozen=True)
class CausalChain:
    chain_id: str
    hypothesis_id: str
    observation_id: str
    outcome_evidence_id: str
    verification_id: str
    belief_update_id: str
    audit_session_id: str | None = None

    @property
    def evidence_ids(self) -> List[str]:
        """Canonical evidence references carried by this causal trace."""
        return [self.outcome_evidence_id, self.verification_id]


def _require_kind(model: SystemModel, node_id: str, kind: str | Tuple[str, ...]) -> None:
    node = model.nodes.get(node_id)
    if node is None:
        raise KeyError(f"missing causal-chain node: {node_id}")
    allowed = (kind,) if isinstance(kind, str) else kind
    if node.kind not in allowed:
        expected = " or ".join(allowed)
        raise ValueError(f"causal-chain node {node_id} must be kind '{expected}', got '{node.kind}'")


def _validate_audit_session(model: SystemModel, audit_session_id: str | None) -> None:
    if audit_session_id is None:
        return
    if not audit_session_id.strip():
        raise ValueError("causal-chain audit session ID must not be empty")
    session = model.nodes.get(audit_session_id)
    if session is None or session.kind != "audit_session":
        raise KeyError(f"causal-chain audit session missing: {audit_session_id}")


def persist_causal_chain(model: SystemModel, chain: CausalChain) -> None:
    """Persist an explicitly-derived reasoning chain without executing or inferring it.

    The chain is a structural trace, not a causal conclusion. Every reference and
    relationship direction is checked before mutation; the resulting graph must satisfy
    the canonical semantic rules. When supplied, audit-session provenance is part of
    the chain identity so a session-bound finding cannot later substitute a trace from
    another investigation.
    """
    if not chain.chain_id.strip():
        raise ValueError("causal chain ID must not be empty")
    _require_kind(model, chain.hypothesis_id, "hypothesis")
    _require_kind(model, chain.observation_id, "observation")
    _require_kind(model, chain.outcome_evidence_id, "evidence")
    # Existing callers represent the verification anchor either as evidence or as the
    # invariant being verified. Both are valid canonical verification anchors.
    _require_kind(model, chain.verification_id, ("evidence", "invariant"))
    _require_kind(model, chain.belief_update_id, "belief")
    _validate_audit_session(model, chain.audit_session_id)

    if chain.chain_id in model.nodes:
        raise ValueError(f"causal chain already exists: {chain.chain_id}")

    links = (
        (chain.hypothesis_id, "motivates", chain.chain_id),
        (chain.chain_id, "plans", chain.observation_id),
        (chain.observation_id, "produced_evidence", chain.outcome_evidence_id),
        (chain.outcome_evidence_id, "informs", chain.verification_id),
        (chain.verification_id, "updates", chain.belief_update_id),
    )

    attributes = {
        "auditable": True,
        "evidence_ids": list(chain.evidence_ids),
    }
    if chain.audit_session_id is not None:
        attributes["audit_session_id"] = chain.audit_session_id

    prospective_nodes = dict(model.nodes)
    prospective_edges = list(model.edges)
    prospective_nodes[chain.chain_id] = Node(
        chain.chain_id,
        "causal_chain",
        chain.chain_id,
        attributes,
    )
    prospective_edges.extend(
        Edge(source, relation, target, {
            "causal_chain_id": chain.chain_id,
            "evidence_ids": list(chain.evidence_ids),
        })
        for source, relation, target in links
    )
    prospective = SystemModel()
    prospective.nodes = prospective_nodes
    prospective.edges = prospective_edges
    semantic_errors = validate_graph(prospective)
    if semantic_errors:
        raise ValueError(f"causal chain violates graph semantics: {semantic_errors[0]}")

    model.add_node(prospective_nodes[chain.chain_id])
    for source, relation, target in links:
        model.add_edge(Edge(source, relation, target, {
            "causal_chain_id": chain.chain_id,
            "evidence_ids": list(chain.evidence_ids),
        }))
