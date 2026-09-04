"""Bind authorized execution results to canonical causal reasoning state.

This adapter is deliberately semantic-neutral. An execution receipt proves what the
adapter observed, not what the observation means for a hypothesis. A caller must
supply the outcome interpreter that maps the concrete result to one of the planned
observation outcomes and an explicit evidentiary polarity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from .causal_chain import CausalChain, persist_causal_chain
from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
from .evidence import Evidence, EvidenceKind, Provenance
from .foundry import result_to_evidence
from .planner import Hypothesis, Observation
from .reasoning_graph import GraphUpdate, ReasoningGraph
from .updater import EvidencePolarity


OutcomeInterpreter = Callable[[object, Observation, Sequence[Hypothesis]], tuple[str, Mapping[str, EvidencePolarity]]]


@dataclass(frozen=True)
class CausalBinding:
    """Immutable interpretation captured once for one execution lifecycle."""
    execution_id: str
    request_digest: str
    evidence_id: str
    semantic_outcome: str
    polarity: Mapping[str, EvidencePolarity]
    causal_chain_id: str | None
    hypothesis_id: str | None


class ExecutionCausalEvidenceAdapter:
    """Translate an authorized result into explicit evidence and causal state."""

    def __init__(self, graph: ReasoningGraph, interpreter: OutcomeInterpreter) -> None:
        if not isinstance(graph, ReasoningGraph):
            raise TypeError("execution causal adapter requires the canonical ReasoningGraph")
        if not callable(interpreter):
            raise TypeError("execution causal adapter requires an explicit outcome interpreter")
        self.graph = graph
        self.interpreter = interpreter
        self._bindings: dict[str, CausalBinding] = {}
        self._finalized_execution_ids: set[str] = set()

    def _primary_hypothesis(self, observation: Observation, hypotheses: Sequence[Hypothesis]) -> Hypothesis | None:
        matches = []
        for hypothesis in hypotheses:
            node = self.graph.model.nodes.get(hypothesis.hypothesis_id)
            claim = node.attributes.get("security_claim") if node is not None and node.kind == "hypothesis" else None
            if isinstance(claim, Mapping) and observation.name in hypothesis.predictions:
                matches.append(hypothesis)
        if len(matches) > 1:
            security = [item for item in matches if self.graph.model.nodes[item.hypothesis_id].attributes.get("security_claim", {}).get("claim_kind") == "security_hypothesis"]
            if len(security) != 1:
                raise ValueError("observation maps to multiple security hypotheses")
            return security[0]
        return matches[0] if matches else None

    def _planned_identity(self, observation: Observation) -> tuple[str | None, str | None]:
        node = self.graph.model.nodes.get(f"observation:{observation.name}")
        if node is None:
            raise KeyError(f"planned observation missing from canonical graph: {observation.name}")
        return node.attributes.get("execution_id"), node.attributes.get("execution_request_digest")

    def bind(self, result, observation: Observation, hypotheses: Sequence[Hypothesis]):
        if not result.execution_id:
            raise ValueError("execution result must have an execution identity")
        if result.execution_id in self._finalized_execution_ids:
            raise ValueError("execution result has already been causally bound")
        planned_execution_id, planned_digest = self._planned_identity(observation)
        if planned_execution_id and planned_execution_id != result.execution_id:
            raise ValueError("execution result identity does not match the planned observation")
        if planned_digest and planned_digest != (result.request_digest or ""):
            raise ValueError("execution result request digest does not match the planned observation")
        if result.execution_id in self._bindings:
            raise ValueError("execution result has already been causally bound")
        semantic_outcome, polarity = self.interpreter(result, observation, hypotheses)
        if not isinstance(semantic_outcome, str) or semantic_outcome not in observation.outcomes:
            raise ValueError("outcome interpreter returned an outcome not declared by the observation")
        if not isinstance(polarity, Mapping):
            raise TypeError("outcome interpreter must return an explicit polarity mapping")
        normalized = dict(polarity)
        for hypothesis_id, value in normalized.items():
            if not isinstance(hypothesis_id, str) or not isinstance(value, EvidencePolarity):
                raise ValueError("causal evidence polarity must map hypothesis IDs to EvidencePolarity")
        primary = self._primary_hypothesis(observation, hypotheses)
        causal_chain_id = f"causal:execution:{result.execution_id}" if primary is not None else None
        binding = CausalBinding(result.execution_id, result.request_digest or "", f"execution-observation:{result.execution_id}", semantic_outcome, normalized, causal_chain_id, primary.hypothesis_id if primary is not None else None)
        self._bindings[result.execution_id] = binding
        return binding.evidence_id, binding.polarity, binding.causal_chain_id

    def finalize(self, result, observation: Observation, hypotheses: Sequence[Hypothesis], update: GraphUpdate) -> CausalVerificationState | None:
        binding = self._bindings.pop(result.execution_id, None)
        if binding is None:
            raise ValueError("causal finalization requires a prior bind for the exact execution result")
        if binding.request_digest != (result.request_digest or ""):
            raise ValueError("execution result request digest changed after causal binding")
        if f"evidence:{binding.evidence_id}" != update.evidence_node_id:
            raise ValueError("canonical outcome evidence does not match the causal binding")
        if binding.causal_chain_id is None or binding.hypothesis_id is None:
            return None
        primary = next((h for h in hypotheses if h.hypothesis_id == binding.hypothesis_id), None)
        if primary is None:
            raise ValueError("causal finalization lost the selected security hypothesis")
        if update.causal_chain_node_id is not None:
            raise ValueError("execution causal adapter requires ownership of causal-chain persistence")
        belief_ids = [node_id for node_id in update.belief_node_ids if self.graph.model.nodes.get(node_id) is not None and self.graph.model.nodes[node_id].attributes.get("hypothesis_id") == primary.hypothesis_id]
        if len(belief_ids) != 1:
            raise ValueError("causal completion requires exactly one belief update for the selected hypothesis")
        if not update.evidence_node_id:
            raise ValueError("causal completion requires canonical outcome evidence")
        verification = result_to_evidence(result, f"causal-verification:{result.execution_id}", authorization_id=getattr(result, "authorization_id", None), scope_status=getattr(result, "scope_status", None))
        acquired_at = getattr(result, "finished_at", None) or getattr(result, "started_at", None)
        timestamp = datetime.fromisoformat(acquired_at) if acquired_at else datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("causal verification timestamp must be timezone-aware")
        verification = Evidence(
            evidence_id=verification.evidence_id, kind=EvidenceKind.TEST_RESULT,
            value={**dict(verification.value), "semantic_outcome": binding.semantic_outcome, "verification_role": "causal_verification"},
            provenance=Provenance(source=f"execution-verification:{result.execution_id}", acquired_at=timestamp, collector="execution_causal_adapter", scope_status=verification.provenance.scope_status, details={"authorization_id": verification.provenance.details.get("authorization_id", ""), "execution_id": result.execution_id, "request_digest": result.request_digest or "", "semantic_outcome": binding.semantic_outcome}),
            interpretation=f"Explicit execution interpretation: {binding.semantic_outcome}", confidence=1.0,
        )
        verification_node_id = self.graph.add_evidence(verification)
        primary_polarity = binding.polarity.get(primary.hypothesis_id)
        if primary_polarity is EvidencePolarity.SUPPORTS:
            self.graph.model.connect(verification_node_id, "supports", primary.hypothesis_id, provenance="explicit_execution_verification", semantic_outcome=binding.semantic_outcome)
            self.graph.model.connect(update.evidence_node_id, "supports", primary.hypothesis_id, provenance="explicit_execution_observation", semantic_outcome=binding.semantic_outcome)
        persist_causal_chain(self.graph.model, CausalChain(chain_id=binding.causal_chain_id, hypothesis_id=primary.hypothesis_id, observation_id=update.observation_node_id, outcome_evidence_id=update.evidence_node_id, verification_id=verification_node_id, belief_update_id=belief_ids[0]))
        verification_result = verify_persisted_causal_chain(self.graph.model, binding.causal_chain_id)
        if verification_result.state is CausalVerificationState.VERIFIED:
            node = self.graph.model.nodes[primary.hypothesis_id]
            claim = node.attributes.get("security_claim")
            if isinstance(claim, Mapping):
                updated_claim = dict(claim)
                updated_claim["causal_chain_id"] = binding.causal_chain_id
                updated_claim["evidence_ids"] = list(verification_result.evidence_ids)
                self.graph.model.nodes[primary.hypothesis_id] = type(node)(node.node_id, node.kind, node.label, {**node.attributes, "security_claim": updated_claim})
        self.graph._event("CAUSAL_CHAIN_FINALIZED", chain_id=binding.causal_chain_id, hypothesis_id=primary.hypothesis_id, observation_id=update.observation_node_id, evidence_ids=list(verification_result.evidence_ids), verification_state=verification_result.state.value)
        self._finalized_execution_ids.add(result.execution_id)
        return verification_result.state
