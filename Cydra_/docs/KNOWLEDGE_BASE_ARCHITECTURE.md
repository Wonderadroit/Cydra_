# CYDRA Knowledge Base Architecture

This document makes the reusable-knowledge design explicit without replacing the canonical SystemModel, authority plane, execution gateway, or evidence model.

## Design decision

The Knowledge Base is a **reasoning layer**, not an authority layer.

`Verified Finding → Learning Extraction → Provenance-Bound Learning → Knowledge Base → Candidate/Plan Ranking → Same Authority Envelope`

Knowledge may improve what CYDRA considers valuable. It may never decide what CYDRA is allowed to do.

## Five knowledge classes

| Class | Examples | Source | Authority effect |
|---|---|---|---|
| Invariants | balance/value, owner/caller, flash-loan price-impact, multi-contract consistency | architectural seeds or verified findings | none |
| Hypotheses | reentrancy, oracle manipulation, state desync, economic arbitrage | architectural seeds or verified findings | none |
| Observation patterns | flash-loan + price-change simulation, A→B→A, multiple attackers | architectural seeds or verified findings | none |
| Dependency patterns | contract→oracle/token, router→pool, aggregator→multiple pools | discovery/verified findings | none |
| Budget profiles | economic attack 200 observations/depth 5; cross-contract 150/depth 4 | heuristic seed or verified findings | recommendation only |

## Provenance rule

The initial framework entries are marked `architectural_seed`. They are **not** falsely presented as findings learned from past investigations.

Finding-derived entries require an exact `source_finding_id`. Existing `LearningStore` records are projected into the Knowledge Base as `finding_derived` records while preserving confidence and finding provenance.

## Economic capability

Economic modeling has two independent limits:

1. **Scenario depth/count/state/transition limits** bound model complexity.
2. **Economic simulation budget** bounds the amount of simulation work consumed by scenario construction.

Attacker capital is separately bounded. A profitable `EconomicAssessment` remains simulated-only and cannot become execution evidence or grant execution authority.

If external confirmation is required, CYDRA returns to the canonical observation → exact request → gateway → durable receipt → receipt-bound evidence path.

## Cross-contract capability

Cross-contract analysis is discovery-first:

`Dependency Discovery → Expansion Request → External Approval/Deny → Approved Grant → Scope Expansion`

A discovered `DependencyCandidate` is not permission. A denied request cannot become a grant. An approval must bind to the exact request fingerprint and then enters the existing `DependencyExpansionGrant` boundary, which still requires the live authority fingerprint and cannot be replayed.

## Adaptive depth and budget

Budget profiles are recommendations. They can say that an economic attack is worth up to 200 observations and depth 5, or that cross-contract analysis is worth 150 observations and depth 4. They cannot change the live controller.

Actual expansion remains:

`Current Authority → External Grant → Absolute Ceiling Check → New Authority`

Complexity, profitability, knowledge confidence, or planner ranking can request more authority, but none can grant it.

## Capability profiles

`STANDARD`, `ECONOMIC`, `CROSS_CONTRACT`, `DEEP_ANALYSIS`, and `COMBINED` select reasoning capabilities. They are policy labels, not authority tokens.

The Knowledge Base can filter knowledge by capability profile, while the planner still applies the ordinary authorization and information-gain gates first.

## Planner integration

Knowledge-aware planning uses an immutable `KnowledgeContext` containing:

- investigation identity
- live authority fingerprint
- lease generation
- authority-independent Knowledge Base fingerprint

Mutation of the knowledge basis invalidates the context. Knowledge can add a bounded ranking bonus only after the observation is already eligible. It cannot make an unauthorized observation executable.

## Security invariant

> **Knowledge changes prioritization, never permission.**

This preserves CYDRA's existing separation:

`Authority Plane ≠ Reasoning Plane ≠ Execution Plane`

The Knowledge Base belongs to the reasoning plane. `InvestigationController` remains the authority plane. `ExternalExecutionGateway` remains the execution boundary. Evidence and findings remain canonical graph state.
