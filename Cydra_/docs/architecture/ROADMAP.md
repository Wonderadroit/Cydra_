# CYDRA Architecture Roadmap

## Mandatory investigation pipeline

`Scope & Authorization → Recon/System Model → Invariants → Evidence → Correlation/Uncertainty → Competing Hypotheses → Information-Gain Planning → Authorized Observation → Hypothesis Update → Causal Verification → Finding`

## Phase 0 — Scope & Constraint Gateway

The gateway is mandatory before active investigation. It parses declared scope, authorization constraints, exclusions, conditional targets, known issues, and relevant repository/specification boundaries. Scope states are `IN_SCOPE`, `OUT_OF_SCOPE`, `CONDITIONAL`, and `UNKNOWN`. `OUT_OF_SCOPE` is hard-blocked; `UNKNOWN` is never silently treated as authorized.

## Phase 1 — Structural Recon / System-Model Initialization

Recon converts the target into a provenance-aware model of assets, components, entry points, identities, access controls, state-changing paths, trust boundaries, data flows, dependencies, contracts, configuration, and invariants. Recon is not merely a file listing.

## Phase 2 — Reasoning

The existing hypothesis planner/updater becomes downstream of the system model and scope gateway. Predictions, observations, costs, authorization, evidence strength, and uncertainty must remain explicit.

## Phase 3 — Causal Verification

Build causal chains from observed behavior through violated invariants to security impact. Correlation alone is insufficient for a final finding.

## Phase 4 — Findings

A finding requires sufficient evidence, provenance, competing-hypothesis consideration, causal support, reproducibility, and scope/authorization validity.

## Phase 5 — Repository Test & Verification Backends

CYDRA may delegate approved verification to local analysis tools. Foundry is an execution backend, not a source of truth. A passing fuzz/invariant run is recorded as an observation and does not prove the absence of a vulnerability. A failing run can produce a counterexample that becomes evidence for hypothesis updating.

POC artifacts must preserve the test name, input, trace, expected violation, and reproducibility state. Future work includes counterexample minimization and automatic generation of focused Foundry tests from validated hypotheses.

## Near-term implementation order

1. Formal scope/authorization data model and gateway.
2. Recon data model and repository structural extractor.
3. Persistent system graph linking recon facts to invariants.
4. Evidence and observation models with provenance.
5. Integrate existing planner/updater with scope, evidence, and graph state.
6. Known-issue baseline ingestion and duplicate-finding suppression.
7. Adversarial/regression tests for boundary enforcement and reasoning integrity.
8. Foundry execution adapter and structured counterexample ingestion.
9. Invariant/fuzz test generation and counterexample minimization.
10. Causal verification and reproducible finding/POC generation.
