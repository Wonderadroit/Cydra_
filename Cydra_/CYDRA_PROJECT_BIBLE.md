# CYDRA Project Bible

**Project:** CYDRA  
**Repository:** `Wonderadroit/CYDRA`  
**Status:** v1.122 canonical development state — Immunefi-first bug-bounty reasoning + persistent bounded investigation learning

## Mission

CYDRA is a **diagnostic reasoning bug-bounty engine**, primarily designed for **Immunefi programs**, especially smart-contract, DeFi, protocol, token, oracle, bridge, lending, staking, exchange, and other on-chain security targets. It is a personal research tool for authorized bug-bounty work, not an audit/compliance product and not a general-purpose internet security service.

Its job is simple: **understand an authorized target deeply enough to find, investigate, verify, and explain real security bugs that are eligible for a bounty.**

CYDRA is not a vulnerability dictionary. It understands system behavior, preserves uncertainty, selects high-information observations, updates beliefs conservatively, verifies causal explanations, and produces reproducible bug-bounty findings. Engineering work is justified primarily when it improves CYDRA's ability to discover, verify, reproduce, prioritize, or clearly report real bounty-eligible security issues.

Canonical chain:
`System behavior → invariants → evidence → competing hypotheses → information-gain testing → observation → belief update → persistent system model → causal verification → finding`

Repository chain:
`Program/Repository acquisition → authorization/scope → recon → SystemModel → invariants → evidence → hypotheses → plan → bounded investigation authority → exact execution request → persistent request state → canonical adapter gateway → external execution → durable result receipt → result rehydration/recovery → exact receipt-bound result ingestion → belief update → contradiction handling → causal verification → finding gate → finding → PoC artifact → persistent PoC lineage → PoC recovery → reproducibility → untrusted publication transport → strict parse → canonical verification → trusted publication`

## Product focus and non-goals

**Primary objective:** maximize reliable bug discovery and verification for authorized Immunefi engagements.

The canonical optimization target is:

`Target understanding → Security invariants → Evidence → Competing hypotheses → High-information investigation → Causal verification → Verified bug → Reproducible PoC → Bounty-ready finding`

Priority order for engineering decisions:

1. Find more real bugs.
2. Reduce false positives and unsupported claims.
3. Improve investigation depth and information gain within authorized bounds.
4. Produce reproducible PoCs and strong Immunefi-ready findings.
5. Preserve provenance, uncertainty, and deterministic reasoning so results can be trusted and reproduced.
6. Learn from verified findings without allowing learning to create authority or contaminate blind evaluation.

**Non-goals:** CYDRA is not being built primarily for formal security auditing, compliance certification, enterprise audit management, public-facing security operations, or internet-exposed autonomous defense. Audit-style provenance, recovery, publication, and integrity controls are retained only where they directly protect reliable bug-bounty reasoning, evidence, PoC reproducibility, or finding correctness.

The word `audit` may remain in legacy/internal class or file names where changing it would create unnecessary architectural churn (for example `RepositoryAuditSession`), but such naming does **not** define CYDRA's product mission.

## Non-negotiable principles

- Authorized testing only; unknown authorization is fail-closed.
- **Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.**
- Scope enforcement precedes active testing and every later evidence-ingestion path must preserve that decision.
- Evidence has explicit provenance and polarity.
- Correlation is not causation.
- Names, labels, probabilities, similarity, and co-occurrence never establish unsupported relationships.
- Unknown, unresolved, supported, and contradicted states remain distinct.
- Contradictions are explicit and auditable.
- Planner probabilities/predictions are explicit inputs and are never inferred from invariant confidence.
- Planner and persistent hypotheses have explicit/lossless boundaries.
- Observations are planned by CYDRA but executed externally; CYDRA never pretends to have executed an external command.
- Important transitions are persistent and reconstructable.
- Reasoning history is append-only and tamper-evident.
- Canonical identity is never reconstructed from descriptive metadata when stronger declaration identity exists.
- Reusing a canonical node ID for different content is rejected; identical re-addition is idempotent.
- Compiler-resolved declaration IDs are preferred over names for AST-derived identity; missing declaration IDs remain explicitly unknown rather than guessed.
- External results must be bound to the exact persisted observation identity before ingestion.
- A complete execution request is persisted before supported external execution.
- External adapters execute only through the canonical gateway contract.
- Successful external execution must have a durable immutable result receipt before terminal completion.
- `RUNNING`, `RESULT_RECORDED`, `COMPLETED`, and `FAILED` are non-replayable; external side effects are never silently retried.
- A result-recording or lifecycle-persistence failure is an unreconciled outcome, not proof of external failure.
- Recovery may resume reasoning from a durable result receipt without invoking external execution.
- Legacy direct external-result recording is disabled.
- Persisted execution lifecycle events must correspond to canonical request state before recovery trusts them.
- Recovery requires intact audit history as well as a valid durable result receipt.
- Concrete Foundry execution additionally requires a gateway-owned opaque execution capability; a request digest alone is insufficient.
- Result ingestion requires both exact request binding and an exact match to the durable canonical result receipt; in-memory result objects cannot substitute for persisted execution outcomes.
- Finding evidence and impact claims must be grounded in the verified causal trace and explicitly support the finding hypothesis.
- Finding severity must match the canonical impact level; unresolved or evidence-free impact claims are rejected.
- A proof-of-concept is a causal demonstration artifact, not a decorative report attachment.
- PoC identity must bind to the finding and hypothesis it demonstrates; PoC evidence must be grounded in the verified causal trace.
- A PoC must distinguish prerequisites, demonstration steps, expected observations, and actual execution evidence; a description must never be presented as an executed result.
- A reproducible PoC must retain the canonical execution-request identity associated with its externally observed behavior.
- PoC generation or execution must not bypass scope, authorization, the canonical execution gateway, durable result receipts, or receipt-bound evidence ingestion.
- Persisted PoCs are first-class graph state with their own canonical identity and explicit finding, hypothesis, evidence, and execution-request lineage.
- PoC recovery is a read-only trust boundary and must reject identity rebinding, detached evidence, malformed counterexamples, missing lineage edges, and invalid audit history.
- Persisting or recovering a PoC never grants execution authority and never substitutes for an actual durable external execution receipt.
- Reproducibility manifests must bind report-facing claims and impact evidence to canonical reasoning state so exported claims cannot silently diverge from verified findings.
- Serialized persisted findings are untrusted transport state until the dedicated read-only recovery boundary validates their canonical references, lineage, claim semantics, and audit/state correspondence.
- A finding publication must originate from the canonical recovered finding; caller-supplied report objects cannot become trusted publication state merely because their manifest looks valid.
- Serialized publication bundles are untrusted transport state until their envelope and manifest shape are strictly parsed and then verified against canonical persisted reasoning state.
- Strict parsing must produce an explicitly untrusted publication type; it must not return the trusted publication type.
- Promotion from parsed publication transport to trusted publication requires explicit canonical verification against the persisted finding and reproducibility manifest.
- A valid detached manifest/fingerprint is not an authenticity proof outside the canonical graph; publication trust is established by canonical recovery and verification.
- Publication verification is read-only and compares both the finding claims and reproducibility manifest against canonical persisted reasoning state.
- Previously trusted publications are snapshots, not permanent authority: revalidation must detect canonical finding/evidence mutation and audit-state divergence before a publication is accepted as current.
- Publication verification fails closed on stale canonical state and never silently refreshes or mutates a publication.
- Regression and adversarial tests protect architectural invariants.
- **Complexity may justify requesting additional authority; complexity can never grant additional authority.**
- Dependency discovery never silently expands an authorized audit scope. Imports, libraries, routers, tokens, oracles, callbacks, and cross-contract calls become active scope only through explicit externally issued authorization.
- Contextual acquisition of an out-of-scope dependency is permitted for system understanding when needed to reason about an in-scope target, but it never authorizes active testing or finding eligibility against that dependency.
- `UNKNOWN` scope is unresolved; it is never silently converted to `IN_SCOPE` or `OUT_OF_SCOPE`.
- Acquiring code, documentation, deployment metadata, or public state never grants execution authority.
- Program acquisition adapters are mechanisms, not authorities. MCP, bbscope, caches, LLM normalization, and web fallback must not silently override authoritative program rules.
- Required but inaccessible program resources remain explicitly unresolved; CYDRA must not guess missing rules, scope, or authorization.
- Program/rule freshness must be tracked; stale material cannot silently remain current authority.
- Repository acquisition must preserve exact repository and revision identity; the default branch is not assumed to be the bounty-eligible or deployed version.
- Adaptive investigation budget/depth expansion is an authority transition, not a planner optimization. Any increase must be externally granted and bounded by an absolute ceiling.
- Economic reasoning is simulated modeling, not external execution evidence. A simulated profitable path, balance change, liquidation path, price movement, or attacker P/L estimate cannot establish that an external action occurred.
- Economic assumptions remain explicit and deterministic, with finite bounds on states, transitions, scenario depth/count, and attacker capital.
- Target investigations and meta investigations have separate authority domains. A target investigation cannot recursively authorize investigation of its own planner.
- Uncertainty is not a failure condition; **unboundedness is**. Investigations may terminate with unresolved hypotheses when their bounded authority is exhausted or information value is insufficient.
- CYDRA persists and applies learning from verified investigations. Each finding may enrich the invariant library, hypothesis library, observation patterns, dependency-discovery patterns, and budget/depth heuristics.
- Learning retains provenance and uncertainty and is bounded by explicit finite knowledge limits. Learned knowledge can improve reasoning within the issued investigation envelope but cannot create, extend, relax, or self-authorize scope, budget, depth, lease, execution capability, or any other authority.

## Canonical architecture

### Program intake and contextual acquisition

The program-intake layer establishes the bug-bounty engagement context before security reasoning. **Immunefi is CYDRA's primary program workflow and the default product context.** The program contract is therefore treated as the source of truth for what constitutes an eligible target, impact, testing permission, PoC, and submission. Program-specific scope, impacts, rules, PoC requirements, testing restrictions, repository/version requirements, deployment requirements, disclosure rules, known issues, and linked resources must be acquired and represented as provenance-aware evidence before active investigation.

The acquisition architecture is API-first, adapter-based, evidence-driven, and provenance-preserving. The canonical specification is `docs/architecture/PROGRAM_INTAKE_AND_CONTEXT_SPEC.md`.

Acquisition mechanisms may include an authoritative platform/API source, authorized MCP/API adapters, bbscope for scope aggregation/monitoring, GitHub-specific repository APIs/connectors, documentation/PDF adapters, deployment/explorer sources, and controlled web/document fallback. These are **adapters, not authorities**. A cache, mirror, MCP result, bbscope result, LLM-normalized scope list, or web page cannot silently override authoritative program material.

Relevant references from a program page or acquired rule/resource must be treated as resource dependencies when they are needed to understand scope, rules, assets, code, deployments, testing environments, PoC requirements, or disclosure constraints. The resource dependency graph records canonical identity, source/authority class, adapter, acquisition context, timestamp, content/version fingerprint, parent relationship, required/optional state, acquisition state, scope state, and provenance.

A referenced required resource that cannot be acquired or authenticated remains `UNRESOLVED`. Intake is not complete while required authorization/rule material remains unresolved. CYDRA never invents missing rules or infers authorization from silence.

Program/rule state is mutable. Acquisition freshness, source version/context, and deterministic fingerprints must be retained so changes can trigger revalidation rather than silently leaving stale authority in force.

### Scope, system understanding, and contextual dependencies

Scope has three distinct meanings in the architecture:

1. **Authorization scope** — what CYDRA may actively test.
2. **Contextual acquisition scope** — what CYDRA may need to inspect/model to understand an authorized target.
3. **Security claim scope** — what CYDRA may assert as an eligible finding.

The governing invariant is:

> **Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.**

An out-of-scope component can therefore be acquired and analyzed as contextual dependency material when it interacts with an in-scope target. For example, if an `IN_SCOPE` Vault calls an `OUT_OF_SCOPE` Oracle, CYDRA may inspect the Oracle source, model the call/data-flow boundary, and reason about the Oracle's effect on the Vault. It may not automatically test the Oracle or promote a finding against it.

Context-only dependencies should retain explicit metadata such as `scope_status = OUT_OF_SCOPE`, `relationship = DEPENDENCY_OF_IN_SCOPE_TARGET`, and `usage = SYSTEM_MODEL_ONLY`. `UNKNOWN` remains unresolved. Contextual acquisition never expands active authority.

The canonical transition is:

`Discover → Acquire context → Classify scope → Model relationship → Request authorization if needed → Receive explicit grant → Plan authorized observation`

This supersedes any simplistic rule that only in-scope code may be acquired. **Only active testing and claim eligibility are scope-gated; system understanding may require out-of-scope contextual material.**

### System model and passive intake

`SystemModel` is the canonical persistent reasoning graph. `RepositoryAuditSession` composes repository recon and compiler-resolved Solidity AST recon through an atomic `Normalize → Stage → Project → Validate → Commit` boundary. Out-of-scope paths are not actively parsed and missing compiler artifacts remain unknown.

Each audit session persists normalized paths, scope decisions, source/artifact SHA-256 manifests, a deterministic intake fingerprint, and a distinct session identity. Persisted provenance is independently verifiable. Findings in session-backed graphs retain exact audit-session lineage.

`SystemModel.add_node()` is a canonical identity boundary: it inserts new nodes, treats exact duplicates as idempotent, and rejects conflicting content under an existing node ID without mutation.

### Solidity identity

Compiler-resolved AST relationships preserve separate identities for enclosing function declarations, referenced target declarations, and concrete AST expressions. Compiler declaration IDs are embedded in canonical identity when available. Missing declaration identity is explicitly marked unknown. AST projection is independently scope-checked so compiler artifacts cannot reintroduce out-of-scope structure.

### Invariants, hypotheses, and planning

Invariant candidates are proposals, not facts. Verification is `candidate → supported / contradicted / unresolved`, with explicit evidence. Only explicitly supported invariants enter the verified-invariant hypothesis bridge.

Planner hypotheses contain explicit probability, predictions, and state. Persistent hypotheses are canonical graph nodes. Test planning selects authorized observations by expected information gain per cost; invariant confidence never silently becomes planner probability.

### Bounded investigation control

`InvestigationController` is the authority-plane boundary for autonomous exploration. Each investigation has an immutable scope, finite rounds, observations, planning steps, hypotheses, execution-cost budget, dependency-depth limit, branching factor, and generation-tagged time lease. The controller can terminate explicitly for resolved/disproven hypotheses, established or blocked causal chains, budget exhaustion, depth limits, scope exhaustion, lease expiry, missing required evidence, or no high-value observation.

A planner can optimize only inside the issued envelope. It cannot acquire, extend, relax, or rewrite authority. Target and meta investigations are distinct domains; planner self-observation must use a separately scoped meta investigation. Persisted investigation snapshots carry an authority fingerprint and require an externally supplied matching fingerprint during recovery, so serialized state cannot enlarge its own budget or lease.

`investigation_expansion.py` provides the authority-plane boundary. `DependencyCandidate` records discovered cross-contract/dependency relationships without granting permission. `DependencyExpansionGrant` is externally issued and bound to the current authority fingerprint, explicit candidate identities, authorized dependency depth, and the observation scope being added. Unauthorized dependency metadata cannot self-authorize.

`BudgetDepthExpansionGrant` allows adaptive investigation to receive additional rounds, observations, planning steps, hypotheses, execution cost, dependency depth, or branching capacity only from external authority and only up to explicit absolute ceilings. The planner cannot replenish its own resources.

This design intentionally distinguishes **scope discovery** from **scope authorization**, and now also distinguishes **scope authorization** from **contextual understanding**. Cross-contract analysis may discover and model an unauthorized dependency for understanding, but it must stop at that boundary for active testing unless explicit authorization is granted.

### Economic reasoning

`economic_model.py` is a bounded simulation layer for complex economic attacks and DeFi-style interactions. `EconomicState` models canonical simulated balances, liabilities, and prices; `EconomicTransition` models deterministic value changes, fees, and slippage; `EconomicModel` bounds state/transition counts and scenario depth; `EconomicScenario` records a finite hypothetical path and attacker capital.

Economic reasoning may model reserves, balances, collateral, debt, prices/exchange rates, fees, incentives, liquidation conditions, attacker capital, slippage, and multi-step value transitions when those quantities are supplied as explicit model inputs. The model must reject non-finite numeric values and identity collisions.

A simulated profitable path is a hypothesis/model result, not evidence that an exploit executed. If CYDRA needs external confirmation, the resulting observation must pass the normal authorization, exact execution-request, gateway, durable-receipt, and receipt-bound evidence-ingestion boundaries. Economic modeling therefore expands reasoning capability without weakening execution authority.

### Persistent learning

`learning.py` is the bounded reusable-knowledge layer. It stores finding-derived records in five categories: invariant patterns, hypothesis patterns, observation patterns, dependency-discovery patterns, and budget/depth heuristics. Each record retains the originating finding identity, category, key/value, confidence, and deterministic learning identity.

`LearningStore.learn_from_finding()` accepts only explicitly supplied learning contributions from a verified finding context; it does not manufacture evidence or infer authority. Identical learning is idempotent while conflicting canonical identities are rejected. Per-category finite limits prevent uncontrolled knowledge growth.

`LearningStore.apply_candidates()` exposes matching prior knowledge to reasoning/planning without changing investigation authority. Learning fingerprints and export state are authority-independent: serialized learned state contains no permission, lease, grant, or execution capability. Rehydration/consumption of learning therefore cannot enlarge the current investigation envelope.

The persistent learning rule is: **CYDRA persists and applies learning from every investigation. Each finding enriches the invariant library, hypothesis library, observation patterns, dependency discovery, and budget/depth heuristics. Learning is bounded by the same authority plane—CYDRA cannot learn to self-authorize unbounded investigation, but it can learn to investigate more effectively within its envelope.**

### Evidence and belief updates

Evidence is immutable canonical fact/artifact state with provenance. `EvidencePolarity` is explicitly `supports`, `contradicts`, or `neutral` and is never inferred from posterior probability or hypothesis state.

Observation-driven belief updates persist hypothesis identity, prior/posterior probability and state, observed outcome, evidence identity, explicit polarity, transition explanation, graph relationships, and audit history. `record_update()` is a persistence primitive after canonical validation, not an external execution authority. `record_test_result()` is disabled.

### External execution boundary

`ReasoningOrchestrator` accepts only persisted authorized observation plans. External results must match exact observation execution identity and request digest, and result ingestion additionally requires an exact match to the durable canonical execution receipt. The canonical `ExecutionRequest` is deterministic and includes adapter, target, exact command, project fingerprint, authorization identity, scope status, execution identity, and adapter parameters.

`ExternalExecutionAdapter` requires canonical request construction, gateway-bound execution, and non-executing result rehydration. `ExternalExecutionResult` requires execution identity, request digest, outcome, and deterministic canonical payload. `validate_result_binding()` fails closed on identity, digest, outcome, or canonical-payload substitution.

`ExternalExecutionGateway` is the canonical execution boundary. It persists the request, verifies authorization and scope, enforces lifecycle/replay rules, delegates through a gateway-owned opaque capability, validates the exact returned result, persists an immutable receipt, and advances lifecycle state conservatively.

The orchestrator's result-ingestion boundary does not trust a result merely because it is request-bound. It reconstructs the expected durable receipt payload/fingerprint and requires exact equality to the canonical `execution_result:<request.digest>` node before converting the result into reasoning evidence. A substituted outcome or receipt field therefore fails closed before evidence or belief state can mutate.

### Concrete Foundry boundary

`FoundryRunner.execute()` is the canonical gateway-facing method. The runner is bound to an opaque capability object owned by the gateway when registered. Both `execute()` and the lower-level `run_test()` reject calls without that exact capability. This prevents a caller with a valid authorization and request digest from directly invoking Forge outside the gateway's request persistence, lifecycle, durable-receipt, and replay-protection boundary.

### Findings, PoCs, recovery, reports, and publication

The graph-aware finding gate validates canonical identities, explicit finding evidence support, causal verification, causal-trace connectivity, research-session provenance, and integrity state. Any retained audit-history/session machinery exists to protect the reliability of bug-bounty evidence, not to turn CYDRA into an audit-management product. Impact evidence must belong to the verified causal trace and explicitly support the finding hypothesis. Impact must be resolved and evidence-backed, and finding severity must match the canonical impact level.

Persisted findings are first-class graph nodes linked through `supported_by`, `about`, `traced_by`, and `originates_from`. Finding persistence repeats the claim-grounding invariants independently so lower-level callers cannot bypass promotion policy.

`poc.py` provides the first-class `POCArtifact` contract for the finding-demonstration layer. It reuses the canonical `Counterexample` rather than defining a second execution-result model, and adds canonical PoC identity, finding identity, hypothesis identity, canonical evidence IDs, expected violation, reproducibility notes, and execution-request identity. Validation is read-only and requires PoC evidence to remain inside the verified causal trace. A reproducible artifact must retain the canonical execution-request identity that produced its externally observed behavior.

`poc_persistence.py` makes PoCs first-class persistent graph state. `persist_poc()` validates the canonical recovered finding and causal trace before mutation and records explicit `demonstrates`, `for_hypothesis`, `uses_evidence`, and optional `derived_from_request` relationships. Duplicate PoC identities are rejected without mutation. `rehydrate_persisted_poc()` reconstructs the counterexample and PoC contract only from canonical persisted attributes, then revalidates finding/hypothesis identity, causal-trace evidence grounding, execution request lineage, graph semantics, audit history, and required graph edges. Recovery is read-only.

PoC artifacts are not execution authorities. CYDRA may formulate or present a PoC from verified reasoning, but any external demonstration must travel through the same authorized observation plan, exact execution request, canonical gateway, durable result receipt, and receipt-bound evidence-ingestion path. A PoC description, generated test, or code reference is never evidence that execution occurred until canonical external execution supplies the corresponding durable result.

Finding report data preserves finding evidence and impact evidence. Reproducibility manifests use schema `cydra.reproducibility.v3`, include impact evidence in the reasoning-node closure, and carry an independent deterministic claim fingerprint over report-facing finding claims. Verification is read-only and detects claim substitution/tampering as well as canonical graph or audit-history divergence.

Serialized finding nodes are transport state, not automatically trusted findings. `finding_recovery.py` rehydrates only persisted findings whose duplicated references agree, causal trace reconstructs, evidence explicitly supports the hypothesis, finding lineage edges exist, graph semantics remain valid, and audit state still corresponds to the canonical graph.

`finding_publication.py` is the final report trust boundary. `build_finding_publication()` first recovers the canonical persisted finding and then creates its reproducibility manifest, returning a trusted `FindingPublication`. Serialized input is represented first as `UntrustedFindingPublication` by strict parsing. That type cannot be passed to `verify_finding_publication()` as trusted state. Its explicit `verify()` method performs canonical recovery and reproducibility verification, then promotes only the canonical recovered finding plus a freshly rebuilt manifest into `FindingPublication`.

`verify_finding_publication_data()` is a read-only compatibility-style validation path that reports errors for untrusted serialized input without silently promoting it. `verify_and_trust_finding_publication_data()` is the explicit promotion API when a caller needs a trusted object. No publication parser, verifier, or promotion path executes external operations or mutates the reasoning graph.

A trusted publication is not an immortal authorization token. `verify_finding_publication()` revalidates the publication against the current canonical finding, reproducibility closure, and tamper-evident audit history. Canonical finding/evidence mutation or audit-state divergence therefore invalidates a stale publication rather than being silently absorbed. Verification never rewrites the graph or refreshes the stale object.

## Immunefi-first bug-bounty doctrine

When a design decision is ambiguous, CYDRA must prefer the interpretation that improves **authorized Immunefi bug discovery** while preserving evidence and scope correctness.

- Program rules, impact taxonomy, affected assets, exclusions, known issues, testing restrictions, deployment/version requirements, and PoC requirements are engagement-specific inputs, not generic assumptions.
- Smart-contract and DeFi reasoning is a first-class capability, not an optional afterthought. Economic state, token flows, permissions, oracle dependencies, cross-contract calls, upgradeability, accounting invariants, liquidation paths, and trust boundaries should be modeled when relevant to the target.
- An out-of-scope dependency may be inspected and modeled when necessary to understand an in-scope protocol component, but it is never silently promoted into an independently testable or bounty-eligible target.
- A suspicious pattern is not a bug. CYDRA must establish the violated security property and causal impact before promoting a finding.
- A mathematically interesting economic path is not a bug until the relevant protocol assumptions, executable behavior, authorization, and bounty eligibility are verified.
- Known issues and program exclusions must affect finding eligibility, but they must not become hidden vulnerability labels used to steer blind reasoning.
- The final output should answer the bug-bounty questions: **What is wrong? Where is it? Why does it happen? How can it be reproduced? What security impact does it cause? Why is it eligible under the program rules?**

## Investigation profiles

Investigation profiles are policy presets, not authority escalators. The intended profile vocabulary is:

- `STANDARD` — normal bounded repository reasoning.
- `ECONOMIC` — enables bounded economic state/scenario modeling within issued authority.
- `CROSS_CONTRACT` — prioritizes dependency discovery and explicitly authorized dependency expansion while allowing contextual modeling of dependencies needed to understand an in-scope target.
- `DEEP_ANALYSIS` — uses additional externally granted budget/depth when the initial envelope is insufficient.
- `COMBINED` — combines the above reasoning capabilities while preserving one authoritative scope/ceiling.

A profile may influence planning priorities, but selecting a profile never grants new scope, execution capability, budget, or depth by itself.

## End-to-end status

v1.69 added the executable Foundry fixture and deterministic integration regression through finding persistence.
v1.70 hardened real Foundry execution authorization and provenance.
v1.71 added live Foundry CI execution.
v1.72 made result authenticity fail closed when authorization provenance is missing.
v1.73 bound external results to exact observation execution identity.
v1.74 added exact execution-request digesting and provenance.
v1.75 made execution requests first-class persistent graph state.
v1.76 added the adapter-neutral external execution contract.
v1.77 made that contract operational through one canonical gateway.
v1.78 added persistent lifecycle, durable result receipts, replay protection, and conservative recovery.
v1.79 added fresh-process result rehydration without external re-execution.
v1.80 disabled the legacy direct result-ingestion bypass.
v1.81 hardened canonical node identity and added passive self-dogfooding.
v1.82 closed the scope-safe AST evidence ingestion path.
v1.83 hardened compiler declaration identity.
v1.84 hardened verified invariant → hypothesis promotion.
v1.85 hardened planner semantics and observation identity.
v1.86 enforced one-to-one observation → execution-request binding.
v1.87 bound result receipts to canonical requests.
v1.88 registered `executes_request` in graph semantics.
v1.89 required durable receipts before external evidence mutation.
v1.90 added production relation-semantics dogfooding.
v1.91 hardened causal verification anchors.
v1.92 aligned finding gate and persistence with causal verification.
v1.93 added finding audit-session lineage coverage.
v1.94 bound audit events to canonical graph-state digests.
v1.95 added independent execution lifecycle ↔ audit correspondence and fail-closed recovery checks.
v1.96 closed standalone Foundry execution without canonical request identity/digest.
v1.97 closed the remaining concrete-adapter bypass with a gateway-owned opaque execution capability.
v1.98 hardened durable execution reconciliation and lifecycle-history completeness.
v1.99 grounded finding evidence in the verified causal trace.
v1.100 grounded finding impact claims in the verified causal trace and bound severity to canonical impact level.
v1.101 bound reproducibility manifests to report-facing claims and impact evidence.
v1.102 added the explicit persisted-finding recovery boundary and audit-state correspondence checks for serialized finding rehydration.
v1.103 added the trusted finding publication boundary, binding publication claims to the canonical recovered finding and reproducibility manifest.
v1.104 added strict publication transport parsing and a direct verification path for untrusted serialized publication data.
v1.105 separated parsed publication transport from trusted publication state and made canonical verification the explicit promotion transition.
v1.106 hardened publication freshness by rejecting previously trusted publications after canonical finding/evidence mutation or audit-state divergence.
v1.107 closed durable execution receipt substitution during observation-result ingestion by requiring exact canonical receipt equality before evidence mutation.
v1.108 made PoC artifacts first-class finding-demonstration state, binding PoC identity and evidence to the finding/hypothesis lineage and preserving canonical execution-request identity for reproducible demonstrations.
v1.109 made PoCs first-class persistent graph state with canonical identity, explicit lineage relations, and a read-only persisted-PoC recovery boundary.
v1.110 added the bounded autonomous investigation control plane with finite authority budgets, dependency depth, branching limits, generation-tagged leases, explicit termination, target/meta separation, and authority-fingerprinted recovery.
v1.111 added bounded economic simulation plus externally authorized dependency-scope and adaptive budget/depth expansion. These capabilities increase reasoning depth without allowing complexity to grant authority.
v1.112 added persistent bounded finding-derived learning for invariant, hypothesis, observation, dependency, and budget/depth knowledge while keeping learned state authority-independent.

Known-issue eligibility is now version- and asset-aware: an exact declared issue identity can block bounty promotion only when its program-declared applicability matches the candidate. Resolved, contextual, or otherwise non-blocking historical knowledge remains available for reasoning without silently converting context into an exclusion.

The program-intake/context architecture is now a canonical implemented boundary: Immunefi-first program acquisition, adapter-based resource collection, linked-resource dependency tracking, explicit unresolved-resource state, exact repository/version acquisition, and the distinction between active authorization scope and contextual system understanding. Canonical program/resource evidence, provenance-bound program contracts, unresolved-resource gating, and canonical SystemModel persistence are now implemented. Live Immunefi evaluation is used to validate intake behavior before deeper reasoning work proceeds.

GitHub Actions validation remains subject to the repository's current Actions capacity; status must be confirmed from the actual workflow run rather than inferred.

## Production acceptance target

`Immunefi Program Discovery → Program Acquisition → Rule/Impact/Scope Extraction → Relevant Reference Discovery → Resource Dependency Graph → Audit/Known-Issue Context → Canonical Program Contract → Source/Deployment Acquisition → Scope Classification → Program Contract → Authorized Target → Recon → Persistent System Model → Security Invariants → Evidence → Competing Security Hypotheses → Information-Gain Plan → Bounded Investigation Authority → Exact Execution Request → Canonical Adapter Gateway → Authorized Execution → Durable Result Receipt → Receipt-Bound Evidence → Belief Update → Contradiction Handling → Causal Verification → Verified Bug → Finding Gate → Persistent Finding → PoC Artifact → PoC Reproducibility → Immunefi-Ready Finding`

For contextual dependencies, the acceptance path is:
`In-Scope Target → Dependency Discovery → Contextual Acquisition → Explicit OUT_OF_SCOPE/UNKNOWN Classification → SystemModel Relationship → Reasoning`

For an out-of-scope dependency to become actively testable, the path must additionally be:
`Dependency Candidate → External Scope/Authorization Grant → Bounded Investigation Authority → Authorized Observation`

For complex economic/cross-contract investigations, the reasoning target additionally supports:
`Dependency Discovery → External Scope Authorization → Bounded Economic/Cross-Contract Modeling → High-Information Observation Selection → Exact Authorized Execution`

For contest workflows requiring a PoC for each finding, the acceptance target is:
`Verified Bug → PoC Lineage Validation → Persistent PoC → Authorized Demonstration Plan → Exact Execution Request → Durable Result Receipt → Receipt-Bound Evidence → PoC Recovery/Revalidation → Reproducibility Verification → Immunefi-Ready Submission Artifact`

For persistent learning, the acceptance target is:
`Verified Finding → Learning Extraction → Provenance-Bound Learning Records → Bounded Learning Store → Future Candidate/Plan Ranking → Same Authority Envelope`

Every transition must preserve provenance, uncertainty, canonical identity, and reconstructable reasoning state.

## Agent operating rules

- Inspect current branches, pull requests, commits, and CI before architectural changes.
- Reuse appropriate branches; do not duplicate implementations.
- Prefer explicit identities and evidence over inferred relationships.
- Preserve unknown and unresolved states.
- Validate prospective graph state before mutation where a boundary can fail.
- Treat CI failures as evidence and fix root causes.
- Never claim CI success without actual repository evidence.
- Keep the canonical graph as the system of record.
- Security conclusions must never be inferred from provenance metadata alone.
- Execution remains external to the reasoning orchestrator and concrete adapters must remain gateway-bound.
- Treat serialized findings as untrusted until the recovery boundary succeeds.
- Treat serialized publication bundles as untrusted until strict transport parsing and canonical verification succeed.
- Never equate successful parsing with trust; parsed publication transport must remain explicitly untrusted until canonical verification.
- Treat report publication as a separate trust boundary from finding persistence and reproducibility generation.
- Treat a trusted publication as a revalidatable snapshot, not a permanent authority token; reject stale canonical state rather than silently refreshing it.
- Treat externally executed results as untrusted until they match the exact durable canonical receipt before evidence ingestion.
- Treat a PoC as a causal demonstration artifact tied to a specific finding and hypothesis, not as proof by itself.
- Require PoC evidence to remain grounded in the verified causal trace and preserve canonical execution-request identity for reproducible demonstrations.
- Treat persisted PoCs as canonical graph state, not detached report metadata; recover them only through the dedicated PoC recovery boundary.
- Never claim a PoC was executed unless the canonical execution boundary produced the corresponding durable receipt and receipt-bound evidence.
- Never bypass scope, authorization, gateway, lifecycle, or receipt verification merely to make a PoC succeed.
- Autonomous investigation must remain bounded by externally issued scope, budgets, depth, branching, and lease authority.
- Complexity may justify a request for more authority, but complexity, planner confidence, economic profitability, or dependency discovery can never grant that authority.
- **Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.**
- Out-of-scope dependencies may be acquired and modeled when necessary to understand an in-scope target, but their scope status must remain explicit and they cannot become active targets without authorization.
- Contextual acquisition is not scope expansion. Public readability, repository access, dependency discovery, or an LLM classification cannot grant testing authority.
- Program acquisition must use the canonical adapter architecture. Acquisition adapters are evidence producers, not authorities.
- For Immunefi workflows, prefer authoritative/API acquisition and authorized MCP/API adapters; use bbscope as a non-authoritative scope adapter and controlled web/document retrieval as fallback.
- Follow relevant program-linked resources with bounded, explainable reference traversal. Track required-but-unresolved resources rather than silently omitting them.
- Preserve exact repository branch/tag/release/commit identity and program-required deployment/version context.
- Never treat cached, mirrored, normalized, or stale program material as current authority without revalidation.
- Target investigations must not recursively expand into planner/meta investigations. Use a separate meta investigation with its own authority envelope.
- Do not turn unresolved uncertainty into an excuse for unbounded retries. Stop explicitly when authority, information value, required evidence, or lease constraints say to stop.
- Learning is part of the persistent investigation loop: every verified finding should be considered for reusable invariant, hypothesis, observation, dependency, and budget/depth knowledge.
- Learning records must retain finding provenance and explicit uncertainty; do not promote heuristics to facts without verification.
- Applying learning may change prioritization and reasoning effectiveness, but never authority. A learned pattern cannot grant scope, budget, depth, lease, execution capability, or an expansion grant.
- Learning storage and application must remain finitely bounded and deterministic; serialized learning state must not contain authority-grant semantics.
- For contest workflows, determine the contest's PoC requirements before marking a finding contest-ready; do not assume every engagement has identical submission rules.

## Change discipline

Prefer focused commits and reversible changes. Never rewrite history or force-push unless explicitly requested by the repository owner.

For substantial changes, use a feature branch and pull request rather than directly modifying the stable branch.

## Testing standard

Tests must cover both ordinary behavior and adversarial reasoning cases. For reasoning components, test contradictions, missing evidence, competing hypotheses, uncertainty preservation, deterministic updates, provenance, and regression behavior where applicable.

For autonomous investigation control, test recursive prerequisite chains, scope escape, target→meta recursion, budget exhaustion during planning and execution, execution-cost limits, lease expiry, stale generation/recovery, duplicate execution identities, low-information termination, hypothesis-budget exhaustion, and attempts to mutate authority through serialized snapshots.

For authority expansion, test unauthorized dependency discovery, stale authority fingerprints, dependency-depth ceilings, absolute budget/depth ceilings, and attempts to use planner state as an authority grant.

For program intake/contextual acquisition, test missing required resources, unresolved linked rules, conflicting authoritative sources, stale program state, unvalidated LLM scope normalization, cache/source substitution, unauthorized scope expansion from dependency discovery, out-of-scope contextual dependencies, `UNKNOWN` scope, exact repository revision binding, resource provenance/fingerprint integrity, and required-resource completion gating.

For economic modeling, test deterministic state identity, conflicting identity rejection, finite numeric validation, state/transition budgets, scenario depth, attacker-capital limits, transition-chain integrity, and the explicit distinction between simulation and external execution evidence.

For learning, test finding provenance, deterministic learning identity, idempotent replay, conflicting identity rejection, category limits, invalid confidence, deterministic fingerprints, persistence/export shape, and attempts to turn learned state into authority grants.

For PoCs, test finding/hypothesis identity binding, causal-trace evidence grounding, missing execution identity for reproducible artifacts, deterministic serialization, canonical persistence/recovery, lineage-edge integrity, duplicate identity rejection, and the distinction between describing a reproduction and claiming that it was executed.

## Completion standard

A feature is done only when implementation, tests, architecture, documentation, and invariants agree. Passing unit tests alone is insufficient.

## 2026-09-04 Intake Evaluation Checkpoint

The Immunefi intake boundary has now been exercised end-to-end against the captured current 0x program material. The evaluation uses the production acquisition/parser/dependency-graph path with deterministic captured transport. Contextual references are preserved without widening authorization. The next engineering boundary is to freeze intake semantics and begin the blind historical Immunefi reasoning evaluation rather than continuing intake-only refinement.
