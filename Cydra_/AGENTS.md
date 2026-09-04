# CYDRA Agent Operating Contract

This file applies to AI coding agents working in the CYDRA repository.

## Authority

`CYDRA_PROJECT_BIBLE.md` is the architectural source of truth. If an implementation request conflicts with it, stop and surface the conflict instead of silently changing the architecture.

## Operating Protocol

Before modifying code:

1. Inspect the repository structure.
2. Read `CYDRA_PROJECT_BIBLE.md`.
3. Read relevant architecture and tests.
4. Identify affected invariants and dependencies.
5. State the intended change and its architectural impact.
6. Make the smallest coherent change.
7. Add or update regression tests.
8. Run the relevant test suite.
9. Inspect the resulting diff for unintended changes.
10. Report changed files, tests, failures, and remaining uncertainty.

## Architectural Rules

- Do not invent evidence.
- Do not silently discard contradictory evidence.
- Do not equate unknown with false.
- Do not convert correlation into causation.
- Preserve evidence provenance.
- Preserve uncertainty through transformations.
- Keep hypotheses explicit and competing where appropriate.
- Every test-selection mechanism must have an explainable reason.
- Do not create duplicate state models when an existing persistent model can represent the concept.
- Avoid hidden global state.
- Avoid speculative abstractions that are not required by the current architecture.
- Do not weaken tests merely to make an implementation pass.
- Do not modify unrelated modules without documenting why.
- Security testing functionality must remain within authorized-use boundaries.
- Autonomous investigation is bounded: scope, budget, dependency depth, and lease are authoritative constraints, not planner suggestions.
- Planning consumes finite budget; a planner cannot evade limits by generating more candidate branches.
- A target investigation cannot authorize or recursively acquire a meta-investigation. Planner self-observation belongs to a separately scoped meta-investigation with its own authority envelope.
- The planner may optimize information gain per cost, but it cannot acquire, extend, relax, or rewrite scope, budget, lease, or termination authority.
- Uncertainty is a valid terminal condition. Budget exhaustion, lease expiry, depth limits, scope exhaustion, missing required evidence, and diminishing information value must remain explicit outcomes rather than triggers for unbounded retry.
- Persisted investigation authority must be recovered against an externally trusted authority fingerprint; a serialized snapshot cannot grant itself a longer lease or larger budget.
- Every external observation request must remain bound to the active investigation context before it reaches the execution gateway.
- Complexity may justify requesting additional authority; complexity can never grant additional authority.
- Dependency expansion is an explicit authorization event, not automatic ecosystem discovery. A discovered import, library, token, router, oracle, callback, or cross-contract call remains outside the active scope until an external authority issues a valid expansion grant.
- Dependency expansion grants are bound to the current authority fingerprint, must identify the authorized dependency candidates, and must respect an externally granted dependency depth. Discovery metadata cannot self-authorize scope.
- Adaptive budget/depth expansion requires an external grant with an absolute ceiling. The planner cannot multiply, replenish, or otherwise extend its own budget.
- **Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.**
- Out-of-scope components may be acquired and modeled as contextual dependencies when needed to understand an in-scope target, but they remain out of scope for active testing and cannot independently become eligible findings.
- Contextual dependency nodes must retain explicit scope status, relationship to the in-scope target, provenance, and system-model-only usage where applicable.
- `UNKNOWN` scope must remain unresolved and cannot be silently treated as either in-scope or out-of-scope.
- Acquiring code, documentation, public state, or deployment metadata never grants execution authority. Public availability is not authorization.
- Program scope/rules must be acquired through the canonical program-intake architecture. Acquisition adapters are mechanisms, not authorities.
- For Immunefi-first workflows, prefer authoritative/API acquisition and authorized MCP/API adapters; use scope aggregators such as bbscope as non-authoritative adapters and controlled web/document retrieval as fallback.
- Relevant linked program resources must be tracked as dependencies. Required but inaccessible resources remain explicitly unresolved; agents must not guess missing rules or authorization.
- LLM-normalized scope is a proposal until validated against authoritative source material. Cached or mirrored scope is provenance-bearing evidence, not silently current authority.
- Program/rule changes must trigger revalidation of dependent intake state rather than silently reusing stale authority.
- Repository acquisition must preserve exact repository and revision identity; do not assume a default branch is the bounty-eligible or deployed version.
- Use source-specific GitHub acquisition/API mechanisms where available instead of generic HTML scraping for repository understanding.
- Economic reasoning is simulation state, not execution evidence. A simulated profitable path, price movement, balance delta, liquidation path, or attacker P/L estimate never proves that an external action occurred.
- Economic models must remain bounded by explicit state, transition, scenario-depth, scenario-count, and attacker-capital limits and must reject non-finite numeric state.
- Economic assumptions must remain explicit and deterministic; do not silently convert a hypothetical price, reserve, fee, incentive, collateral, debt, or capital assumption into observed evidence.
- Complex economic or cross-contract analysis must use the same authorization, scope, execution-gateway, durable-receipt, and evidence-ingestion boundaries as ordinary investigations.
- Learning is persistent and finding-derived: verified investigations may enrich the invariant library, hypothesis library, observation patterns, dependency-discovery patterns, and budget/depth heuristics.
- Learning must preserve finding provenance and explicit uncertainty; it must never invent evidence or silently convert a heuristic into a fact.
- Learning is bounded by explicit finite storage/knowledge limits and the same authority plane as investigation. Learned heuristics may improve planning inside the issued envelope but can never create, extend, relax, or self-authorize scope, budget, depth, lease, execution capability, or other authority.
- Applying learned knowledge is a reasoning/planning operation, not an authority transition. Any authority increase still requires an externally issued grant.
- A proof-of-concept is a causal demonstration artifact, not a decorative report attachment.
- A PoC must identify the finding and hypothesis it demonstrates and use only evidence grounded in the verified causal trace.
- A PoC description must distinguish prerequisites, demonstration steps, and expected observations; it must never imply that CYDRA executed an external action when it did not.
- Reproducible PoCs must retain the canonical execution-request identity that produced their externally observed behavior.
- PoC parsing/presentation must not manufacture verification; external execution results must pass the same canonical gateway, durable-receipt, and evidence-ingestion boundaries as every other observation.
- Persisted PoCs are first-class graph state: they require canonical PoC identity, finding/hypothesis lineage, causal-trace evidence grounding, and explicit graph relationships.
- PoC recovery must reconstruct only from canonical persisted state and reject ID rebinding, detached evidence, missing lineage edges, malformed counterexamples, and audit-history divergence.
- A PoC must never become an execution authority merely because it is persisted or recovered.
- Do not generate or execute an exploit merely because a suspicious pattern exists; first establish an authorized, sufficiently supported hypothesis and an observation that can distinguish it.

## Change Discipline

Prefer focused commits and reversible changes. Never rewrite history or force-push unless explicitly requested by the repository owner.

For substantial changes, use a feature branch and pull request rather than directly modifying the stable branch.

## Testing

Tests must cover both ordinary behavior and adversarial reasoning cases. For reasoning components, test contradictions, missing evidence, competing hypotheses, uncertainty preservation, deterministic updates, provenance, and regression behavior where applicable.

For autonomous investigation control, test recursive prerequisite chains, scope escape, target→meta recursion, budget exhaustion during planning and execution, execution-cost limits, lease expiry, stale generation/recovery, duplicate execution identities, low-information termination, hypothesis-budget exhaustion, and attempts to mutate authority through serialized snapshots.

For authority expansion, test unauthorized dependency discovery, stale grant fingerprints, candidate identity mismatch, dependency-depth ceilings, absolute budget/depth ceilings, and attempts to use planner state as an authority grant.

For program intake and contextual acquisition, test missing required resources, unresolved linked rules, conflicting authoritative sources, stale program state, unvalidated LLM scope normalization, cache/source substitution, unauthorized scope expansion from dependency discovery, out-of-scope contextual dependencies, `UNKNOWN` scope, exact repository revision binding, and resource provenance/fingerprint integrity.

For economic modeling, test deterministic state identity, conflicting identity rejection, finite numeric validation, state/transition budgets, scenario depth, attacker-capital limits, transition-chain integrity, and the explicit distinction between simulation and external execution evidence.

For learning, test finding provenance, deterministic learning identity, idempotent replay, conflicting identity rejection, category limits, invalid confidence, deterministic fingerprints, persistence/export shape, and attempts to turn learned state into authority grants.

For PoCs, test finding/hypothesis identity binding, causal-trace evidence grounding, missing execution identity for reproducible artifacts, deterministic serialization, canonical persistence/recovery, lineage-edge integrity, duplicate identity rejection, and the distinction between describing a reproduction and claiming that it was executed.

## Completion Standard

A feature is done only when implementation, tests, architecture, documentation, and invariants agree. Passing unit tests alone is insufficient.
