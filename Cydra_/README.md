# CYDRA

**CYDRA — Autonomous system-understanding and causal security reasoning engine**

CYDRA is an authorized repository-security reasoning engine designed to understand a system before making a security claim. It models structure, evidence, invariants, competing hypotheses, information-gain tests, observations, belief transitions, causal chains, and findings in one persistent reasoning graph.

## Reasoning pipeline

`Program Discovery → Program Acquisition → Rule/Scope Extraction → Relevant Reference Discovery → Resource Dependency Graph → Source/Deployment Acquisition → Scope Classification → Program Contract → Repository → Recon → SystemModel → Invariants → Evidence → Hypotheses → Test Planning → Bounded Investigation Control → Observation → Exact Execution Request → Persistent Request → External Gateway → External Execution → Durable Result Receipt → Result Rehydration/Recovery → Observed Evidence → Belief Update → Causal Verification → Finding → PoC Artifact → Persistent PoC Lineage → PoC Recovery → Untrusted Publication Transport → Strict Parse → Canonical Verification → Trusted Publication`

## Current architecture

- **Canonical SystemModel** — persistent representation of the target system and its security-relevant structure.
- **Canonical program intake** — Immunefi-first, API/adapter-based acquisition of program rules, scope, impacts, PoC requirements, disclosure constraints, repositories, deployments, and linked resources before active investigation.
- **Resource dependency graph** — relevant linked program resources are tracked with provenance, authority classification, acquisition state, freshness, fingerprints, and unresolved-resource state rather than being silently omitted.
- **Acquisition adapters are not authorities** — authoritative/API sources are preferred; authorized MCP/API adapters, bbscope, GitHub-specific acquisition, document/PDF sources, and controlled web fallback feed evidence into the canonical intake boundary without silently overriding it.
- **Scope versus understanding** — scope controls what CYDRA may test and claim, not what it may need to understand. Out-of-scope components may be acquired and modeled as contextual dependencies of an in-scope target, but remain blocked for active testing and cannot independently become eligible findings without explicit authorization.
- **Explicit scope states** — `IN_SCOPE`, `OUT_OF_SCOPE`, `CONDITIONAL`, and `UNKNOWN` remain distinct; `UNKNOWN` never silently becomes authorization.
- **Exact source/version identity** — repository analysis preserves the exact branch/tag/release/commit and deployment context required by the program rather than assuming the default branch is bounty-eligible.
- **Canonical node identity** — identical node re-addition is idempotent; reuse of a canonical node ID for different content is rejected rather than silently overwriting state.
- **Evidence layer** — provenance-preserving facts and artifacts.
- **Invariant lifecycle** — candidates are explicitly verified as `supported`, `contradicted`, or `unresolved` using canonical evidence.
- **Competing hypotheses** — alternative explanations with explicit probabilities, predictions, and state.
- **Canonical hypothesis boundary** — planner and persistent hypothesis representations synchronize explicitly by identity, belief/probability, state, and declared prediction metadata.
- **Persistent belief transitions** — each observation records prior/posterior probability, prior/posterior state, and explicit evidence polarity in the canonical graph.
- **Evidence polarity integrity** — `supports`, `contradicts`, and `neutral` are explicit caller-supplied relationships; CYDRA never infers polarity from probability, ranking, or hypothesis state.
- **Tamper-evident audit history** — reasoning events form a SHA-256 hash chain with sequence and previous-event linkage, and graph validation verifies its integrity.
- **Information-gain planning** — selects authorized observations based on expected information gain per cost.
- **Bounded autonomous investigation control** — scope, finite planning/observation/execution-cost budgets, dependency depth, branching limits, and time-bound leases constrain autonomous exploration; terminal uncertainty is explicit rather than an invitation to recurse indefinitely.
- **Target/meta separation** — planner self-evaluation belongs to a separately scoped meta investigation and cannot recursively expand a target investigation.
- **Authority recovery integrity** — investigation snapshots carry an authority fingerprint and cannot restore a modified budget or lease without an externally supplied matching authority fingerprint.
- **Externally authorized scope expansion** — dependency candidates are discoveries, not permissions; cross-contract targets become active only through an externally issued grant bound to the current authority fingerprint and dependency-depth ceiling.
- **Externally authorized adaptive budget/depth** — additional investigation rounds, observations, planning steps, hypotheses, execution cost, dependency depth, and branching capacity require an external grant with absolute ceilings; the planner cannot expand itself.
- **Bounded economic modeling** — `economic_model.py` models balances, liabilities, prices, value transitions, fees, slippage, attacker capital, and bounded multi-step scenarios as explicit simulation state.
- **Simulation/evidence separation** — a simulated profitable path or economic P/L estimate is never treated as proof that external execution occurred; confirmation uses the normal gateway and durable-receipt evidence path.
- **Persistent investigation learning** — `learning.py` stores bounded finding-derived knowledge for invariant patterns, hypothesis patterns, observation patterns, dependency discovery, and budget/depth heuristics. Learned knowledge can improve future reasoning but cannot grant or expand authority.
- **ReasoningGraph** — persists hypotheses, observations, plans, invariant candidates, verification evidence, beliefs, causal links, findings, and audit history.
- **Direct external-result bypass closed** — legacy `ReasoningGraph.record_test_result()` is disabled; external results must enter through the canonical orchestrator/gateway boundary.
- **ReasoningOrchestrator** — coordinates these boundaries without executing observations itself.
- **Audit-session reasoning boundary** — validated audit-session state can be explicitly attached after provenance and graph-semantic validation; existing reasoning state is never silently replaced or merged.
- **External observation-result ingestion** — externally executed authorized results enter only through an already persisted observation plan with exact execution identity/request binding and an exact durable result receipt; CYDRA does not execute or pretend to execute external commands.
- **Causal verification boundary** — persisted causal traces are reconstructed and classified as `verified`, `rejected`, or `unresolved` using explicit canonical evidence and belief-transition anchors.
- **Graph-aware finding gate** — finding promotion verifies canonical evidence, explicit hypothesis support, causal verification, trace connectivity, audit history, and audit-session provenance when applicable.
- **Finding claim grounding** — finding evidence and impact evidence must be grounded in the verified causal trace and explicitly support the finding hypothesis; severity is bound to the canonical impact level and evidence-free/unresolved impact claims are rejected.
- **Persistent findings** — approved findings are first-class canonical graph nodes linked explicitly to supporting evidence, hypothesis, causal trace, and originating audit session.
- **Canonical benchmark finding promotion** — blind reasoning output can pass reasoning-produced findings through the same graph-aware finding gate and persistence boundary; the benchmark adapter never consults historical issues or evaluation annotations, and blocked/unresolved candidates remain unpromoted.
- **Finding PoC artifacts** — `POCArtifact` reuses the canonical `Counterexample` and adds canonical PoC identity, finding/hypothesis lineage, evidence IDs, expected violation, reproducibility notes, and canonical execution-request identity. PoC artifacts are causal demonstration artifacts, not decorative report attachments.
- **Persistent PoC lineage** — `poc_persistence.py` persists PoCs as first-class graph nodes with explicit `demonstrates`, `for_hypothesis`, `uses_evidence`, and optional `derived_from_request` relationships.
- **PoC recovery boundary** — persisted PoCs are rehydrated only after canonical finding/causal-trace validation, counterexample validation, identity checks, execution-request lineage checks, graph semantics, audit integrity, and required lineage edges agree; recovery is read-only.
- **PoC integrity boundary** — PoC evidence must be grounded in the verified causal trace; reproducible artifacts retain the execution request that produced their external behavior; describing a PoC never implies that it was executed.
- **Finding recovery boundary** — serialized persisted findings are rehydrated only after canonical reference duplication, graph-edge lineage, evidence support, claim semantics, and audit integrity agree; recovery is read-only.
- **Finding reproducibility manifests** — manifests fingerprint the complete reasoning closure including impact evidence and independently fingerprint report-facing finding claims; verification detects claim mutation as well as graph/audit tampering.
- **Trusted finding publication boundary** — publication starts from the canonical persisted finding, refuses caller-supplied claim substitution, and verifies the reproducibility manifest against the same canonical reasoning state before a finding is treated as publishable.
- **Publication trust-state boundary** — `UntrustedFindingPublication` is the only result of transport parsing; it cannot be passed to trusted-publication verification. Explicit canonical verification promotes it to `FindingPublication`, making `UNTRUSTED TRANSPORT → STRICT PARSE → CANONICAL VERIFICATION → TRUSTED PUBLICATION` visible in the API.
- **Publication transport boundary** — serialized publication envelopes are parsed against an exact supported schema before verification; `verify_finding_publication_data()` treats transport data as untrusted, while `verify_and_trust_finding_publication_data()` performs explicit parse-and-promote verification.
- **Stale-publication detection** — trusted publications are revalidated against canonical finding state, relevant evidence, reproducibility closure, and tamper-evident audit state; graph/evidence mutation invalidates stale publication state rather than being silently absorbed.
- **Canonical repository recon** — passive repository structure projects into the same SystemModel used by security reasoning.
- **Solidity AST recon** — compiler-resolved Solidity structure and data-flow evidence can be projected into the canonical model without executing contracts or inventing conclusions.
- **Unified audit session** — `RepositoryAuditSession` composes repository and Solidity recon through one deterministic passive intake boundary.
- **Compiler identity integrity** — Solidity relationships retain separate compiler function/target declaration identities; names/source locations never substitute for declaration identity.
- **Atomic passive intake** — complete projection is staged and committed only after canonical graph validation, preventing partial mutation on malformed input.
- **Audit-session provenance** — each passive intake has a distinct session identity, deterministic intake fingerprint, normalized source/artifact SHA-256 manifests, and explicit scope decisions.
- **Audit-session provenance verification** — persisted session metadata can be independently revalidated by recomputing its deterministic fingerprint and checking manifest/path/file-node integrity; tampering fails closed.
- **Finding audit-session lineage** — session-backed findings carry exact canonical session identity and explicit finding → audit-session lineage.
- **Foundry execution adapter** — authorized Foundry execution records exact command, deterministic project fingerprint, Forge version, bounded timing, authorization/scope, execution identity, request digest, stdout/stderr, and return status.
- **Canonical external execution gateway** — all supported adapters share one request/result integrity and lifecycle boundary.
- **Persistent execution lifecycle** — requests progress through `PERSISTED → RUNNING → RESULT_RECORDED → COMPLETED`, with explicit `FAILED` and `OUTCOME_UNRECORDED` states.
- **Durable result receipts** — successful external results are immutable canonical graph receipts before execution is considered terminal; this prevents unsafe replay after process failure.
- **Receipt-bound evidence ingestion** — external results cannot become reasoning evidence merely because they match request identity/digest; ingestion revalidates the complete result against the exact durable canonical receipt first.
- **Fresh-process result recovery** — durable receipts can be rehydrated without external execution and routed through the normal reasoning reconciliation path after process restart.
- **Execution lifecycle audit correspondence** — persisted lifecycle events are independently reconstructed and checked against canonical request state, result receipts, identity, digest, and terminal completion semantics.
- **Concrete Foundry execution boundary** — `FoundryRunner.run_test()` requires a canonical execution identity, exact request digest, and gateway-owned capability before Forge can be invoked.
- **CI gateway integration** — the live Foundry integration test itself uses `ExternalExecutionGateway`; CI must exercise the same canonical execution boundary rather than calling the lower-level runner directly.
- **Blind benchmark corpus boundary** — frozen historical benchmark manifests contain only source revision and permitted blind inputs; report/finding/known-issue paths are rejected from the blind input contract.
- **Blind benchmark materialization** — `benchmark_materialization.py` verifies the exact repository revision, rejects symlinks and oracle-like paths, copies only selected files into a clean staging directory, and writes a deterministic oracle-free provenance receipt with file SHA-256 digests.
- **Blind benchmark validation** — the staged file set and receipt can be revalidated before investigation; extra, missing, substituted, stale, or oracle-like content fails closed.

## Architectural references

- `CYDRA_PROJECT_BIBLE.md` — canonical architectural source of truth.
- `docs/architecture/PROGRAM_INTAKE_AND_CONTEXT_SPEC.md` — canonical program acquisition, linked-resource, contextual dependency, and scope-versus-understanding specification.
- `docs/architecture/SCOPE_AND_RECON_SPEC.md` — canonical scope/recon enforcement and contextual dependency rules.

## Investigation capability profiles

Profiles are reasoning-policy presets, not authority escalators:

- **STANDARD** — normal bounded repository reasoning.
- **ECONOMIC** — bounded economic state/scenario modeling.
- **CROSS_CONTRACT** — dependency discovery plus explicitly authorized dependency expansion, with contextual modeling of dependencies needed to understand in-scope targets.
- **DEEP_ANALYSIS** — deeper investigation only when additional authority has been externally granted.
- **COMBINED** — combines these capabilities while preserving one authoritative scope and absolute ceiling.
