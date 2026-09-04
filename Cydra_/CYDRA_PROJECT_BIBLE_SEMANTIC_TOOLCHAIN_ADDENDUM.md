# CYDRA Project Bible Addendum — Semantic Interaction and Toolchain Contract

This addendum is part of the Project Bible's canonical architectural record.

## Toolchain discovery is part of reasoning intake

CYDRA must discover a target project's declared toolchain and build environment before selecting evidence-generation capabilities. Project instructions, README/build instructions, build configuration, CI configuration, lockfiles, compiler pragmas, dependency metadata, and equivalent authoritative declarations are evidence about the expected environment.

CYDRA distinguishes:

- **Declared environment:** what the project says it expects.
- **Observed environment:** what CYDRA actually has or provisions.
- **Substituted environment:** an observed capability intentionally used instead of the declared capability.

CYDRA may provision a compatible alternative when the declared capability is unavailable, but the compatibility/fidelity relationship must be established and recorded. Evidence from a substitute cannot silently become equivalent to declared-toolchain evidence. Approximate or incomplete capability output remains explicitly limited and cannot support a compiler-faithful security claim until fidelity is established.

A toolchain failure is an observation, not permission to weaken the evidence contract. CYDRA may continue with supported partial understanding while preserving unresolved state.

## Reasoning is capability-independent

The CYDRA reasoning contract is invariant across projects. Compiler, parser, AST provider, execution engine, and other external tools are replaceable capabilities for generating evidence. Capability failure must not collapse the reasoning flow and must never grant additional authority.

The canonical sequence is:

`declared environment → capability selection/provisioning → compatibility/fidelity assessment → canonical evidence → reasoning`

## Semantic interaction composition

Canonical relationships may be composed into higher-order semantic interactions only when the required identity and evidence boundaries are satisfied. Function-local composition requires evidence-backed candidate relationships, the same canonical function declaration identity, and usable source locations establishing the relevant source ordering.

Missing ordering evidence and cross-function relationships are unresolved and must not be composed into security interactions.

## Source order versus runtime causality

AST source ranges provide source-code locations. A source offset can establish **syntactic/source ordering**, but it does not by itself prove runtime execution order across all control-flow paths.

CYDRA therefore preserves two distinct semantic states:

- `syntactically_ordered` — supported by canonical source-location evidence.
- `runtime_causally_ordered` — established only by sufficient control-flow or execution evidence.

Syntactic ordering may generate a bounded competing hypothesis and a discriminating observation. It cannot by itself establish a verified security claim.

## Evidence provenance

Semantic-interaction evidence should retain canonical function identity, AST node identity, source location, provenance, confidence, project revision, and toolchain identity where available. Compiler source-unit identity must be preserved rather than reconstructed from basenames or descriptive labels.
