"""Blind benchmark adapter for CYDRA's canonical reasoning lifecycle.

The blind run never loads historical findings or evaluation annotations. It may,
however, pass reasoning-produced finding drafts through the normal finding gate
so the sealed artifact represents the complete reasoning-to-finding boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable

from .benchmark_corpus import BenchmarkCorpusEntry
from .benchmark_materialization import MaterializedBenchmarkInput, validate_materialized_input
from .benchmark_replay import BenchmarkReplayAdapter, BenchmarkReplayResult, ReplayAuthorization, ReplayVerifier
from .evidence_reasoning_provider import CanonicalEvidenceReasoningProvider, EvidenceReasoningPolicy
from .finding_synthesis import ReasoningFindingDraft, synthesize_reasoning_findings
from .investigation_control import InvestigationBudget, InvestigationController, InvestigationLease, InvestigationScope
from .scope import ScopePolicy, ScopeRule, ScopeState
from .security_reasoning import SecurityReasoningInputs, persist_security_claims
from .canonical_pipeline import CanonicalAuditPipeline


@dataclass(frozen=True)
class BlindReasoningResult:
    case_id: str
    materialization_fingerprint: str
    model_fingerprint: str
    hypothesis_names: tuple[str, ...]
    observation_names: tuple[str, ...]
    selected_observation: str | None
    rounds_used: int
    planning_steps_used: int
    observations_used: int
    contest_name: str = ""
    repository: str = ""
    revision: str = ""
    input_manifest: tuple[str, ...] = ()
    replay_result: dict[str, object] | None = None
    hypothesis_updates: tuple[dict[str, object], ...] = ()
    findings: tuple[dict[str, object], ...] = ()
    promotion_attempts: tuple[dict[str, object], ...] = ()

    def to_json(self) -> str:
        payload = {
            "case": {
                "case_id": self.case_id,
                "contest_name": self.contest_name,
                "repository": self.repository,
                "revision": self.revision,
                "rules": {},
                "input_manifest": list(self.input_manifest),
            },
            "case_id": self.case_id,
            "materialization_fingerprint": self.materialization_fingerprint,
            "model_fingerprint": self.model_fingerprint,
            "hypothesis_names": list(self.hypothesis_names),
            "observation_names": list(self.observation_names),
            "selected_observation": self.selected_observation,
            "rounds_used": self.rounds_used,
            "planning_steps_used": self.planning_steps_used,
            "observations_used": self.observations_used,
            "replay_result": self.replay_result,
            "hypothesis_updates": list(self.hypothesis_updates),
            "findings": list(self.findings),
            "promotion_attempts": list(self.promotion_attempts),
        }
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _sources(root: Path, materialized: MaterializedBenchmarkInput) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in materialized.selected_paths:
        try:
            sources[relative] = (root / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"blind benchmark source is not UTF-8 text: {relative}") from exc
    return sources


def _model_fingerprint(pipeline: CanonicalAuditPipeline) -> str:
    """Hash stable canonical intake state, excluding per-run identity and execution state."""
    exported = pipeline.model.export()
    session_ids = {node["id"] for node in exported["nodes"] if node["kind"] == "audit_session"}
    nodes = [node for node in exported["nodes"] if node["kind"] != "audit_session"]
    edges = [edge for edge in exported["edges"] if edge["source"] not in session_ids and edge["target"] not in session_ids]
    payload = {"schema_version": exported["schema_version"], "nodes": nodes, "edges": edges}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _serialized_hypothesis_updates(graph, observation_name: str) -> tuple[dict[str, object], ...]:
    """Expose the canonical persisted belief transitions for one observation."""
    observation_id = f"observation:{observation_name}"
    belief_ids = sorted(
        edge.target
        for edge in graph.model.edges
        if edge.source == observation_id and edge.relation == "updates"
    )
    updates: list[dict[str, object]] = []
    for belief_id in belief_ids:
        node = graph.model.nodes.get(belief_id)
        if node is None or node.kind != "belief":
            raise RuntimeError("blind artifact references an invalid persisted belief update")
        attributes = node.attributes
        updates.append({
            "hypothesis_id": attributes["hypothesis_id"],
            "prior_probability": attributes["prior_probability"],
            "posterior_probability": attributes["probability"],
            "prior_state": attributes["prior_state"],
            "posterior_state": attributes["state"],
            "observed_outcome": attributes["observed_outcome"],
            "evidence_strength": attributes["evidence_strength"],
            "status": attributes["status"],
            "evidence_polarity": attributes["evidence_polarity"],
            "evidence_id": attributes["evidence_id"],
        })
    return tuple(updates)


def _persist_planned_reasoning(graph, hypotheses, observations, plan) -> None:
    """Persist the selected reasoning plan without minting execution authority."""
    if plan is None:
        return
    selected = next((observation for observation in observations if observation.name == plan.observation), None)
    if selected is None:
        raise RuntimeError("planner selected an observation absent from provider inputs")
    graph.add_hypotheses(list(hypotheses))
    graph.record_plan(plan, list(hypotheses), selected)


def _replay_selected_observation(
    pipeline: CanonicalAuditPipeline,
    controller: InvestigationController,
    proposed,
    plan,
    root: Path,
    case: BenchmarkCorpusEntry,
    materialized: MaterializedBenchmarkInput,
    verifier: ReplayVerifier,
) -> BenchmarkReplayResult:
    """Execute exactly the planner-selected observation through the canonical gateway."""
    selected = next((item for item in proposed.observations if item.name == plan.observation), None)
    if selected is None:
        raise RuntimeError("selected observation is absent from reasoning proposals")

    authorization = ReplayAuthorization(
        f"benchmark-replay:{case.case_id}:{materialized.fingerprint()[:16]}"
    )
    adapter = BenchmarkReplayAdapter(root, verifier)
    pipeline.orchestrator.register_external_adapter("benchmark_replay", adapter)
    request = adapter.build_request(
        observation=selected,
        authorization=authorization,
        command=("cydra-replay", selected.name),
    )
    bound = replace(
        selected,
        execution_request=request,
        execution_request_digest=request.digest,
    )
    pipeline.orchestrator.persist_execution_request_binding(request, bound)
    controller.authorize_observation(bound)
    result = pipeline.orchestrator.execute_external_observation(
        "benchmark_replay",
        bound,
        authorization=authorization,
    )
    evidence_id = f"evidence:benchmark-replay:{case.case_id}:{plan.observation}"
    pipeline.orchestrator.ingest_observation_result(
        result,
        bound,
        list(proposed.hypotheses),
        evidence_id,
        evidence_polarity=result.polarity,
    )
    return result


def _promotion_output(graph, drafts: Iterable[ReasoningFindingDraft]) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    """Materialize explicit reasoning claims, then pass them through the canonical gate."""
    draft_list = tuple(drafts)
    if not draft_list:
        return (), ()

    from .benchmark_finding_promotion import FindingPromotionCandidate, promote_reasoning_findings

    synthesized = synthesize_reasoning_findings(graph, draft_list)
    candidates = [FindingPromotionCandidate(item.candidate, item.finding) for item in synthesized]
    attempts = promote_reasoning_findings(graph, candidates)
    findings: list[dict[str, object]] = []
    serialized_attempts: list[dict[str, object]] = []
    for attempt in attempts:
        serialized_attempts.append({
            "finding_id": attempt.finding_id,
            "decision": attempt.decision.value,
            "finding_fingerprint": attempt.finding_fingerprint,
            "reasons": list(attempt.reasons),
        })
        if attempt.decision.value == "READY" and attempt.finding_fingerprint is not None:
            finding_node = graph.model.nodes.get(attempt.finding_id)
            severity = finding_node.attributes.get("severity") if finding_node is not None else None
            findings.append({
                "finding_fingerprint": attempt.finding_fingerprint,
                "severity": severity,
            })
    return tuple(findings), tuple(serialized_attempts)


def run_blind_reasoning(
    case: BenchmarkCorpusEntry,
    materialized: MaterializedBenchmarkInput,
    staging_root: str | Path,
    *,
    policy: EvidenceReasoningPolicy | None = None,
    solidity_asts: dict[str, dict] | None = None,
    finding_drafts: Iterable[ReasoningFindingDraft] = (),
    observation_replayer: ReplayVerifier | None = None,
) -> BlindReasoningResult:
    """Run passive intake, bounded planning, optional observation replay, and promotion."""
    root = Path(staging_root).resolve()
    validate_materialized_input(case, root, materialized)
    source_map = _sources(root, materialized)

    scope = ScopePolicy([
        ScopeRule(path, ScopeState.IN_SCOPE, "blind benchmark input")
        for path in materialized.selected_paths
    ])
    pipeline = CanonicalAuditPipeline(scope.decide)
    pipeline.ingest(materialized.selected_paths, source_map, solidity_asts=solidity_asts)
    model_fingerprint = _model_fingerprint(pipeline)

    provider = CanonicalEvidenceReasoningProvider(policy)
    proposed = provider.propose(pipeline.model)
    allowed = frozenset(observation.name for observation in proposed.observations)
    controller = InvestigationController(
        f"investigation:{case.case_id}:{materialized.fingerprint()[:16]}",
        InvestigationScope(f"scope:{case.case_id}", allowed_observations=allowed),
        InvestigationBudget(
            max_rounds=2,
            max_observations=1,
            max_planning_steps=1,
            max_hypotheses=max(1, len(proposed.hypotheses)),
            max_execution_cost=1.0,
        ),
        InvestigationLease("blind-benchmark", 0.0, 9_999_999_999.0, generation=1),
    )

    controller.require_active()
    controller.begin_round()
    controller.register_hypotheses(len(proposed.hypotheses))
    plan = controller.plan(list(proposed.hypotheses), list(proposed.observations))

    _persist_planned_reasoning(
        pipeline.orchestrator.graph,
        proposed.hypotheses,
        proposed.observations,
        plan,
    )
    if isinstance(proposed, SecurityReasoningInputs):
        persist_security_claims(pipeline.orchestrator.graph, proposed)

    replay_result = None
    hypothesis_updates: tuple[dict[str, object], ...] = ()
    if plan is not None and observation_replayer is not None:
        replay_result = _replay_selected_observation(
            pipeline,
            controller,
            proposed,
            plan,
            root,
            case,
            materialized,
            observation_replayer,
        )
        hypothesis_updates = _serialized_hypothesis_updates(
            pipeline.orchestrator.graph,
            plan.observation,
        )

    # Finalize security claims only after the selected observation has produced a
    # verified belief transition and causal trace. This is deliberately downstream
    # of replay: a security hypothesis must cross the canonical verified-claim
    # boundary before any finding draft can be considered.
    if isinstance(proposed, SecurityReasoningInputs) and replay_result is not None:
        from .security_claim_orchestrator import finalize_verified_security_claims
        finalize_verified_security_claims(pipeline.orchestrator, proposed)

    # The verified-claim provider is the finding-facing boundary. It only emits
    # explicit claim_kind=finding contracts; ordinary security hypotheses remain
    # reasoning output and cannot be promoted by inference.
    if finding_drafts:
        promotion_drafts = tuple(finding_drafts)
    else:
        from .verified_claim_reasoning import VerifiedClaimDraftProvider
        promotion_drafts = VerifiedClaimDraftProvider().propose(pipeline.orchestrator.graph, None)
    findings, promotion_attempts = _promotion_output(pipeline.orchestrator.graph, promotion_drafts)

    return BlindReasoningResult(
        case_id=case.case_id,
        contest_name=case.contest_name,
        repository=case.repository,
        revision=case.revision,
        input_manifest=materialized.selected_paths,
        materialization_fingerprint=materialized.fingerprint(),
        model_fingerprint=model_fingerprint,
        hypothesis_names=tuple(item.name for item in proposed.hypotheses),
        observation_names=tuple(item.name for item in proposed.observations),
        selected_observation=plan.observation if plan else None,
        rounds_used=controller.rounds_used,
        planning_steps_used=controller.planning_steps_used,
        observations_used=controller.observations_used,
        replay_result=(dict(replay_result.canonical_payload()) if replay_result is not None else None),
        hypothesis_updates=hypothesis_updates,
        findings=findings,
        promotion_attempts=promotion_attempts,
    )