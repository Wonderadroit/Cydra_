# Real-World Validation Variants

## Purpose

Real-world validation variants are a first-class CYDRA investigation capability for distinguishing a genuine security failure from an observation that is only suspicious under one artificial state or execution path.

A variant is a bounded, explicitly described change to a relevant execution condition—such as state, input, actor, ordering, dependency response, economic parameter, or other causal factor—that CYDRA expects may distinguish competing security explanations.

## Canonical loop

`Security hypothesis → identify causal dependencies → select relevant variants → execute authorized observations → persist exact results → compare observations → update hypotheses → causal verification → finding`

## Why variants exist

A single suspicious observation does not establish a vulnerability. CYDRA should challenge important hypotheses by testing conditions that can:

- falsify the suspected mechanism;
- expose missing preconditions;
- distinguish a benign explanation from a security failure;
- reveal state dependence or ordering dependence; or
- demonstrate that the same causal mechanism survives meaningful changes in conditions.

Cross-variant agreement can strengthen a causal hypothesis when the variants are independently evidenced and causally relevant. Divergence can reveal a false positive, hidden precondition, state dependence, or competing explanation. Neither agreement nor divergence is proof by itself.

## Variant selection

Variants are generated from CYDRA's current system model, invariants, competing hypotheses, observed causal dependencies, and authorized investigation envelope. They are selected for information value, not because they resemble a known vulnerability or historical finding.

Useful variant dimensions can include:

- boundary and near-boundary values;
- repeated versus first-time interactions;
- alternate authorized actors;
- state-before/state-after conditions;
- transaction or call ordering;
- dependency responses;
- exchange-rate and price conditions;
- rounding and precision boundaries;
- finite economic scenario parameters; and
- other model-derived causal conditions.

The exact dimensions depend on the target and must not become a universal checklist.

## Authority and provenance

Variants never create authority. Every active variant remains subject to the same scope, authorization, bounded-investigation, execution-gateway, durable-result, and receipt-bound evidence-ingestion controls as any other observation.

Each variant observation must retain:

- the exact observation identity it tests;
- the hypothesis or competing-hypothesis binding;
- the relevant changed condition(s);
- execution-request identity;
- durable execution result receipt; and
- resulting evidence and provenance.

A failed, missing, or inconclusive variant execution must never silently become a negative security result.

## Blind validation

Historical findings may be used after blind evaluation for learning and assessment, but must not be injected into variant generation, selection, or execution as a current-answer oracle.

A successful validation should arise from CYDRA's current evidence and reasoning path. The purpose is to measure whether CYDRA can independently discover and validate the causal mechanism.

## Bounded search

Variant sets must be finite. Variant count, state-space size, execution cost, dependency depth, branching, and scenario depth remain bounded by the investigation authority. Adaptive expansion requires explicit external authority and cannot be self-granted by the planner.

## Security outcome

The desired progression is:

`Observation → competing hypotheses → informative variants → real observed behavior → cross-variant evidence → causal explanation → reproducible PoC → verified finding`

This capability is part of CYDRA's core bug-discovery mission. It is not a separate audit/compliance feature.
