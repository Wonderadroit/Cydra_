# CYDRA Development Checkpoint

This file is the durable handoff point for autonomous development across chats and sessions.

## Current repository state

- Repository: `Wonderadroit/CYDRA`
- Active PR: `#58`
- PR branch: `feat/v1.97-gateway-execution-capability`
- PR state: open, unmerged
- Current branch head: `09c18b6e1553e941a045cf2c32675dd91c0c85c4`
- Recent commits: `ed491f24` (security-claim provider), `9e8cc2dd` (autonomous-driver integration), `09c18b6e` (provider regression tests)

If conversation history is unavailable, inspect this file first, then inspect `CYDRA_PROJECT_BIBLE.md`, `AGENTS.md`, PR #58, current workflow runs, and the latest benchmark artifacts before changing code.

## Mission and architectural boundary

CYDRA is an authorized security-research reasoning engine. It must understand system behavior and produce evidence-grounded, causally verified findings rather than memorize vulnerability labels.

Canonical chain:

`System behavior → invariants → evidence → competing hypotheses → information-gain testing → observation → belief update → persistent system model → causal verification → finding`

Repository chain begins with program discovery/intake and scope classification and ends with trusted publication. Authorization, scope, evidence provenance, uncertainty, causal verification, bounded investigation, durable execution receipts, and finding-gate invariants are non-negotiable.

**Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.** Out-of-scope dependencies may be acquired and modeled contextually when necessary to understand an in-scope target, but cannot be actively tested or independently claimed without explicit authorization. `UNKNOWN` is unresolved and cannot silently become authorization.

Complexity may justify requesting additional authority; complexity can never grant additional authority. Learning is authority-independent and cannot grant scope or execution capability.

## Completed immediately before this checkpoint

1. Canonical program-intake/context architecture was documented.
2. Immunefi-first program acquisition, linked-resource dependency tracking, source/version identity, and acquisition-versus-authority boundaries were documented.
3. Scope-versus-understanding rules were documented in the Project Bible, README, and scope/recon architecture specification.
4. Blind historical benchmarking is sealed and oracle-free until post-run evaluation.
5. Finding synthesis and the `FindingDraftProvider` boundary exist, but they do not infer vulnerabilities themselves.
6. `SecurityClaimReasoner` now adjudicates explicit security claims only after supported hypotheses, canonical supported invariants, intact causal verification, supporting evidence, resolved impact, severity/impact agreement, scope, and hypothesis resolution all pass.
7. `SecurityClaimDraftProvider` converts explicit claim contracts stored on canonical hypotheses into rules and routes emitted drafts through the existing finding synthesis/gate path.
8. `AutonomousInvestigationDriver` now uses `SecurityClaimDraftProvider` by default while retaining injectable specialized providers.
9. Regression coverage proves the provider does not infer a finding from relationships without an explicit claim contract.

## Latest validation

For current head `09c18b6e1553e941a045cf2c32675dd91c0c85c4`:

- **CYDRA CI #1246: SUCCESS**.
- **Blind Historical Baselines #95: SUCCESS**.
- Predy 2024-05 sealed artifact: produced successfully.
- Size 2024-06 sealed artifact: produced successfully.
- No external execution was triggered by the blind benchmark.

### Predy 2024-05

- Frozen revision: `a9246db5f874a91fb71c296aac6a66902289306a`
- Hypotheses: 32
- Proposed observations: 32
- Planning steps: 1
- Executed observations: 0
- Promoted findings: 0
- Candidate findings: 0

### Size 2024-06

- Frozen revision: `4c61f1a5d07e3a201c1990546dd8905b2d2ddf92`
- Hypotheses: 27
- Proposed observations: 27
- Planning steps: 1
- Executed observations: 0
- Promoted findings: 0
- Candidate findings: 0

The current two-case artifacts remain zero-candidate reasoning baselines. They are not security claims. Historical oracle annotations must only be applied after candidate artifacts are sealed and must never be supplied to CYDRA during blind reasoning or used to manufacture drafts.

## What the current baseline tells us

The reasoning stack successfully constructs canonical relationship hypotheses and proposes verification observations. The blind benchmark intentionally stops before external observation execution, so the current sealed runs cannot legitimately produce causally verified findings. The new security-claim component is therefore exercised primarily through unit/integration fixtures rather than historical benchmark findings.

The new component is deliberately an **adjudication boundary**, not a vulnerability detector: explicit semantic claim contracts are supplied by the reasoning layer, and the reasoner decides whether canonical state is sufficient to materialize a finding draft. It does not yet constitute a broad vulnerability-class generator.

## Current engineering target

Strengthen the security-claim reasoning layer so it can consume sufficiently verified canonical security predicates and produce explicit, contest-independent claim contracts without relying on historical findings or pattern-matching oracle answers.

Target flow:

`Canonical evidence-backed relationships → security-relevant invariant/contradiction reasoning → explicit security predicate/claim contract → causal/evidence requirements → finding synthesis → existing graph-aware finding gate`

The next implementation should especially ensure that required invariants are semantically bound to the claim hypothesis (not merely present and supported), preserve competing hypotheses and unresolved state, and keep impact/severity as explicit evidence-backed claim data rather than heuristic inference.

## Evaluation gate

1. Keep normal unit/integration CI green.
2. Preserve the sealed Predy and Size baselines.
3. Add diverse historical contests before tuning reasoning logic.
4. For each new blind case, inspect sealed artifacts before semantic comparison.
5. Apply independently curated semantic annotations only after sealing.
6. Calculate TP/FP/FN and failure classes per case and in aggregate.
7. Inspect every candidate's hypothesis/evidence/causal/provenance grounding before treating metrics as meaningful.
8. Only after multiple diverse cases establish a baseline should detector/reasoning tuning occur.

## What must not happen next

- Do not consult historical oracle data while constructing or executing blind reasoning.
- Do not manufacture finding drafts from known historical findings.
- Do not turn canonical relationship names into vulnerability labels merely by pattern matching.
- Do not bypass the finding gate.
- Do not allow learning to grant authority.
- Do not execute external actions during a reasoning-only benchmark unless explicitly authorized by the benchmark design.
- Do not modify sealed benchmark artifacts.
- Do not assume a default GitHub branch is bounty-eligible or deployed.

## Recovery procedure for a new chat

When continuing autonomous development:

1. Read this checkpoint.
2. Read `CYDRA_PROJECT_BIBLE.md` and `AGENTS.md`.
3. Inspect PR #58 and the actual current branch head; never trust a stale conversational SHA.
4. Inspect current GitHub Actions and benchmark artifacts.
5. Check whether the current step is running, passed, failed, or superseded.
6. Continue from the earliest incomplete decision gate above.
7. Preserve this file whenever a material milestone, regression, benchmark result, or next-step decision changes.

This document is a development handoff, not an authority source. It cannot grant testing permission, scope, execution capability, or finding trust.
