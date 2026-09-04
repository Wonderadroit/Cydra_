# Program Intake & Contextual Acquisition Architecture

## Objective

CYDRA must be able to understand the complete authorized program context before security reasoning begins, especially for Immunefi workflows. Program rules, scope, resources, repositories, deployments, documentation, and externally referenced material are acquisition inputs to the canonical SystemModel; they are not themselves authority to test.

The architecture is **API-first, adapter-based, evidence-driven, and provenance-preserving**.

## Primary contest/program context

Immunefi is the primary target workflow for CYDRA. Program-specific rules and scope are treated as authoritative engagement inputs, together with applicable platform-wide rules and any explicit operator authorization.

CYDRA must not assume that two programs have identical scope, impacts, PoC requirements, disclosure rules, repository rules, deployment requirements, or testing restrictions. A program intake therefore creates a program-specific contract rather than applying a universal bug-bounty template.

The intake must capture, when available:

- program identity and version/context;
- platform-wide rules applicable to the engagement;
- program-specific rules;
- assets in scope;
- impacts in scope;
- explicit out-of-scope assets/behaviors/impacts;
- conditional permissions and prerequisites;
- PoC requirements;
- testing-environment restrictions;
- deployment/network requirements;
- repository/version/release requirements;
- responsible-publication/disclosure requirements;
- known issues and prior-audit information;
- explicit bounty-ineligible known vulnerabilities, duplicates, and prior disclosures;
- linked resources and external references;
- unresolved or inaccessible requirements.

Rules can change. The acquired program contract must therefore preserve acquisition time/context and source provenance and must not silently treat stale material as current authority.

## Acquisition adapter architecture

CYDRA does not make a single acquisition mechanism the authority. Acquisition mechanisms are interchangeable adapters feeding one canonical intake boundary.

Preferred acquisition order is:

`Authoritative program/API source → authorized MCP/API adapter → scope aggregation adapter → source-specific adapters → controlled web/document fallback`

Potential adapters include:

- Immunefi API or API-compatible/MCP acquisition when available and authorized;
- `bbscope` for scope aggregation and change monitoring;
- GitHub-specific API/connector acquisition for repositories, branches, releases, commits, files, and metadata;
- documentation and PDF acquisition;
- blockchain/explorer/deployment metadata acquisition;
- controlled browser/web retrieval for resources that cannot be obtained through a stronger source;
- future first-party or platform-specific adapters.

Adapters are acquisition mechanisms, not authorities. In particular, MCP, bbscope, LLM normalization, cached data, or web pages must never silently override the canonical program contract.

## Controlled fallback

Web retrieval is a fallback acquisition mechanism, not the primary Immunefi acquisition strategy. If an authoritative/API path is unavailable, CYDRA may use a controlled fallback only when the source is identifiable and the resulting evidence records its provenance, retrieval context, and authority classification.

If a required resource cannot be acquired or authenticated, CYDRA must preserve an explicit `UNRESOLVED` state. It must not hallucinate missing rules, infer authorization from absence of a prohibition, or mark intake complete.

## Resource dependency graph

Program intake creates a resource dependency graph in addition to the security reasoning graph.

Example:

`Immunefi program → program rules → linked documentation → repository → release/commit → deployment metadata → dependent contract/service`

Each resource node should preserve, where applicable:

- canonical resource identity;
- source URL/API identifier or connector identity;
- source authority class;
- acquisition adapter;
- acquisition timestamp/context;
- content hash or deterministic fingerprint;
- version/commit/release identity;
- relationship to the parent resource;
- required/optional status;
- acquisition state (`ACQUIRED`, `UNRESOLVED`, `STALE`, `REJECTED`);
- scope state (`IN_SCOPE`, `OUT_OF_SCOPE`, `CONDITIONAL`, `UNKNOWN`);
- reason for the classification;
- evidence/provenance references.

A resource that is referenced by an authoritative source but has not been acquired is a tracked dependency, not an invisible omission.

## Reference following

CYDRA must acquire and model program-published known-issue/prior-disclosure material as contextual evidence. A known issue marked ineligible by the program must be available to the finding gate, while similarity to a known issue alone must never be treated as identity.

CYDRA must follow semantically relevant references from program pages and acquired resources when they are required to understand rules, scope, assets, deployments, code, testing environments, PoC requirements, or disclosure constraints.

Reference following is bounded. CYDRA must not crawl arbitrary linked content without a reason. Each follow decision should have an explainable reason such as:

- referenced by a scope/rules section;
- required repository/codebase resource;
- deployment or contract discovery source;
- explicit testing-environment requirement;
- explicit PoC requirement;
- responsible-publication requirement;
- dependency needed to understand an in-scope system.

## Scope versus understanding

The core scope invariant is:

> **Scope controls what CYDRA may test and claim, not what CYDRA may need to understand.**

CYDRA must distinguish three concepts:

1. **Authorization scope** — what active testing and findings may target.
2. **Contextual acquisition** — what CYDRA may need to inspect or model to understand an authorized target.
3. **Security claim scope** — what CYDRA may assert as an eligible finding.

An out-of-scope component may therefore be acquired and analyzed as contextual dependency material when it interacts with an in-scope component. This does not authorize active testing of the out-of-scope component and does not make findings against that component eligible.

Example:

`In-scope Vault → calls Oracle → Oracle is out of scope`

CYDRA may acquire the Oracle source, model the call boundary, inspect relevant behavior, and reason about how Oracle behavior affects the Vault. Active tests against the Oracle remain blocked unless explicit authorization is granted. A finding must still be framed against an authorized in-scope asset and within program impact rules.

Context-only components should be represented explicitly, for example:

- `scope_status = OUT_OF_SCOPE`;
- `relationship = DEPENDENCY_OF_IN_SCOPE_TARGET`;
- `usage = SYSTEM_MODEL_ONLY`.

`UNKNOWN` scope remains unresolved and must never be silently treated as in-scope or out-of-scope.

## Acquisition versus authorization

Acquiring source code, documentation, deployment metadata, or public state does not itself grant permission to execute tests against the acquired target.

Likewise, discovering an import, callback, router, oracle, token, bridge, service, or cross-contract dependency does not expand active scope.

The flow is:

`Discover → Acquire context → Classify scope → Model relationship → Request authorization if needed → Receive explicit grant → Plan authorized observation`

Only the explicit authorization/grant transition can activate additional testing authority.

## Repository acquisition

Repository acquisition must be source-specific and version-aware. CYDRA should prefer the exact repository, branch, tag, release, or commit required by the program rules. It must not assume the default branch represents the deployed or bounty-eligible code.

For GitHub, use the GitHub API/connector rather than generic HTML scraping where supported. Repository acquisition should capture repository identity and exact revision metadata so subsequent AST/recon and findings can be tied to the correct source state.

A repository may be acquired for context even when it is not itself in scope if an in-scope asset depends on it. The resulting scope classification remains explicit.

## Program contract

The intake layer should eventually emit a canonical program contract containing:

- program/platform identity;
- applicable rule sources;
- scope rules;
- impact rules;
- PoC requirements;
- testing restrictions;
- disclosure/publication constraints;
- resource dependency graph;
- acquired source/version identities;
- unresolved requirements;
- deterministic intake fingerprint;
- provenance for every material assertion.

The program contract is input to scope enforcement and reasoning. It is not allowed to mutate authority merely because a resource says that something should be tested.

## Change detection and freshness

Program scope and rules are mutable. Acquisition adapters should support deterministic comparison of newly acquired program state against prior state. Scope/rule changes must invalidate or revalidate dependent intake state rather than silently leaving stale authority in place.

Change monitoring may use bbscope or another monitoring adapter, but detected changes remain observations requiring canonical re-acquisition and validation before becoming current program authority.

## Failure and trust rules

- Missing required program material → `UNRESOLVED`, not guessed.
- Unauthenticated or unverifiable source → untrusted evidence, not authority.
- Conflicting authoritative sources → explicit contradiction requiring resolution.
- Stale source → marked stale and revalidated before use as current authority.
- LLM-normalized scope → candidate interpretation only until validated against authoritative source material.
- Cached adapter output → evidence with cache provenance; never silently current authority.
- External dependency discovered by code analysis → contextual dependency candidate; never automatic scope expansion.
- Publicly readable code → not automatically authorized for active testing.
- Out-of-scope dependency → may inform the SystemModel but cannot become an eligible target without explicit authorization.

## AI role

AI may assist with semantic extraction, classification, normalization, reference relevance, hypothesis generation, and reasoning prioritization. AI output is always evidence or a proposal with provenance until validated by the appropriate canonical boundary.

AI must never:

- invent missing scope/rules;
- turn inferred authorization into authority;
- silently resolve contradictory program rules;
- convert an out-of-scope dependency into an in-scope target;
- treat an LLM-normalized scope list as authoritative without source validation;
- claim execution occurred when only a plan or generated PoC exists.

## Canonical pipeline

`Program Discovery → Program Acquisition → Rule/Scope Extraction → Reference Discovery → Resource Dependency Graph → Source/Deployment Acquisition → Scope Classification → Program Contract → System Acquisition → SystemModel → Reasoning → Authorized Test Plan → External Gateway`

The acquisition layer ends where canonical, provenance-aware program/system context is available. The execution gateway remains the only route to active external execution.

## Implementation status and remaining sequence

1. **DONE** — Define canonical program/resource evidence types.
2. **DONE** — Define acquisition-adapter interface and provenance contract.
3. **DONE** — Implement Immunefi acquisition adapter with injectable transport and bounded canonical page acquisition.
4. **IN PROGRESS** — Implement reference extraction and bounded dependency traversal.
5. **DONE** — Model program-published known issues as provenance-bound, explicitly eligibility-scoped context.
5. Implement GitHub source/version adapter.
6. Integrate bbscope as a non-authoritative scope adapter.
7. Add controlled document/PDF/web fallback.
8. Build the resource dependency graph and unresolved-resource gate.
9. Produce the canonical program contract.
10. Feed the contract into existing scope enforcement and `RepositoryAuditSession` without weakening current execution/finding gates.
11. Add adversarial tests for stale rules, conflicting sources, unauthorized scope expansion, out-of-scope contextual dependencies, and missing required resources.

## Acceptance criteria

Program intake is complete only when every required resource is either:

- acquired and provenance-validated;
- explicitly determined not applicable with evidence; or
- explicitly unresolved and surfaced to the operator.

No active testing may begin while required authorization/scope material remains unresolved.

Contextual understanding may include out-of-scope dependencies, but all such nodes remain visibly out of scope and cannot authorize testing or finding promotion.

The acquisition layer must be deterministic enough to reproduce the program contract from the same source versions and retrieval context, subject to explicitly recorded external-source changes.
