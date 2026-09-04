# CYDRA Development Milestones

## v1.16 — Hypothesis Updating

Baseline reasoning loop for competing hypotheses and belief updates.

## v1.17 — Persistent System Model

**Current development milestone.**

### Completed/under development

- persistent graph model
- graph persistence and validation
- reasoning graph integration
- repository source inventory
- initial Solidity structural model
- scope/contest constraints
- known-issue representation
- Foundry execution boundary
- counterexample representation
- evidence-backed causal verification
- conservative finding promotion gate
- impact assessment and finding model

### Acceptance criteria

The milestone is complete only when the above components operate as one tested workflow and the repository can demonstrate provenance from source observation through hypothesis, authorized test execution, evidence, causal verification, impact assessment, and finding promotion.

## v1.18 — Integrated Repository Audit Workflow

Planned after v1.17 acceptance:

- compiler/AST-backed Solidity semantics
- automatic graph population from repository structure
- invariant candidate generation
- rule-aware test planning
- Foundry fuzz/invariant execution against real fixtures
- execution-aware counterexample shrinking
- POC reproducibility and artifact capture
- end-to-end regression corpus

## v1.x hardening

- adversarial self-tests
- differential testing against independent analyzers
- performance benchmarks
- deterministic replay
- failure-safe behavior
- documentation and stable CLI/API contracts
