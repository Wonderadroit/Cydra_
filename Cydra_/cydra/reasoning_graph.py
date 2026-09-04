from dataclasses import dataclass
from typing import List, Optional, Iterable, Mapping
import hashlib
import json
import time
import uuid

from .evidence import Evidence
from .planner import Hypothesis, Observation, Plan
from .updater import EvidencePolarity, UpdateResult
from .graph_semantics import validate_graph
from .invariants import CandidateVerification, VerificationState
from .system_model import Node, SystemModel
from ._planner_binding_helpers import validate_competing_pair


@dataclass(frozen=True)
class GraphUpdate:
    observation_node_id: str
    belief_node_ids: List[str]
    evidence_node_id: Optional[str]
    causal_chain_node_id: Optional[str]


class ReasoningGraph:
    AUDIT_GENESIS = "GENESIS"
    AUDIT_ALGORITHM = "sha256"
    SERIALIZATION_VERSION = "1.0"

    def __init__(self, model: Optional[SystemModel] = None):
        self.model = model or SystemModel()
        self.history: List[dict] = []

    @classmethod
    def _audit_digest(cls, event: dict) -> str:
        payload = {key: value for key, value in event.items() if key != "event_hash"}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

    @classmethod
    def _state_digest(cls, model: SystemModel) -> str:
        payload = json.dumps(model.export(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _event(self, event_type: str, **payload) -> dict:
        sequence = len(self.history)
        previous_hash = self.history[-1].get("event_hash", self.AUDIT_GENESIS) if self.history else self.AUDIT_GENESIS
        event = {
            "event_id": str(uuid.uuid4()),
            "sequence": sequence,
            "timestamp": time.time(),
            "type": event_type,
            "previous_hash": previous_hash,
            "state_digest": self._state_digest(self.model),
            **payload,
        }
        event["event_hash"] = self._audit_digest(event)
        self.history.append(event)
        return event

    def verify_history_integrity(self) -> List[str]:
        errors = []
        previous_hash = self.AUDIT_GENESIS
        for expected_sequence, event in enumerate(self.history):
            if not isinstance(event, dict):
                errors.append(f"audit event is not a mapping at sequence {expected_sequence}")
                continue
            if event.get("sequence") != expected_sequence:
                errors.append(f"audit sequence mismatch at index {expected_sequence}")
            if event.get("previous_hash") != previous_hash:
                errors.append(f"audit previous-hash mismatch at sequence {expected_sequence}")
            stored_hash = event.get("event_hash")
            if not stored_hash:
                errors.append(f"audit event hash missing at sequence {expected_sequence}")
            elif stored_hash != self._audit_digest(event):
                errors.append(f"audit event hash mismatch at sequence {expected_sequence}")
            previous_hash = stored_hash or previous_hash
        return errors

    def verify_state_correspondence(self) -> List[str]:
        """Verify that recorded events reference real state and the latest event binds it."""
        errors = []
        security_claim_event_counts: dict[str, int] = {}
        for event in self.history:
            if not isinstance(event, Mapping):
                continue
            event_type = event.get("type")
            if event_type == "HYPOTHESES_SYNCHRONIZED":
                for node_id in event.get("hypotheses", ()):
                    node = self.model.nodes.get(node_id)
                    if node is None or node.kind != "hypothesis":
                        errors.append(f"audit event references missing hypothesis: {node_id}")
            elif event_type == "INVARIANT_CANDIDATES_RECORDED":
                for node_id in event.get("candidates", ()):
                    node = self.model.nodes.get(node_id)
                    if node is None or node.kind != "invariant":
                        errors.append(f"audit event references missing invariant: {node_id}")
            elif event_type == "INVARIANT_VERIFICATION_RECORDED":
                node_id = event.get("candidate")
                node = self.model.nodes.get(node_id)
                if node is None or node.kind != "invariant":
                    errors.append(f"audit event references missing invariant: {node_id}")
            elif event_type == "INVARIANT_HYPOTHESIS_LINKS_RECORDED":
                for link in event.get("links", ()):
                    if not isinstance(link, Mapping):
                        errors.append("audit invariant link is malformed")
                        continue
                    invariant_id = link.get("invariant")
                    hypothesis_id = link.get("hypothesis")
                    invariant = self.model.nodes.get(invariant_id)
                    hypothesis = self.model.nodes.get(hypothesis_id)
                    if invariant is None or invariant.kind != "invariant":
                        errors.append(f"audit event references missing invariant: {invariant_id}")
                    if hypothesis is None or hypothesis.kind != "hypothesis":
                        errors.append(f"audit event references missing hypothesis: {hypothesis_id}")
            elif event_type in {"PLAN_RECORDED", "UPDATE_RECORDED"}:
                observation_id = event.get("observation")
                observation = self.model.nodes.get(observation_id)
                if observation is None or observation.kind != "observation":
                    errors.append(f"audit event references missing observation: {observation_id}")
            elif event_type == "VERIFIED_SECURITY_CLAIM_PERSISTED":
                claim_id = event.get("security_claim")
                claim_node = self.model.nodes.get(claim_id)
                if claim_node is None or claim_node.kind != "security_claim":
                    errors.append(f"audit event references missing security claim: {claim_id}")
                else:
                    security_claim_event_counts[claim_id] = security_claim_event_counts.get(claim_id, 0) + 1
                    expected = {
                        "hypothesis": claim_node.attributes.get("hypothesis_id"),
                        "observation": claim_node.attributes.get("observation_id"),
                        "causal_chain": claim_node.attributes.get("causal_chain_id"),
                        "evidence": claim_node.attributes.get("evidence_ids"),
                        "claim_fingerprint": claim_node.attributes.get("claim_fingerprint"),
                    }
                    for field, value in expected.items():
                        if event.get(field) != value:
                            errors.append(f"verified security claim event does not match canonical claim: {claim_id}")
                            break
                    if claim_node.attributes.get("verified") is not True:
                        errors.append(f"persisted security claim is not canonically verified: {claim_id}")
                    hypothesis_id = claim_node.attributes.get("hypothesis_id")
                    if claim_id != f"security_claim:{hypothesis_id}":
                        errors.append(f"security claim node ID does not match canonical hypothesis: {claim_id}")
            if event_type == "PLAN_RECORDED":
                observation = self.model.nodes.get(event.get("observation"))
                if observation is not None and observation.attributes.get("planned") is not True:
                    errors.append(f"plan event does not correspond to planned observation: {event.get('observation')}")
                event_hypotheses = tuple(event.get("hypotheses", ()))
                for hypothesis_id in event_hypotheses:
                    node = self.model.nodes.get(hypothesis_id)
                    if node is None or node.kind != "hypothesis":
                        errors.append(f"plan event references missing hypothesis: {hypothesis_id}")
                if observation is not None:
                    node_pair = tuple(observation.attributes.get("discriminates_hypothesis_ids", ()))
                    event_pair = tuple(event.get("discriminates_hypothesis_ids", ()))
                    if node_pair != event_pair:
                        errors.append(f"plan event hypothesis binding does not match observation: {event.get('observation')}")
                    if node_pair:
                        hypothesis_map = {node_id: self.model.nodes[node_id] for node_id in event_hypotheses if node_id in self.model.nodes}
                        try:
                            validate_competing_pair(node_pair, hypothesis_map, self._competing_pairs())
                        except ValueError as exc:
                            errors.append(f"plan event has invalid competing hypothesis binding: {exc}")
            elif event_type == "UPDATE_RECORDED":
                for belief_id in event.get("beliefs", ()):
                    node = self.model.nodes.get(belief_id)
                    if node is None or node.kind != "belief":
                        errors.append(f"update event references missing belief: {belief_id}")
                evidence_id = event.get("evidence")
                if evidence_id:
                    node = self.model.nodes.get(evidence_id)
                    if node is None or node.kind != "evidence":
                        errors.append(f"update event references missing evidence: {evidence_id}")
                causal_id = event.get("causal_chain")
                if causal_id:
                    node = self.model.nodes.get(causal_id)
                    if node is None or node.kind != "causal_chain":
                        errors.append(f"update event references missing causal chain: {causal_id}")

        canonical_security_claim_ids = {
            node_id for node_id, node in self.model.nodes.items() if node.kind == "security_claim"
        }
        for claim_id in canonical_security_claim_ids:
            count = security_claim_event_counts.get(claim_id, 0)
            if count != 1:
                errors.append(f"canonical security claim must have exactly one persistence event: {claim_id}")

        if self.history:
            latest = self.history[-1]
            stored = latest.get("state_digest") if isinstance(latest, Mapping) else None
            if not stored:
                errors.append("latest audit event is missing state digest")
            elif stored != self._state_digest(self.model):
                errors.append("audit state digest mismatch with current graph state")
        return errors

    def _competing_pairs(self) -> set[tuple[str, str]]:
        return {
            (edge.source, edge.target)
            for edge in self.model.edges
            if edge.relation == "competes_with"
        }

    def export_state(self) -> dict:
        errors = self.validate()
        if errors:
            raise ValueError(f"cannot export invalid reasoning graph: {errors[0]}")
        return {
            "serialization_version": self.SERIALIZATION_VERSION,
            "audit_algorithm": self.AUDIT_ALGORITHM,
            "model": self.model.export(),
            "history": [dict(event) for event in self.history],
        }

    @classmethod
    def from_state_dict(cls, payload: Mapping[str, object]) -> "ReasoningGraph":
        if not isinstance(payload, Mapping):
            raise TypeError("reasoning graph state must be a mapping")
        if payload.get("serialization_version") != cls.SERIALIZATION_VERSION:
            raise ValueError("unsupported reasoning graph serialization version")
        if payload.get("audit_algorithm") != cls.AUDIT_ALGORITHM:
            raise ValueError("unsupported reasoning audit algorithm")
        model_payload = payload.get("model")
        history_payload = payload.get("history")
        if not isinstance(model_payload, Mapping):
            raise ValueError("reasoning graph state is missing canonical model")
        if not isinstance(history_payload, list):
            raise ValueError("reasoning graph state is missing audit history")
        graph = cls(SystemModel.from_dict(dict(model_payload)))
        graph.history = [dict(event) for event in history_payload if isinstance(event, Mapping)]
        if len(graph.history) != len(history_payload):
            raise ValueError("audit history contains a non-mapping event")
        errors = graph.validate()
        if errors:
            raise ValueError(f"persisted reasoning graph is invalid: {errors[0]}")
        return graph

    def add_hypotheses(self, hypotheses: List[Hypothesis]) -> List[str]:
        ids = []; updated = []
        for h in hypotheses:
            node_id = f"hypothesis:{h.name}"; attributes = {"probability": h.probability, "predictions": {name: dict(outcomes) for name, outcomes in h.predictions.items()}, "state": h.state.value, "subject_id": node_id}; existing = self.model.nodes.get(node_id)
            if existing is None: self.model.add_node(Node(node_id, "hypothesis", h.name, attributes)); updated.append(node_id)
            elif existing.kind != "hypothesis": raise ValueError(f"hypothesis ID conflicts with non-hypothesis node: {node_id}")
            else:
                merged = {**existing.attributes, **attributes}
                if merged != existing.attributes: self.model.nodes[node_id] = Node(existing.node_id, existing.kind, existing.label, merged); updated.append(node_id)
            ids.append(node_id)
        if updated: self._event("HYPOTHESES_SYNCHRONIZED", hypotheses=updated)
        return ids

    def add_observation(self, observation: Observation) -> str:
        node_id = f"observation:{observation.name}"; attributes = {"outcomes": list(observation.outcomes), "cost": observation.cost, "authorized": observation.authorized, "domain": observation.domain, "execution_id": observation.execution_id, "execution_request_digest": observation.execution_request_digest, "discriminates_hypothesis_ids": list(observation.discriminates_hypothesis_ids), "target_ids": list(observation.target_ids), "rationale": observation.rationale}; existing = self.model.nodes.get(node_id)
        if existing is None:
            self.model.add_node(Node(node_id, "observation", observation.name, attributes)); return node_id
        if existing.kind != "observation": raise ValueError(f"observation ID conflicts with non-observation node: {node_id}")
        immutable_keys = tuple(key for key in attributes if key != "rationale")
        if any(existing.attributes.get(key) != attributes[key] for key in immutable_keys):
            raise ValueError("observation identity conflicts with existing canonical observation")
        return node_id

    def record_invariant_candidates(self, candidates) -> List[str]:
        candidate_ids = []
        for candidate in candidates:
            node_id = candidate.candidate_id; attributes = {"status": "candidate", "source_ids": list(candidate.source_ids), "confidence": candidate.confidence, "evidence_count": candidate.evidence_count, "discovery_metadata": dict(getattr(candidate, "metadata", {}))}; existing = self.model.nodes.get(node_id)
            if existing is None: self.model.add_node(Node(node_id, "invariant", candidate.statement, attributes))
            elif existing.kind != "invariant": raise ValueError(f"candidate ID conflicts with non-invariant node: {node_id}")
            else:
                preserved = {**existing.attributes, **attributes}; verification_state = existing.attributes.get("verification_state")
                if verification_state in {state.value for state in VerificationState}: preserved["verification_state"] = verification_state; preserved["status"] = verification_state; preserved["verified"] = verification_state == VerificationState.SUPPORTED.value
                self.model.nodes[node_id] = Node(existing.node_id, existing.kind, existing.label, preserved)
            candidate_ids.append(node_id)
        if candidate_ids: self._event("INVARIANT_CANDIDATES_RECORDED", candidates=candidate_ids)
        return candidate_ids

    def record_invariant_verification(self, verification: CandidateVerification, *, evidence_node_ids: Optional[Mapping[str, str]] = None, rationale: str = "") -> str:
        node = self.model.nodes.get(verification.candidate_id)
        if node is None or node.kind != "invariant": raise KeyError(f"invariant node missing: {verification.candidate_id}")
        if not verification.evidence_ids: raise ValueError("verification requires evidence IDs")
        evidence_node_ids = evidence_node_ids or {e: f"evidence:{e}" for e in verification.evidence_ids}
        for evidence_id in verification.evidence_ids:
            evidence = self.model.nodes.get(evidence_node_ids[evidence_id])
            if evidence is None or evidence.kind != "evidence": raise KeyError(f"evidence node missing: {evidence_node_ids[evidence_id]}")
        state = verification.state.value; attributes = {**node.attributes, "verification_state": state, "verification_evidence_ids": list(verification.evidence_ids), "supporting_evidence_ids": list(verification.supporting_ids), "contradicting_evidence_ids": list(verification.contradicting_ids), "verification_confidence": verification.confidence, "verification_rationale": rationale, "verified": state == VerificationState.SUPPORTED.value, "status": state}; self.model.nodes[verification.candidate_id] = Node(node.node_id, node.kind, node.label, attributes)
        for e in verification.supporting_ids: self.model.connect(verification.candidate_id, "verified_by", evidence_node_ids[e], provenance="explicit_verification", rationale=rationale)
        for e in verification.contradicting_ids: self.model.connect(verification.candidate_id, "contradicted_by", evidence_node_ids[e], provenance="explicit_verification", rationale=rationale)
        self._event("INVARIANT_VERIFICATION_RECORDED", candidate=verification.candidate_id, state=state, evidence=list(verification.evidence_ids), confidence=verification.confidence, rationale=rationale); return verification.candidate_id

    def record_invariant_hypothesis_links(self, links: Mapping[str, Iterable[str]], *, provenance: str = "explicit_reasoning_mapping", rationale: str = "") -> List[tuple[str, str]]:
        if not provenance.strip(): raise ValueError("relationship provenance must not be empty")
        persisted = []
        for invariant_id, hypothesis_ids in links.items():
            invariant = self.model.nodes.get(invariant_id)
            if invariant is None or invariant.kind != "invariant": raise KeyError(f"invariant node missing: {invariant_id}")
            for hypothesis_id in hypothesis_ids:
                hypothesis = self.model.nodes.get(hypothesis_id)
                if hypothesis is None or hypothesis.kind != "hypothesis": raise KeyError(f"hypothesis node missing: {hypothesis_id}")
                self.model.connect(invariant_id, "informs", hypothesis_id, provenance=provenance, rationale=rationale); persisted.append((invariant_id, hypothesis_id))
        if persisted: self._event("INVARIANT_HYPOTHESIS_LINKS_RECORDED", links=[{"invariant": s, "hypothesis": t} for s, t in persisted], provenance=provenance, rationale=rationale)
        return persisted

    def add_evidence(self, evidence: Evidence) -> str:
        node_id = f"evidence:{evidence.evidence_id}"; attributes = {"kind": evidence.kind.value, "value": evidence.value, "interpretation": evidence.interpretation, "confidence": evidence.confidence, "provenance": {"source": evidence.provenance.source, "acquired_at": evidence.provenance.acquired_at.isoformat(), "collector": evidence.provenance.collector, "scope_status": evidence.provenance.scope_status, "details": evidence.provenance.details}}
        details = evidence.provenance.details
        if evidence.provenance.source == "foundry" and isinstance(details, Mapping) and details.get("execution_id") and details.get("request_digest"):
            request_id = f"execution_request:{details['request_digest']}"; receipt_id = f"execution_result:{details['request_digest']}"; request = self.model.nodes.get(request_id); receipt = self.model.nodes.get(receipt_id)
            if request is None or request.kind != "execution_request": raise RuntimeError("external execution evidence requires its canonical execution request")
            if receipt is None or receipt.kind != "execution_result": raise RuntimeError("external execution evidence requires a durable result receipt")
            if request.attributes.get("execution_id") != details["execution_id"]: raise RuntimeError("external execution evidence does not match its canonical execution request")
            if receipt.attributes.get("execution_id") != details["execution_id"] or receipt.attributes.get("request_digest") != details["request_digest"]: raise RuntimeError("external execution evidence does not match its durable result receipt")
            if receipt.attributes.get("payload") != evidence.value: raise RuntimeError("external execution evidence does not match its durable result payload")
        existing = self.model.nodes.get(node_id)
        if existing is None: self.model.add_node(Node(node_id, "evidence", evidence.evidence_id, attributes))
        elif existing.kind != "evidence": raise ValueError(f"evidence ID conflicts with non-evidence node: {node_id}")
        elif existing.attributes != attributes: raise ValueError(f"evidence ID conflicts with immutable persisted evidence: {node_id}")
        return node_id

    def record_plan(self, plan: Plan, hypotheses: List[Hypothesis], observation: Observation) -> str:
        if plan.observation != observation.name: raise ValueError("plan observation does not match canonical observation")
        if not observation.authorized: raise ValueError("unauthorized observations cannot enter an executable reasoning plan")
        observation_pair = tuple(observation.discriminates_hypothesis_ids)
        plan_pair = tuple(plan.discriminates_hypothesis_ids)
        if plan_pair != observation_pair:
            raise ValueError("plan hypothesis binding does not match canonical observation")
        self.add_hypotheses(hypotheses)
        hypothesis_map = {h.hypothesis_id: h for h in hypotheses}
        if observation_pair:
            validate_competing_pair(observation_pair, hypothesis_map)
        observation_id = self.add_observation(observation)
        if observation_pair:
            left, right = observation_pair
            self.model.connect(left, "competes_with", right, provenance="explicit_planner_binding")
        node = self.model.nodes[observation_id]
        self.model.nodes[observation_id] = Node(observation_id, node.kind, node.label, {**node.attributes, "planned": True, "expected_information_gain": plan.expected_information_gain, "utility": plan.utility, "rationale": plan.rationale})
        for h in hypotheses: self.model.connect(f"hypothesis:{h.name}", "tested_by", observation_id)
        self._event("PLAN_RECORDED", observation=observation_id, hypotheses=[f"hypothesis:{h.name}" for h in hypotheses], discriminates_hypothesis_ids=list(observation_pair), rationale=plan.rationale)
        return observation_id

    def record_update(self, result: UpdateResult, observation_id: str, evidence_id: Optional[str] = None, causal_chain_id: Optional[str] = None) -> GraphUpdate:
        if observation_id not in self.model.nodes: raise KeyError("observation must exist before its update is recorded")
        if self.model.nodes[observation_id].kind != "observation": raise ValueError("update source must be an observation node")
        if evidence_id:
            if evidence_id not in self.model.nodes: raise KeyError("evidence node must exist")
            if self.model.nodes[evidence_id].kind != "evidence": raise ValueError("evidence_id must reference an evidence node")
        if causal_chain_id:
            if causal_chain_id not in self.model.nodes: raise KeyError("causal chain node must exist")
            if self.model.nodes[causal_chain_id].kind != "causal_chain": raise ValueError("causal_chain_id must reference a causal_chain node")
        hypothesis_names = {h.name for h in result.hypotheses}; unknown = set(result.evidence_polarity) - hypothesis_names
        if unknown: raise ValueError(f"evidence polarity references unknown hypotheses: {sorted(unknown)}")
        belief_ids = []; transitions = []
        for h in result.hypotheses:
            hypothesis_id = h.hypothesis_id; node = self.model.nodes.get(hypothesis_id)
            if node is None or node.kind != "hypothesis": raise KeyError(f"hypothesis node missing: {hypothesis_id}")
            prior_probability = node.attributes.get("probability", h.probability); prior_state = node.attributes.get("state", "unresolved"); polarity = result.evidence_polarity.get(h.name); synchronized = {**node.attributes, "probability": h.probability, "predictions": {n: dict(o) for n, o in h.predictions.items()}, "state": h.state.value}; self.model.nodes[hypothesis_id] = Node(node.node_id, node.kind, node.label, synchronized)
            belief_id = f"belief:{h.name}:{len(self.history)}"; self.model.add_node(Node(belief_id, "belief", h.name, {"hypothesis_id": hypothesis_id, "evidence_id": evidence_id, "causal_chain_id": causal_chain_id, "prior_probability": prior_probability, "probability": h.probability, "prior_state": prior_state, "state": h.state.value, "observed_outcome": result.observed_outcome, "evidence_strength": result.evidence_strength, "status": result.status, "explanation": result.explanation, "evidence_polarity": polarity.value if polarity else None})); self.model.connect(observation_id, "updates", belief_id); self.model.connect(hypothesis_id, "updated_to", belief_id); belief_ids.append(belief_id); transitions.append({"hypothesis": hypothesis_id, "prior_probability": prior_probability, "posterior_probability": h.probability, "prior_state": prior_state, "posterior_state": h.state.value, "evidence_polarity": polarity.value if polarity else None})
            if evidence_id and polarity == EvidencePolarity.SUPPORTS: self.model.connect(evidence_id, "supports", hypothesis_id, provenance="explicit_observation_update")
            elif evidence_id and polarity == EvidencePolarity.CONTRADICTS: self.model.connect(evidence_id, "contradicts", hypothesis_id, provenance="explicit_observation_update")
        if evidence_id: self.model.connect(evidence_id, "derived_from", observation_id, provenance="explicit_graph_link")
        if causal_chain_id:
            if evidence_id: self.model.connect(causal_chain_id, "explains", evidence_id)
            for h in result.hypotheses:
                polarity = result.evidence_polarity.get(h.name); relation = polarity.value if polarity in {EvidencePolarity.SUPPORTS, EvidencePolarity.CONTRADICTS} else None
                if relation: self.model.connect(causal_chain_id, relation, h.hypothesis_id, provenance="explicit_causal_mapping")
        self._event("UPDATE_RECORDED", observation=observation_id, evidence=evidence_id, causal_chain=causal_chain_id, beliefs=belief_ids, transitions=transitions, status=result.status, observed_outcome=result.observed_outcome); return GraphUpdate(observation_id, belief_ids, evidence_id, causal_chain_id)

    def record_test_result(self, *args, **kwargs):
        raise RuntimeError("direct test-result recording is disabled; use ReasoningOrchestrator.execute_external_observation() followed by ingest_observation_result()")

    def validate(self) -> List[str]:
        errors = self.model.validate(); errors.extend(validate_graph(self.model)); errors.extend(self.verify_history_integrity()); errors.extend(self.verify_state_correspondence()); return errors

    def export_history(self) -> List[dict]: return [dict(event) for event in self.history]
