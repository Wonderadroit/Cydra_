# v1.123 — Conservative Immunefi Material Extraction

- Added deterministic HTML-to-text extraction using the standard-library HTML parser.
- Added `parse_immunefi_material()` for provenance-bound policy assertions covering PoC, KYC, testing restrictions, known-issue, audit, and disclosure policy signals.
- Added `extract_known_issues()` for explicit known-issue entries while keeping exact root-cause fingerprints unresolved unless supplied by authoritative material.
- Added `parse_immunefi_program()` to combine the bounded Information/Scope/Resources acquisition pages into structured intake context.
- Preserved the critical distinction: known-issue textual similarity is not issue identity and extracted context never grants execution authority.
- Full suite: 738 passed; 2 existing PytestCollectionWarnings.

## v1.122 — Version- and Asset-Bound Known-Issue Eligibility

- Added exact `known_issue_applies()` eligibility evaluation for program-declared known/duplicate issues.
- Require an exact issue/root-cause fingerprint before a known issue can exclude a candidate; textual or semantic resemblance alone never blocks promotion.
- Apply declared affected-asset and affected-version constraints without inventing constraints when the program did not publish them.
- Keep `RESOLVED_KNOWN`, `CONTEXT_ONLY`, and `UNKNOWN` entries as historical/contextual knowledge rather than automatic bounty blockers.
- Added adversarial regression coverage for fingerprint, asset, and version mismatches.
- Full suite: 736 passed; 2 existing PytestCollectionWarnings.

## v1.121 — Known-Issue / Prior-Knowledge Boundary

- Added first-class `KnownIssue` context to the Immunefi `ProgramContract`.
- Added explicit known-issue eligibility states so program-published duplicates can be blocked without treating every historical issue as an automatic semantic match.
- Added provenance, affected assets/versions, optional issue locator, and deterministic serialization for known-issue records.
- Added explicit `KNOWN_ISSUES` resource classification for known-issue/security-advisory references.
- Preserved the distinction between known-issue context and bounty eligibility: a distinct root cause is not rejected merely because it resembles prior context.
- Added regression coverage for known-issue exclusion, contextual retention, and non-authorizing acquisition.
- Full suite: 733 passed; 2 existing PytestCollectionWarnings.

## v1.120 — Immunefi Canonical Acquisition Boundary

- Added an injectable `DocumentFetcher` transport boundary so Immunefi acquisition can be tested deterministically without coupling semantics to network transport.
- Added `ImmunefiAcquisitionAdapter` with canonical program slug/locator normalization and bounded acquisition of the Information, Scope, and Resources pages.
- Reject non-Immunefi inputs and fetcher responses that escape the Immunefi authority boundary.
- Hardened link classification for explorer hosts, documentation hosts, deployment paths, and exact Immunefi/GitHub host matching.
- Added regression coverage proving contextual discovery remains non-authorizing and unknown resources never become in-scope implicitly.
- Full suite: 730 passed; 2 existing PytestCollectionWarnings.

## v1.113.1 — Immunefi Program Intake Foundation

- Added canonical program/resource intake evidence and deterministic program-contract fingerprints.
- Added explicit acquisition states and authority classes.
- Added canonical SystemModel persistence for program/resource context without granting execution authority.
- Added live 0x Immunefi intake evaluation snapshot covering scope, contracts, rules, prohibited testing, PoC requirement, repository, and documentation references.
- Preserved the rule that contextual acquisition does not expand active testing authority.

# Changelog

## v1.119 — Post-Dogfood Compatibility and Recovery Hardening

- Fix current-belief projection to update an existing canonical belief node without attempting identity-substituting re-addition.
- Restore the `FoundryResult.passed` compatibility property while keeping the canonical `outcome` model authoritative.
- Keep Foundry evidence conversion compatible with legacy in-memory fixtures while preserving the canonical orchestrator request/result/receipt validation boundary.
- Restore authorization provenance in Foundry-derived evidence.
- Classify missing Foundry execution identity as a permission failure rather than a malformed-value failure.
- Fix fresh-process execution recovery to validate the canonical reasoning graph audit history rather than a nonexistent orchestrator-local history field.
- Reconcile causal finding tests with the current explicit `UNRESOLVED` state and canonical impact-evidence grounding requirements.
- Reconcile PoC tests with the current rule that reproducible PoCs require canonical execution-request identity.
- Reconcile recovery fixtures with the canonical graph-owned audit history.

## v1.118 — Blind Benchmark Materialization Boundary

- Add `benchmark_materialization.py` as the fail-closed boundary between a frozen historical repository checkout and a CYDRA blind run.
- Require the source checkout to match the exact corpus commit SHA before materialization.
- Materialize only manifest-selected files into a clean staging directory; symlinks and oracle-like paths are rejected.
- Persist a deterministic, oracle-free blind-input receipt containing the corpus fingerprint, source revision, selected paths, and file SHA-256 manifest.
- Revalidate the staged file set and receipt before the blind input can be handed to CYDRA.
- Reject stale, substituted, extra, missing, symlinked, or oracle-like materialized content.
- Add `tools/materialize_blind_benchmark.py` so benchmark preparation is reproducible without giving the investigation access to historical findings.
- Add adversarial regression coverage for revision mismatch, file tampering, receipt tampering, oracle-path selection, and clean materialization.

## v1.117 — Investigation Execution Authorization Boundary

- Bind external execution authorization to the live investigation authority fingerprint and lease generation.
- Persist only the authority snapshot on execution requests; recovery requires a fresh externally trusted capability from the live controller.
- Reject stale, forged, replayed, or authority-substituted execution bindings before external execution.
- Keep execution authorization separate from serialized investigation state so persisted state cannot grant new authority.

## v1.116 — Authority-Bound Learning-Aware Planning

- Require active investigation authority before learning-aware planning.
- Filter candidate observations through the current investigation scope and branching ceiling.
- Bind planning to a validated authority-derived learning context and terminate explicitly when no eligible high-value observation remains.

## v1.115 — Authority-Bound Persistent Learning Lifecycle

- Bind learning-aware planning to an immutable learning snapshot and investigation authority context.
- Add `LearningContext` with investigation identity, authority fingerprint, lease generation, and learning fingerprint.
- Require changed learning state or authority state to invalidate the planning context.
- Add an authority-plane factory so callers derive learning context from the live investigation controller rather than manufacturing authority fingerprints.

## v1.114 — Learning-Aware Observation Planning

- Allow bounded finding-derived observation-pattern learning to influence candidate ranking after information-gain and cost eligibility.
- Keep learning unable to change observation cost or information gain.
- Persist the learning IDs used by a plan for auditability.

## v1.113 — Persistent Finding-Derived Learning

- Bind explicit learning contributions to the verified-finding gate.
- Persist learning as canonical graph state with deterministic identity and finding lineage.
- Recover learning read-only with canonical finding provenance, graph semantics, audit integrity, and externally supplied limits.
- Keep failed learning validation atomic and prevent duplicate/rebound learning identities.

## v1.112 — Persistent Bounded Investigation Learning

- Preserve finding-derived learning across investigations while keeping learning bounded and authority-independent.
- Add bounded learning records for invariant, hypothesis, observation-pattern, dependency-pattern, and budget/depth heuristics.
- Allow learned knowledge to improve future reasoning only within already-issued authority.
- Prevent learning from granting scope, budget, depth, lease, execution capability, or expansion authority.

## v1.111 — Explicit Dependency Expansion Decision Boundary

- Keep dependency discovery separate from authorization.
- Distinguish already-authorized dependencies, context-only dependencies, and dependencies requiring active investigation expansion.
- Require explicit externally issued expansion decisions before an out-of-scope dependency becomes an active investigation target.
- Preserve target/meta separation and current authority fingerprints across expansion decisions.

## v1.110 — Bounded Autonomous Investigation Control

- Add an explicit investigation control plane separating planner optimization from investigation authority.
- Bound autonomous investigations with immutable scope, finite rounds/observations/planning/hypothesis/execution-cost budgets, dependency depth, and branching limits.
- Add explicit target and meta investigation domains so planner self-evaluation cannot recursively expand a target investigation.
- Add time-bound, generation-tagged investigation leases; expired investigations fail closed before planning or execution authorization.
- Add explicit terminal reasons for budget exhaustion, depth limits, scope exhaustion, lease expiry, missing evidence, and diminishing information value.
- Reject repeated execution identities within one investigation to prevent observation replay through the control plane.
- Bind observation domain and execution identity/request digest into canonical observation graph state.
- Add authority fingerprints for persisted investigation envelopes; snapshot recovery requires an externally supplied matching authority fingerprint and cannot extend its own lease or budget.
- Add adversarial regression coverage for recursive prerequisites, target/meta separation, budget exhaustion, lease expiry, stale snapshot authority, duplicate execution identity, low-information termination, and hypothesis-budget exhaustion.

## v1.109 — Persistent PoC Lineage and Recovery

- Give `POCArtifact` a canonical PoC identity so demonstrations can become first-class persistent graph state.
- Add canonical PoC graph relations for finding, hypothesis, causal evidence, and execution-request lineage.
- Add `persist_poc()` and `rehydrate_persisted_poc()` as read-only-validation recovery boundaries around persisted PoCs.
- Reject PoCs whose finding/hypothesis identity, evidence, execution request, counterexample, or graph lineage has been substituted or detached.
- Keep PoC persistence separate from execution authority: persistence and recovery never execute external actions.
- Add adversarial coverage for PoC identity duplication, finding rebinding, detached evidence, and missing lineage edges.

## v1.108 — Finding PoC Integrity

- Promote the existing `POCArtifact` into an explicit finding-demonstration contract rather than treating PoCs as decorative report attachments.
- Bind PoC artifacts to finding and hypothesis identity when that lineage is available.
- Preserve canonical evidence IDs and require PoC evidence to remain grounded in the verified causal trace.
- Preserve canonical execution-request identity for externally reproducible demonstrations.
- Distinguish a PoC description from evidence that the PoC was actually executed.
- Add adversarial regression coverage for finding/hypothesis rebinding, evidence outside the verified trace, and missing execution identity on reproducible artifacts.

## v1.107 — Durable Execution Receipt Ingestion Integrity

- Require externally executed observation results to match the durable canonical execution receipt before they can become reasoning evidence.
- Close the remaining ingestion gap where an in-memory result could satisfy request identity/digest checks while substituting its outcome or other receipt fields.
- Keep result ingestion fail-closed and read-only until the durable receipt matches exactly.
- Add adversarial coverage proving forged result substitution cannot enter the evidence layer.

## v1.106 — Stale Publication Invalidation

- Treat a previously verified finding publication as a snapshot that must remain bound to canonical reasoning state.
- Revalidate trusted publications against canonical finding recovery, reproducibility closure, and tamper-evident audit history before accepting them as current.
- Add adversarial coverage proving canonical finding mutation invalidates a previously trusted publication.
- Add adversarial coverage proving relevant evidence mutation invalidates a previously trusted publication.
- Keep publication verification read-only and fail closed rather than refreshing or mutating stale publication state.

## v1.105 — Publication Trust-State Separation

- Introduce `UntrustedFindingPublication` as the explicit result of strict publication transport parsing.
- Ensure parsing serialized publication data never creates the trusted `FindingPublication` type.
- Require explicit canonical graph verification before promotion from untrusted transport to trusted publication.
- Add `verify_and_trust_finding_publication_data()` for an explicit parse → verify → trust transition.
- Keep `verify_finding_publication()` restricted to trusted publication objects and reject untrusted transport objects.
- Preserve read-only canonical recovery and reproducibility verification as the source of publication trust; no detached manifest is treated as an authenticity proof.
- Add adversarial coverage for trust-state confusion, explicit promotion, substituted claims, schema drift, manifest tampering, ID rebinding, export/import, and read-only verification.

## v1.104 — Publication Transport Integrity

- Add strict parsing for serialized `FindingPublication` bundles before they can enter verification.
- Require the publication envelope, finding report shape, nested impact shape, and reproducibility manifest to have the exact supported schema shape; dropped or unexpected fields fail closed.
- Add `verify_finding_publication_data()` so external consumers can verify untrusted serialized publication data directly against canonical persisted reasoning state.
- Preserve the existing read-only canonical recovery and reproducibility checks after transport parsing.
- Add adversarial coverage for serialized title substitution, finding-ID rebinding, manifest field deletion/addition, finding-field injection, manifest tampering, round-trip parsing, and read-only verification.

## v1.103 — Trusted Finding Publication Integrity

- Add a dedicated read-only finding publication boundary.
- Build publications only from the canonical persisted finding recovered from the reasoning graph.
- Refuse caller-supplied finding claim substitution before publication.
- Verify the reproducibility manifest against the canonical recovered finding rather than an independently supplied report object.
- Add adversarial coverage for substituted claims, tampered manifests, export/import round trips, and read-only publication verification.

## v1.102 — Persisted Finding Recovery Boundary

- Add a trusted read-only persisted-finding recovery boundary.
- Require serialized findings to agree with canonical evidence, hypothesis, causal-chain, audit-session, and graph lineage before trust.
- Reject identity rebinding, detached evidence, malformed lineage, and audit-history divergence during recovery.
- Preserve canonical finding state as the only source for later publication/report trust.

## v1.101 — Reproducibility Claim Integrity

- Bind reproducibility manifests to impact evidence and an independent fingerprint of report-facing finding claims.
- Include the complete reasoning closure needed to reproduce the finding, including impact evidence.
- Detect claim substitution as well as graph and audit-history tampering during manifest verification.

## v1.100 — Finding Impact Grounding

- Ground finding impact claims in the verified causal trace and explicitly supporting evidence.
- Bind report severity to the canonical impact level.
- Reject unresolved or evidence-free impact claims.
- Preserve impact evidence as part of the finding's canonical reasoning closure.

## v1.99 — Finding Evidence Grounding

- Require finding evidence to be a subset of verified causal-trace evidence.
- Require every cited evidence ID to explicitly support the finding hypothesis.
- Add adversarial coverage for unsupported evidence attachment and detached causal references.

## v1.98 — Durable Execution Reconciliation Integrity

- Require durable result persistence before terminal external-execution reconciliation.
- Require every canonical execution request to have corresponding lifecycle audit history.
- Keep recovery fail-closed when lifecycle or receipt correspondence is incomplete.

## v1.97 — Gateway-Owned Execution Capability

- Add a gateway-owned opaque execution capability to the concrete Foundry adapter boundary.
- Require the exact gateway capability in both `execute()` and lower-level `run_test()` paths.
- Close direct adapter execution using only a valid request identity/digest.
- Add regression coverage for adapter rebinding across gateways.

## v1.96 — Canonical Execution Identity Boundary

- Require standalone Foundry execution to use canonical execution-request identity and digest.
- Reject direct external execution when request identity or digest is absent or substituted.

## v1.95 — Execution Lifecycle ↔ Audit Correspondence

- Add an independent audit-side validator that reconstructs durable external-execution lifecycle transitions from persisted reasoning events.
- Cross-check execution identity, request digest, canonical execution state, and immutable result-receipt identity.
- Reject reordered, skipped, duplicated, or terminally unanchored lifecycle events rather than trusting event presence alone.
- Require durable result recording before `RESULT_RECORDED` or successful `COMPLETED` transitions become audit-valid.
- Keep lifecycle validation read-only and separate from the runtime execution gateway; it cannot authorize or execute external operations.
- Add adversarial coverage for valid completion/failure, reordered transitions, result-event ordering, canonical-state substitution, and result-receipt substitution.

## v1.94 — Audit Event ↔ Graph State Correspondence

- Bind every newly recorded reasoning audit event to a deterministic canonical graph-state digest.
- Verify that the latest audit event still corresponds to the current canonical graph state, detecting post-event graph mutation before export or rehydration.
- Validate that recorded hypothesis, invariant, observation, belief, evidence, and causal-chain references resolve to canonical nodes of the expected kinds.
- Verify plan events still correspond to planned observations and update events still resolve to their recorded belief/evidence/causal nodes.
- Fail closed through the existing reasoning-graph validation and persistence boundary when event references or state correspondence are inconsistent.
- Add adversarial coverage for graph mutation after an event, substituted event references, and export-time correspondence validation.

## v1.93 — Finding Audit-Session Lineage Integrity

- Add regression coverage proving findings persist only with canonical audit-session provenance when an audit session exists in the reasoning graph.
- Reject substituted audit-session nodes that lack a valid persisted intake fingerprint and repository lineage.
- Reject findings that omit required audit-session lineage rather than treating a merely present session node as sufficient provenance.

## v1.92 — Finding Gate & Persistence Alignment

- Add regression coverage proving finding promotion and finding persistence accept the same invariant-backed causal trace semantics.
- Keep finding evidence restricted to canonical evidence nodes while allowing the causal verification anchor to be a canonical invariant.
- Prevent drift between the promotion gate and persistence boundary as causal verification semantics evolve.

## v1.91 — Causal Verification Anchor Integrity

- Preserve invariant nodes as valid causal-chain verification anchors during reconstruction.
- Validate actual evidence separately from invariant verification anchors instead of treating every causal trace reference as evidence.
- Return only canonical evidence nodes in causal verification's evidence set, preventing invariant anchors from being misclassified as evidence.
- Add regression coverage for causal chains whose verification anchor is a canonical invariant.

## v1.90 — Production Relation-Semantics Dogfood

- Add an AST-based self-audit regression that extracts literal production `SystemModel.connect()` relationship names and verifies every discovered relation is registered in the canonical semantic rules.
- Prevent recurrence of cross-layer drift where the canonical model accepts a relationship that the semantic validator does not understand.

## v1.89 — Durable Receipt-Bound External Evidence

- Require externally attributed Foundry evidence to resolve to its canonical execution request and durable execution-result receipt before it can enter the reasoning graph.
- Require the persisted receipt payload to exactly match the evidence value, preventing a result-shaped object from becoming authoritative without a recorded external outcome.
- Fail closed before evidence mutation when the request or durable receipt is missing or identity-substituted.
- Add regression coverage proving direct external-result ingestion cannot create evidence or belief transitions without the durable receipt boundary.

## v1.88 — Execution Binding Semantic Rule

- Register `executes_request` as a canonical graph relationship in the semantic validator.
- Constrain the relationship to `observation → execution_request` so valid execution bindings remain semantically coherent.
- Add regression coverage proving a valid canonical execution binding passes graph semantic validation.

## v1.87 — Result Receipt Binding Integrity

- Require persistent `execution_result` nodes to resolve to the canonical `execution_request` identified by its request digest.
- Cross-check receipt execution identity, adapter identity, and payload execution/request identities against the canonical request.
- Reject orphaned or request-substituted durable result receipts during graph validation.
- Add adversarial coverage for missing canonical requests and receipt identity substitution.

## v1.86 — Execution Request Binding Integrity

- Enforce one-to-one canonical binding between an execution request and its planned observation.
- Restrict `executes_request` endpoints to `observation → execution_request` at the persistent graph layer.
- Reject ambiguous/deserialized execution-request bindings rather than allowing later resolution to choose an arbitrary observation.
- Add adversarial coverage for duplicate observation bindings, wrong endpoint kinds, and persisted ambiguity.

## v1.85 — Planner Semantic Integrity & Observation Identity

- Require a persisted plan's observation name to exactly match the canonical observation being recorded.
- Reject observation identity reuse when outcomes, cost, or authorization metadata differ from the existing canonical observation.
- Preserve exact observation identity while keeping identical re-planning idempotent.
- Add regression coverage for plan/observation mismatch and observation identity conflicts.

## v1.84 — Verified Invariant → Hypothesis Bridge Hardening

- Require invariant-to-hypothesis promotion to originate from an explicitly `SUPPORTED` canonical invariant.
- Require supporting evidence IDs and matching `verified_by` evidence edges before a verified invariant can inform a hypothesis.
- Bind candidate statements exactly to the canonical invariant label so a caller cannot substitute different invariant text under an existing candidate ID.
- Reject direct persistence of an unverified invariant as a hypothesis source, even when a mutable `verified` flag is present.
- Reject conflicting existing hypothesis labels instead of overwriting canonical hypothesis content during bridge persistence.
- Add adversarial regression coverage for missing proof edges, statement substitution, unverified direct persistence, and identity/content conflicts.

## v1.83 — Compiler Declaration Identity Preservation

- Use compiler declaration IDs as canonical function/state-variable identities when AST evidence provides them.
- Prevent overloaded Solidity declarations from collapsing into one canonical function node merely because their source-level names match.
- Preserve an explicit `identity_status=unknown` fallback when compiler declaration identity is absent instead of guessing uniqueness.
- Carry function/target declaration IDs into canonical AST-derived nodes and relationship attributes for auditability.
- Add adversarial regression coverage for overloaded declarations and missing declaration identity.

## v1.82 — Scope-Safe Compiler AST Evidence Ingestion

- Enforce the repository scope decision again before projecting compiler-produced AST relationships into the canonical security model.
- Prevent compiler AST artifacts from reintroducing function/state/data-flow evidence for paths that passive repository recon correctly classified as out of scope.
- Normalize AST artifact paths before membership and scope checks so path spelling cannot bypass the requested-path boundary.
- Add adversarial regression coverage proving out-of-scope AST evidence is not projected while the out-of-scope file node remains explicitly represented with its scope state.

## v1.81 — Canonical Node Identity Collision Hardening

- Make `SystemModel.add_node()` idempotent only for an exactly identical canonical node.
- Reject attempts to reuse an existing node ID with different kind, label, or attributes instead of silently overwriting canonical state.
- Preserve existing explicit node replacement paths used by reasoning lifecycle code while closing the generic node-identity substitution boundary.
- Add regression coverage for identical-node idempotency and collision rejection without mutation.

## v1.80 — Direct Execution-Result Ingestion Bypass Closure

- Disable the legacy `ReasoningGraph.record_test_result()` path because it could accept an external result directly and bypass the canonical adapter gateway.
- Require external results to enter through `ReasoningOrchestrator.execute_external_observation()` and the adapter-neutral execution boundary before reasoning ingestion.
- Preserve the graph's lower-level `record_update()` primitive for already-established internal reasoning transitions; it does not establish external execution provenance.
- Add regression coverage proving the legacy direct-result path fails closed without mutating graph state.
- Treat this as a security boundary hardening release: authorization, exact execution-request binding, durable result receipt, replay protection, and recovery cannot be established by the reasoning graph alone.

## v1.79 — Fresh-Process External Result Rehydration

- Extend the adapter-neutral external execution contract with a non-executing `rehydrate_result()` boundary.
- Reconstruct durable external results from canonical receipts without invoking external execution or consulting mutable target state.
- Add exact `FoundryResult.from_canonical_payload()` validation and `FoundryRunner.rehydrate_result()` request binding.
- Require rehydrated Foundry receipts to match execution identity, request digest, exact command, project target, project fingerprint, authorization identity, and scope.
- Add a canonical fresh-process recovery helper that loads the persisted execution request and immutable result receipt from `SystemModel`.
- Validate receipt identity, adapter identity, canonical payload shape, and deterministic fingerprint before rehydration.
- Route recovered results through the existing orchestrator reconciliation path so evidence and belief updates retain canonical provenance and replay protection.
- Prove recovery performs zero external execution and survives `SystemModel.export()/from_dict()` process-reload boundaries.
- Reject malformed, substituted, or tampered receipts fail closed.

## v1.78 — Canonical Execution Lifecycle & Replay Protection

- Add a persistent execution lifecycle: `PERSISTED → RUNNING → RESULT_RECORDED → COMPLETED/FAILED`.
- Require every successful external execution to produce a durable, immutable canonical result receipt before it becomes terminal.
- Bind each result receipt to the exact execution identity, request digest, adapter, canonical result payload, and deterministic receipt fingerprint.
- Register `execution_result` as first-class `SystemModel` state and bump the SystemModel schema to 1.22.0.
- Enforce lifecycle transitions centrally at the adapter gateway and reject invalid state transitions fail closed.
- Treat persisted `RUNNING`, `RESULT_RECORDED`, `COMPLETED`, and `FAILED` requests as non-replayable, including after process reload.
- Preserve same-process replay protection as a secondary guard rather than the source of truth.
- Represent inability to durably record a successful external outcome as `OUTCOME_UNRECORDED`; this state is non-replayable and forces explicit reconciliation rather than unsafe automatic retry.
- Never misclassify an external execution that already produced a result as `FAILED` merely because result receipt or lifecycle persistence failed.
- Allow reasoning recovery after `COMPLETED` or `RESULT_RECORDED` when the immutable result receipt exists, without invoking the external adapter again.
- Make recovery at-most-once across the evidence/belief persistence crash window: complete updates are reused, partial updates fail closed, and evidence identities remain immutable.
- Require a durable canonical result receipt before reconciling an external outcome; a merely result-shaped object with matching execution identity/digest is not accepted as authoritative recovery state.
- Make Foundry result evidence replay-stable by preserving the external execution completion timestamp as evidence acquisition time when available.
- Restore the orchestrator's canonical external execution entry point and persist execution identity/request digest onto planned observations before request persistence.
- Enforce immutable request-parameter canonicalization at the Foundry adapter boundary without exposing frozen internal representation to adapter code.
- Add adversarial coverage for receipt integrity, recovery from completed execution, partial belief transitions, immutable evidence reuse, unrecorded outcomes, and canonical orchestrator execution.

## v1.77 — Canonical External Adapter Gateway

- Add `ExternalExecutionGateway` as the single orchestration boundary for supported adapters.
- Require every registered adapter to satisfy the canonical request-builder and request-bound execution contract.
- Persist the exact `ExecutionRequest` before delegating to an external adapter.
- Reject adapter-name substitution, authorization identity/scope substitution, duplicate registration, unregistered adapters, missing request persistence, and result identity/digest substitution.
- Add `FoundryRunner.execute()` so Foundry receives the canonical request rather than reconstructing an independent execution intent.
- Verify the Foundry request target, authorization, parameters, command, and canonical digest before Forge execution.
- Keep actual command execution outside CYDRA; the gateway only validates, persists, delegates, and releases a validated result.
- Add regression coverage for persistence ordering, authorization substitution, adapter substitution, duplicate/unregistered adapters, result substitution, and Foundry contract conformance.

## v1.76 — External Adapter Contract

- Add an adapter-neutral `ExternalExecutionAdapter` contract separating CYDRA reasoning from concrete external execution.
- Require supported adapters to expose canonical request construction and request-bound execution.
- Add `ExternalExecutionResult` as the minimum adapter result contract.
- Add fail-closed `validate_result_binding()` for execution identity and request digest integrity.

## v1.113.2 — End-to-End Immunefi 0x Intake Evaluation

- Exercised the captured 2026-09-04 0x program material through the real `ImmunefiAcquisitionAdapter` pipeline.
- Validated canonical Information/Scope/Resources acquisition, structured rule extraction, and bounded reference expansion.
- Added regression coverage proving contextual repository/documentation resources remain `UNKNOWN` scope rather than becoming authorized targets.
- Confirmed current 0x program material includes explicit known-issue and previous-audit eligibility boundaries.
- Full suite: 746 passed; 2 existing PytestCollectionWarnings.
