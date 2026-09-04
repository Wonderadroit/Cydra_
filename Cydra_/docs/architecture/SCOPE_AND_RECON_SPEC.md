# Scope & Recon Architecture Specification

## Objective

Make scope enforcement and reconnaissance the first architectural gateway of CYDRA. CYDRA must establish authorization and boundaries before active investigation and must convert reconnaissance into system-model evidence.

## Scope state machine

Every target/node receives one of:

- `IN_SCOPE` — explicitly authorized and within declared scope.
- `OUT_OF_SCOPE` — explicitly excluded; active testing is prohibited.
- `CONDITIONAL` — permitted only when stated conditions are satisfied.
- `UNKNOWN` — insufficient evidence to establish authorization.

### Enforcement

- `OUT_OF_SCOPE` → hard block for active testing.
- `UNKNOWN` → no active testing; may be retained as an unresolved model node.
- `CONDITIONAL` → require all conditions to be verified before active testing.
- `IN_SCOPE` → eligible for downstream planning subject to remaining constraints.

**Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.**

Scope is inherited by derived active-test nodes unless an explicit scope rule narrows or changes it. Derived observations must retain the scope decision that permitted them.

## Scope inputs

CYDRA should support declared scope from authorized program specifications, platform/program rules, repository documentation, scope files, configuration, and explicit operator policy. Natural-language scope must be represented as structured rules before enforcement.

The gateway should also record:

- target identity;
- authorization source;
- authorization version/context;
- included targets/paths;
- excluded targets/paths;
- conditional requirements;
- time or environment restrictions when supplied;
- known issues / prior audit constraints;
- unresolved scope questions;
- resource dependencies required to understand the target.

## Authorization scope versus contextual acquisition

CYDRA must distinguish:

1. **Authorization scope** — what active testing and eligible findings may target.
2. **Contextual acquisition** — code, documentation, deployment metadata, public state, or dependencies CYDRA may need to inspect or model to understand an authorized target.
3. **Security claim scope** — what CYDRA may assert as an eligible finding.

An out-of-scope component may be acquired and analyzed as contextual dependency material when it interacts with an in-scope component. This does not authorize active testing of the out-of-scope component and does not make findings against that component eligible.

Example:

`IN_SCOPE Vault → calls OUT_OF_SCOPE Oracle`

CYDRA may acquire the Oracle source, model the call boundary, inspect relevant behavior, and reason about how Oracle behavior affects the Vault. Active tests against the Oracle remain blocked unless explicit authorization is granted. Any promoted finding must remain grounded in an eligible in-scope asset and the applicable program impact rules.

Context-only dependency nodes should carry explicit metadata such as:

- `scope_status = OUT_OF_SCOPE`;
- `relationship = DEPENDENCY_OF_IN_SCOPE_TARGET`;
- `usage = SYSTEM_MODEL_ONLY`.

`UNKNOWN` scope remains unresolved and must never be silently treated as in-scope or out-of-scope.

## Acquisition versus authorization

Acquiring source code, documentation, deployment metadata, or public chain state does not itself grant permission to execute tests against the acquired target.

Likewise, discovering an import, library, callback, router, oracle, token, bridge, service, or cross-contract dependency does not expand active scope.

The canonical transition is:

`Discover → Acquire context → Classify scope → Model relationship → Request authorization if needed → Receive explicit grant → Plan authorized observation`

Only the explicit authorization/grant transition can activate additional testing authority.

## Classification versus pruning

Recon should classify test, mock, vendor, generated, and dependency material rather than universally deleting it. Such material can contain useful architectural evidence. Active testing remains governed by scope.

Out-of-scope contextual material is therefore not automatically pruned from the SystemModel; it is explicitly labeled and constrained to system-understanding use.

## Recon outputs

Recon produces provenance-aware system-model observations for:

- assets;
- components;
- entry points;
- externally reachable interfaces;
- identities;
- authentication and authorization controls;
- state-changing operations;
- trust boundaries;
- data flows;
- dependencies and external contracts;
- configuration/deployment boundaries;
- invariants and security assumptions;
- contextual relationships to out-of-scope dependencies.

## Repository recon

For source repositories, the first structural pass should identify language/framework, package boundaries, imports, interfaces, exported/public functions, state mutation, authorization checks, external calls, persistence, configuration, and test/mock/vendor boundaries.

Repository/version acquisition should prefer the exact branch, tag, release, or commit required by the program rules. A repository's default branch must not be assumed to represent the deployed or bounty-eligible code.

A repository may be acquired for contextual understanding even when it is not itself in scope, provided the acquisition is authorized/legitimate and the scope classification remains explicit.

AST extraction should remain factual. Interpretation belongs in later reasoning layers.

## Program/resource intake

Program pages and authoritative program resources may reference additional rules, documentation, repositories, deployment sources, PoC requirements, disclosure policies, or other material. Relevant references must be tracked as resource dependencies and acquired through the program-intake architecture before intake is declared complete.

The acquisition architecture is defined in `docs/architecture/PROGRAM_INTAKE_AND_CONTEXT_SPEC.md`.

An acquired resource is evidence with provenance; acquisition is not authorization. A referenced but inaccessible required resource remains explicitly unresolved.

## Known issues

Known issues and previous audit findings are ingested as baseline knowledge. They may suppress duplicate finding generation but remain available as contextual evidence and must retain provenance.

## Safety invariant

No downstream planner may produce an executable active-test action unless the gateway establishes that the target/action is authorized and in scope. Planning can still produce a blocked or unresolved explanation when authorization is absent.

Contextual acquisition and modeling may continue for out-of-scope dependencies when needed to understand the in-scope system, but this must never create an executable active-test action or eligible finding against the contextual component without explicit authorization.
