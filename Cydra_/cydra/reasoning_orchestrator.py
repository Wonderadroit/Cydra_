"""Orchestrate CYDRA's evidence-to-plan reasoning lifecycle.

CYDRA plans and reasons; concrete adapters execute outside the reasoning engine.
The orchestrator owns the canonical request/state boundary but never executes commands.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping, Optional

from .audit_session import AuditSessionResult, RepositoryAuditSession
from .execution_request import ExecutionRequest
from .external_execution import ExternalExecutionGateway, validate_result_binding
from .foundry import result_to_evidence
from .graph_semantics import validate_graph
from .hypothesis_bridge import planning_set_to_persistent
from .invariant_hypothesis_bridge import planner_hypotheses_from_verified_invariants, persist_invariant_hypotheses
from .invariants import InvariantCandidate, candidates_from_system_model
from .planner import Hypothesis, Observation, Plan, choose_next_observation
from .reasoning_graph import GraphUpdate, ReasoningGraph
from .system_model import Node, SystemModel
from .updater import EvidencePolarity, update_hypotheses


@dataclass(frozen=True)
class ReasoningPlan:
    invariant_candidates: tuple[InvariantCandidate, ...]
    persistent_hypothesis_ids: tuple[str, ...]
    plan: Plan


@dataclass(frozen=True)
class AuthorizedInvestigationPlan:
    """Canonical plan-to-execution handoff carrying the live authority capability."""
    observation_id: str
    observation: Observation
    authorization: object


class ReasoningOrchestrator:
    def __init__(self, model: Optional[SystemModel] = None):
        self.graph = ReasoningGraph(model)
        self.external_gateway = ExternalExecutionGateway(self._persist_gateway_request, self._set_gateway_execution_state, self._get_gateway_execution_state, self._persist_gateway_result)

    @property
    def model(self) -> SystemModel:
        return self.graph.model

    def register_external_adapter(self, name: str, adapter: object) -> None:
        self.external_gateway.register(name, adapter)

    def _persist_gateway_request(self, request: ExecutionRequest) -> str:
        matches = [node.node_id for node in self.model.nodes.values() if node.kind == "observation" and node.attributes.get("execution_id") == request.execution_id]
        if len(matches) != 1:
            raise ValueError("execution request must resolve to exactly one planned observation")
        return self.persist_execution_request(request, matches[0])

    def _get_gateway_execution_state(self, request: ExecutionRequest) -> Optional[str]:
        node = self.model.nodes.get(f"execution_request:{request.digest}")
        return None if node is None or node.kind != "execution_request" else node.attributes.get("execution_state")

    def _set_gateway_execution_state(self, request: ExecutionRequest, state: str) -> str:
        node_id = f"execution_request:{request.digest}"
        node = self.model.nodes.get(node_id)
        if node is None or node.kind != "execution_request":
            raise ValueError("execution request must be persisted before its lifecycle can advance")
        current = node.attributes.get("execution_state")
        allowed = {None: {"PERSISTED"}, "PERSISTED": {"RUNNING"}, "RUNNING": {"RESULT_RECORDED", "FAILED", "OUTCOME_UNRECORDED"}, "RESULT_RECORDED": {"COMPLETED", "OUTCOME_UNRECORDED"}, "COMPLETED": set(), "FAILED": set(), "OUTCOME_UNRECORDED": {"COMPLETED", "FAILED"}}
        if state not in allowed.get(current, set()):
            raise RuntimeError(f"invalid persisted execution transition: {current or 'ABSENT'} -> {state}")
        self.model.nodes[node_id] = Node(node.node_id, node.kind, node.label, {**node.attributes, "execution_state": state})
        self.graph._event("EXECUTION_STATE_CHANGED", execution_request=node_id, execution_id=request.execution_id, previous_state=current, state=state)
        return node_id

    def _persist_gateway_result(self, request: ExecutionRequest, result) -> str:
        validate_result_binding(result, request)
        payload = result.canonical_payload()
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        receipt_fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        node_id = f"execution_result:{request.digest}"
        attributes = {"execution_id": request.execution_id, "request_digest": request.digest, "adapter": request.adapter, "payload": payload, "fingerprint": receipt_fingerprint}
        existing = self.model.nodes.get(node_id)
        if existing is None:
            self.model.add_node(Node(node_id, "execution_result", request.digest, attributes))
        elif existing.kind != "execution_result" or existing.attributes != attributes:
            raise ValueError("execution result receipt conflicts with an existing canonical receipt")
        self.graph._event("EXECUTION_RESULT_RECORDED", execution_result=node_id, execution_request=f"execution_request:{request.digest}", execution_id=request.execution_id, request_digest=request.digest, fingerprint=receipt_fingerprint)
        return node_id

    def _require_result_receipt(self, request: ExecutionRequest, result) -> str:
        validate_result_binding(result, request)
        node_id = f"execution_result:{request.digest}"
        node = self.model.nodes.get(node_id)
        if node is None or node.kind != "execution_result":
            raise RuntimeError("external result has no durable result receipt; canonical receipt required")
        payload = result.canonical_payload()
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        expected = {"execution_id": request.execution_id, "request_digest": request.digest, "adapter": request.adapter, "payload": payload, "fingerprint": fingerprint}
        if node.attributes != expected:
            raise RuntimeError("external result does not match the durable canonical receipt")
        return node_id

    def persist_execution_request(self, request: ExecutionRequest, observation_id: str) -> str:
        if observation_id not in self.model.nodes or self.model.nodes[observation_id].kind != "observation":
            raise ValueError("execution request must bind to an existing observation")
        observation = self.model.nodes[observation_id]
        if observation.attributes.get("execution_id") != request.execution_id:
            raise ValueError("execution request identity does not match observation")
        planned_digest = observation.attributes.get("execution_request_digest")
        if planned_digest and planned_digest != request.digest:
            raise ValueError("execution request digest does not match observation")
        node_id = f"execution_request:{request.digest}"
        existing = self.model.nodes.get(node_id)
        canonical = {**request.canonical_payload(), "digest": request.digest, "execution_state": "PERSISTED"}
        if existing is None:
            self.model.add_node(Node(node_id, "execution_request", request.digest, canonical))
        elif existing.kind != "execution_request":
            raise ValueError("execution request ID conflicts with a non-execution-request node")
        else:
            state = existing.attributes.get("execution_state")
            if state not in {None, "PERSISTED", "RUNNING", "RESULT_RECORDED", "COMPLETED", "FAILED", "OUTCOME_UNRECORDED"}:
                raise ValueError("persisted execution request has an invalid lifecycle state")
            canonical["execution_state"] = state
            if dict(existing.attributes) != canonical:
                raise ValueError("persisted execution request conflicts with canonical request")
        self.model.connect(observation_id, "executes_request", node_id, provenance="explicit_execution_binding")
        self.graph._event("EXECUTION_REQUEST_PERSISTED", observation=observation_id, execution_request=node_id, digest=request.digest)
        return node_id

    def _load_persisted_execution_request(self, observation_id: str, digest: str) -> ExecutionRequest:
        request_id = f"execution_request:{digest}"
        node = self.model.nodes.get(request_id)
        if node is None or node.kind != "execution_request": raise ValueError("planned execution request is missing from the canonical graph")
        if not any(edge.source == observation_id and edge.relation == "executes_request" and edge.target == request_id for edge in self.model.edges): raise ValueError("planned execution request is not explicitly bound to the observation")
        return ExecutionRequest.from_canonical_payload(node.attributes, expected_digest=digest)

    def plan_next(self, hypotheses: Iterable[Hypothesis], observations: Iterable[Observation], invariant_hypotheses: Optional[Mapping[str, Iterable[str]]] = None, verified_invariant_hypotheses: Optional[Mapping[str, Hypothesis]] = None) -> Optional[ReasoningPlan]:
        hypothesis_list = list(hypotheses)
        observation_list = list(observations)
        invariant_candidates = self.derive_invariants()
        bridge_pairs = []
        if verified_invariant_hypotheses:
            planning_model = SystemModel.from_dict(self.model.export())
            for candidate in invariant_candidates:
                if candidate.candidate_id not in planning_model.nodes:
                    planning_model.add_node(Node(candidate.candidate_id, "invariant", candidate.statement, {"status": "candidate", "source_ids": list(candidate.source_ids), "confidence": candidate.confidence, "evidence_count": candidate.evidence_count}))
            bridge_pairs = planner_hypotheses_from_verified_invariants(planning_model, list(invariant_candidates), verified_invariant_hypotheses)
            for _, hypothesis in bridge_pairs:
                if all(existing.name != hypothesis.name for existing in hypothesis_list): hypothesis_list.append(hypothesis)
        plan = choose_next_observation(hypothesis_list, observation_list)
        if plan is None: return None
        self.persist_invariants(invariant_candidates)
        self.graph.add_hypotheses(hypothesis_list)
        persistent = planning_set_to_persistent(hypothesis_list)
        if verified_invariant_hypotheses:
            bridge_pairs = planner_hypotheses_from_verified_invariants(self.model, list(invariant_candidates), verified_invariant_hypotheses)
            persist_invariant_hypotheses(self.model, [record for record, _ in bridge_pairs])
        if invariant_hypotheses: self.link_invariants_to_hypotheses(invariant_hypotheses)
        selected = next(observation for observation in observation_list if observation.name == plan.observation)
        observation_id = self.graph.record_plan(plan, hypothesis_list, selected)
        self._persist_execution_binding(observation_id, selected)
        return ReasoningPlan(invariant_candidates=invariant_candidates, persistent_hypothesis_ids=tuple(h.hypothesis_id for h in persistent), plan=plan)

    def ingest_observation_result(self, result, observation: Observation, hypotheses: list[Hypothesis], evidence_id: str, *, evidence_polarity: Optional[Mapping[str, EvidencePolarity]] = None, causal_chain_id: Optional[str] = None) -> GraphUpdate:
        observation_id = f"observation:{observation.name}"
        node = self.model.nodes.get(observation_id)
        if node is None or node.kind != "observation": raise KeyError("observation must be an existing planned observation")
        if not node.attributes.get("planned"): raise ValueError("observation result requires a persisted plan")
        if node.attributes.get("authorized") is not True or not observation.authorized: raise ValueError("unauthorized observations cannot be ingested")
        planned_execution_id = node.attributes.get("execution_id")
        if not planned_execution_id: raise ValueError("planned observation is missing an execution identity")
        if result.execution_id != planned_execution_id: raise ValueError("external result execution identity does not match the planned observation")
        digest = node.attributes.get("execution_request_digest")
        request = None
        if digest:
            request = self._load_persisted_execution_request(observation_id, digest)
            validate_result_binding(result, request)
            self._require_result_receipt(request, result)
        evidence = result_to_evidence(result, evidence_id, authorization_id=request.authorization_id, scope_status=request.scope_status) if request is not None else result_to_evidence(result, evidence_id)
        evidence_node_id = self.graph.add_evidence(evidence)
        update_hypotheses_input = hypotheses
        discriminated_ids = tuple(observation.discriminates_hypothesis_ids)
        if discriminated_ids:
            hypotheses_by_id = {hypothesis.hypothesis_id: hypothesis for hypothesis in hypotheses}
            if len(discriminated_ids) != 2 or discriminated_ids[0] == discriminated_ids[1]:
                raise ValueError("explicit observation hypothesis binding must contain two distinct hypotheses")
            if any(hypothesis_id not in hypotheses_by_id for hypothesis_id in discriminated_ids):
                raise ValueError("explicit observation hypothesis binding references a missing hypothesis")
            update_hypotheses_input = [hypotheses_by_id[hypothesis_id] for hypothesis_id in discriminated_ids]
        updated = update_hypotheses(update_hypotheses_input, observation.name, result.outcome, evidence_strength=1.0, evidence_polarity=evidence_polarity)
        update = self.graph.record_update(updated, observation_id, evidence_node_id, causal_chain_id)
        self.graph._event("OBSERVATION_RESULT_INGESTED", observation=observation_id, evidence=evidence_node_id, outcome=result.outcome, execution_id=planned_execution_id, execution_request_digest=digest, external_execution=True)
        return update

    def execute_external_observation(self, adapter_name: str, observation: Observation, *, authorization):
        observation_id = f"observation:{observation.name}"
        node = self.model.nodes.get(observation_id)
        if node is None or node.kind != "observation" or not node.attributes.get("planned"): raise ValueError("external execution requires an existing persisted observation plan")
        if node.attributes.get("authorized") is not True or not observation.authorized: raise ValueError("unauthorized observations cannot be executed")
        execution_id = node.attributes.get("execution_id"); digest = node.attributes.get("execution_request_digest")
        if not execution_id or not digest: raise ValueError("external execution requires persisted execution identity and request digest")
        if observation.execution_id != execution_id: raise ValueError("observation execution identity does not match the persisted plan")
        if observation.execution_request_digest != digest: raise ValueError("observation request digest does not match the persisted plan")
        request = self._load_persisted_execution_request(observation_id, digest)
        result = self.external_gateway.execute(adapter_name, request, authorization=authorization)
        validate_result_binding(result, request); self._require_result_receipt(request, result)
        self.graph._event("EXTERNAL_EXECUTION_COMPLETED", observation=observation_id, execution_request=f"execution_request:{request.digest}", execution_id=request.execution_id, outcome=result.outcome)
        return result

    def _existing_recovery_update(self, observation_id: str, evidence_node_id: str, expected_hypothesis_ids: set[str], causal_chain_id: Optional[str]) -> Optional[GraphUpdate]:
        belief_ids = [edge.target for edge in self.model.edges if edge.source == observation_id and edge.relation == "updates"]
        if not belief_ids: return None
        beliefs = [self.model.nodes.get(node_id) for node_id in belief_ids]
        if any(node is None or node.kind != "belief" for node in beliefs): raise RuntimeError("recovery found an invalid persisted belief edge; refusing replay")
        matching = [node for node in beliefs if node.attributes.get("evidence_id") == evidence_node_id and node.attributes.get("causal_chain_id") == causal_chain_id]
        if len(matching) != len(expected_hypothesis_ids): raise RuntimeError("recovery found a partial or ambiguous belief update; refusing replay")
        actual_hypothesis_ids = {node.attributes.get("hypothesis_id") for node in matching}
        if actual_hypothesis_ids != expected_hypothesis_ids: raise RuntimeError("recovery belief update does not match the planned hypothesis set")
        if set(belief_ids) != {node.node_id for node in matching}: raise RuntimeError("observation contains an unrelated or duplicate belief update; refusing replay")
        return GraphUpdate(observation_id, [node.node_id for node in matching], evidence_node_id, causal_chain_id)

    def _validate_existing_recovery_evidence(self, evidence_node_id: str, evidence) -> None:
        node = self.model.nodes.get(evidence_node_id)
        if node is None: return
        if node.kind != "evidence": raise RuntimeError("recovery evidence identity conflicts with a non-evidence node")
        expected = {"kind": evidence.kind.value, "value": evidence.value, "interpretation": evidence.interpretation, "confidence": evidence.confidence, "provenance": {"source": evidence.provenance.source, "acquired_at": evidence.provenance.acquired_at.isoformat(), "collector": evidence.provenance.collector, "scope_status": evidence.provenance.scope_status, "details": evidence.provenance.details}}
        if node.attributes != expected: raise RuntimeError("recovery evidence identity resolves to different persisted evidence")

    def reconcile_external_observation_result(self, result, observation: Observation, hypotheses: list[Hypothesis], evidence_id: str, *, evidence_polarity: Optional[Mapping[str, EvidencePolarity]] = None, causal_chain_id: Optional[str] = None, terminal_state: str = "COMPLETED") -> GraphUpdate:
        if terminal_state not in {"COMPLETED", "FAILED"}: raise ValueError("reconciliation terminal state must be COMPLETED or FAILED")
        observation_id = f"observation:{observation.name}"; node = self.model.nodes.get(observation_id)
        if node is None or node.kind != "observation" or not node.attributes.get("planned"): raise ValueError("reconciliation requires an existing persisted observation plan")
        if node.attributes.get("authorized") is not True or not observation.authorized: raise ValueError("unauthorized observations cannot be reconciled")
        execution_id = node.attributes.get("execution_id"); digest = node.attributes.get("execution_request_digest")
        if not execution_id or not digest: raise ValueError("reconciliation requires persisted execution identity and request digest")
        if result.execution_id != execution_id: raise ValueError("external result execution identity does not match the planned observation")
        request = self._load_persisted_execution_request(observation_id, digest); validate_result_binding(result, request)
        state = self._get_gateway_execution_state(request)
        if state not in {"OUTCOME_UNRECORDED", "RESULT_RECORDED", "COMPLETED"}: raise RuntimeError(f"reconciliation requires a recorded external outcome, found {state or 'ABSENT'}")
        self._require_result_receipt(request, result)
        evidence = result_to_evidence(result, evidence_id, authorization_id=request.authorization_id, scope_status=request.scope_status)
        evidence_node_id = f"evidence:{evidence_id}"
        if evidence_node_id not in self.model.nodes:
            self.graph.add_evidence(evidence)
        self._validate_existing_recovery_evidence(evidence_node_id, evidence)
        discriminated_ids = tuple(observation.discriminates_hypothesis_ids)
        if discriminated_ids:
            if len(discriminated_ids) != 2 or discriminated_ids[0] == discriminated_ids[1]:
                raise ValueError("explicit observation hypothesis binding must contain two distinct hypotheses")
            hypothesis_ids = {h.hypothesis_id for h in hypotheses}
            if any(hypothesis_id not in hypothesis_ids for hypothesis_id in discriminated_ids):
                raise ValueError("explicit observation hypothesis binding references a missing hypothesis")
            expected_hypothesis_ids = set(discriminated_ids)
        else:
            expected_hypothesis_ids = {h.hypothesis_id for h in hypotheses}
        existing_update = self._existing_recovery_update(observation_id, evidence_node_id, expected_hypothesis_ids, causal_chain_id)
        if existing_update is None: update = self.ingest_observation_result(result, observation, hypotheses, evidence_id, evidence_polarity=evidence_polarity, causal_chain_id=causal_chain_id)
        else: update = existing_update
        if state != "COMPLETED": self.external_gateway.reconcile_result(request, result, terminal_state=terminal_state)
        self.graph._event("EXTERNAL_EXECUTION_RECONCILED", observation=observation_id, execution_request=f"execution_request:{request.digest}", execution_id=request.execution_id, terminal_state=terminal_state, evidence=evidence_id)
        return update

    def attach_audit_session(self, result: AuditSessionResult) -> str:
        provenance_errors = RepositoryAuditSession.validate_persisted_provenance(result.model, result.session_id)
        if provenance_errors: raise ValueError(f"audit-session provenance is invalid: {provenance_errors[0]}")
        graph_errors = validate_graph(result.model)
        if graph_errors: raise ValueError(f"audit-session graph is invalid: {graph_errors[0]}")
        session_node = result.model.nodes.get(result.session_id)
        if session_node is None or session_node.kind != "audit_session": raise ValueError("audit-session result does not contain its canonical session node")
        if self.model.nodes and self.model.export() != result.model.export(): raise ValueError("cannot attach a different canonical graph to a non-empty reasoning graph")
        if self.model.nodes: return result.session_id
        self.graph.model = result.model
        self.graph._event("AUDIT_SESSION_ATTACHED", session_id=result.session_id, intake_id=session_node.attributes.get("intake_id"))
        return result.session_id

    def derive_invariants(self) -> tuple[InvariantCandidate, ...]: return tuple(candidates_from_system_model(self.model))
    def persist_invariants(self, candidates: Iterable[InvariantCandidate]) -> list[str]: return self.graph.record_invariant_candidates(list(candidates))
    def link_invariants_to_hypotheses(self, links: Mapping[str, Iterable[str]], *, provenance: str = "explicit_reasoning_mapping", rationale: str = "") -> list[tuple[str, str]]: return self.graph.record_invariant_hypothesis_links(links, provenance=provenance, rationale=rationale)

    def _persist_execution_binding(self, observation_id: str, observation: Observation) -> None:
        digest = observation.execution_request_digest
        if not digest: return
        if not observation.execution_id: raise ValueError("execution request digest requires an execution identity")
        if observation.execution_request is None: raise ValueError("execution request digest requires the canonical execution request")
        node = self.model.nodes.get(observation_id)
        if node is None or node.kind != "observation": raise ValueError("observation node missing while persisting execution binding")
        if node.attributes.get("execution_id") not in {None, observation.execution_id}: raise ValueError("cannot rebind an observation to a different execution identity")
        if (node.attributes.get("execution_request_digest") or None) not in {None, digest}: raise ValueError("cannot rebind an observation to a different execution request")
        if observation.execution_request.execution_id != observation.execution_id: raise ValueError("execution request identity does not match observation")
        if observation.execution_request.digest != digest: raise ValueError("execution request digest does not match observation")
        self.persist_execution_request(observation.execution_request, observation_id)
        updated_attributes = {**node.attributes, "execution_id": observation.execution_id, "execution_request_digest": digest}
        if updated_attributes != node.attributes: self.model.nodes[observation_id] = Node(node.node_id, node.kind, node.label, updated_attributes)

    def persist_execution_request_binding(self, request: ExecutionRequest, observation: Observation) -> str:
        observation_id = f"observation:{observation.name}"; node = self.model.nodes.get(observation_id)
        if node is None: raise ValueError("observation must be persisted before its execution request")
        if node.kind != "observation": raise ValueError("execution request binding target must be an observation")
        if node.attributes.get("execution_id") not in {None, observation.execution_id}: raise ValueError("cannot rebind an observation to a different execution identity")
        existing_digest = node.attributes.get("execution_request_digest") or None
        if existing_digest not in {None, observation.execution_request_digest, request.digest}: raise ValueError("cannot rebind an observation to a different execution request")
        if request.execution_id != observation.execution_id: raise ValueError("execution request identity does not match observation")
        if observation.execution_request_digest and request.digest != observation.execution_request_digest: raise ValueError("execution request digest does not match observation")
        if observation.execution_request is not None and observation.execution_request.digest != request.digest: raise ValueError("execution request does not match observation's canonical request")
        self.persist_execution_request(request, observation_id)
        updated_attributes = {**node.attributes, "execution_id": observation.execution_id, "execution_request_digest": request.digest}
        if updated_attributes != node.attributes: self.model.nodes[observation_id] = Node(node.node_id, node.kind, node.label, updated_attributes)
        return f"execution_request:{request.digest}"

    def _persisted_execution_request_for_observation(self, observation_id: str) -> ExecutionRequest:
        node = self.model.nodes.get(observation_id)
        if node is None or node.kind != "observation": raise KeyError("observation node is missing")
        digest = node.attributes.get("execution_request_digest")
        if not digest: raise ValueError("observation has no execution request digest")
        return self._load_persisted_execution_request(observation_id, digest)

    def record_authorized_plan(self, plan: Plan, hypotheses: list[Hypothesis], observation: Observation) -> str:
        observation_id = self.graph.record_plan(plan, hypotheses, observation); self._persist_execution_binding(observation_id, observation); return observation_id

    def record_investigation_plan(self, controller, plan: Plan, hypotheses: list[Hypothesis], observation: Observation, *, authorization, dependency_depth: int = 0) -> AuthorizedInvestigationPlan:
        from .investigation_execution import bind_observation_execution, issue_execution_authorization
        investigation_authorization = issue_execution_authorization(controller, observation, authorization, dependency_depth=dependency_depth)
        bound_observation = bind_observation_execution(observation, investigation_authorization)
        observation_id = self.record_authorized_plan(plan, hypotheses, bound_observation)
        return AuthorizedInvestigationPlan(observation_id=observation_id, observation=bound_observation, authorization=investigation_authorization)

    def execute_investigation_plan(self, adapter_name: str, planned: AuthorizedInvestigationPlan):
        from .investigation_execution import validate_execution_binding
        authorization = planned.authorization; authorization.validate_live(); observation = planned.observation; observation_id = f"observation:{observation.name}"
        if planned.observation_id != observation_id: raise ValueError("authorized investigation plan observation identity mismatch")
        node = self.model.nodes.get(observation_id)
        if node is None or node.kind != "observation" or not node.attributes.get("planned"): raise ValueError("authorized investigation plan is not persisted")
        digest = node.attributes.get("execution_request_digest")
        if not digest: raise ValueError("authorized investigation plan has no execution request")
        request = self._load_persisted_execution_request(observation_id, digest); validate_execution_binding(request, authorization)
        if request.digest != observation.execution_request_digest: raise ValueError("authorized investigation plan request digest mismatch")
        return self.execute_external_observation(adapter_name, observation, authorization=authorization)
