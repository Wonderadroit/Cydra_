# CYDRA v1.18 — Semantic Graph

The system model now has explicit relationship semantics. Graph validation checks both endpoint existence and whether a relationship is valid for the source/target node kinds.

Supported semantic relations include `supports`, `contradicts`, `explains`, `derived_from`, `tested_by`, `updates`, `updated_to`, `constrains`, and `crosses`.

Unknown relationships are rejected by semantic validation. Contradictions are represented as first-class edges and are preserved rather than converted into a binary finding decision.

This layer is intentionally reasoning-only: it does not execute live targets or bypass authorization.

## Semantic interaction contract

Canonical AST-backed relationships may be composed into semantic interactions only when the relationships share the required canonical identity and the evidence needed for the composition is present. Function-local ordering requires evidence-backed candidate relationships, the same canonical function declaration identity, and usable source locations establishing source order. Missing ordering evidence and cross-function relationships remain unresolved and must not be composed into security interactions.

A Solidity AST source range establishes **syntactic/source ordering** only. It does not prove runtime execution order on every control-flow path. CYDRA therefore distinguishes `syntactically_ordered` from `runtime_causally_ordered`. The former can generate a bounded hypothesis; the latter requires separate control-flow or execution evidence before a verified security claim may be emitted.

## Toolchain contract

CYDRA's reasoning contract is project-independent. Compiler, parser, AST provider, execution engine, and other external tools are replaceable evidence-generation capabilities.

Before selecting an evidence-generation capability, CYDRA must discover the project's declared toolchain from project instructions, build configuration, CI configuration, lockfiles, compiler pragmas, dependency metadata, and related authoritative material. CYDRA must distinguish the declared environment, observed environment, and any substituted environment.

A substituted capability may be used when necessary, but compatibility and fidelity must be established and recorded before its evidence can support a security claim. Capability failure is an observation and must not silently weaken evidence requirements. Partial understanding may continue where supported, while approximate or incomplete evidence remains explicitly unresolved for compiler-faithful verification.

The resulting architecture is:

`declared environment → capability selection/provisioning → compatibility/fidelity assessment → canonical evidence → semantic interaction → competing hypotheses → discriminating observation → verification → causal claim`
