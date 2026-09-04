# CYDRA Blind Historical Benchmark Protocol

## Purpose

CYDRA should be evaluated against real historical security audits before more reasoning features are added. Historical findings are evaluation oracles, never investigation input.

The benchmark is an experiment, not a feature-development excuse: run several independent historical cases, measure misses and false positives, cluster failure modes, then make the smallest evidence-supported change.

## Blind boundary

A benchmark case may expose only the contest/project identifier, exact repository revision, contest scope and forbidden actions, selected repository/documentation artifacts, and an explicitly simulated authority/budget envelope.

It must not expose historical finding titles, issue IDs, report text, root-cause labels, or oracle fingerprints.

`cydra.benchmark.BlindBenchmarkCase` is the input-side contract. `BenchmarkOracle` exists only on the evaluator side.

`BenchmarkCorpusEntry` freezes the permitted source paths. The materialization boundary in `cydra.benchmark_materialization` verifies the exact source commit, requires a clean checkout, rejects oracle-like paths and symlinks, copies only the frozen inputs into a clean staging directory, and writes an oracle-free receipt containing file SHA-256 digests.

## Reproducible materialization

For a frozen manifest such as `data/benchmarks/predy-2024-05.json`:

```bash
python tools/materialize_blind_benchmark.py \
  --manifest data/benchmarks/predy-2024-05.json \
  --source /path/to/2024-05-predy \
  --destination /tmp/cydra-blind/predy-2024-05
```

The source checkout must already be pinned to the manifest's exact commit and have no uncommitted or untracked changes. The command fails closed on a revision mismatch or dirty checkout. It also refuses historical report/finding paths, symlinks, stale destination content, and other materialization-boundary violations.

The resulting `.cydra-blind-receipt.json` is the provenance receipt for the exact blind input. Before investigation, the staged file set and receipt should be revalidated with `validate_materialized_input()`; the receipt itself contains no historical finding data.

The materialization tool does **not** run the investigation, execute Solidity, invoke Foundry, or load the historical oracle. It creates the clean input boundary so the actual blind run can be performed by an independent runner without contaminating the investigation.

## Investigation run

1. Freeze the benchmark manifest and record its fingerprint.
2. Clone/checkout the historical repository at the exact pinned revision outside the CYDRA oracle store.
3. Ensure the historical checkout is clean and contains no uncommitted or untracked changes.
4. Materialize only the manifest-selected inputs into a clean staging directory.
5. Validate the materialization receipt immediately before handing the staged input to CYDRA.
6. Start CYDRA with only the blind case, staged source observations, contest rules, and the selected simulated authority envelope.
7. Disable historical-finding learning during this run. No oracle-derived records may enter the learning store.
8. Record the CYDRA commit SHA, corpus fingerprint, materialization fingerprint, authority/budget profile, investigation identity, candidate findings, and run timing/cost.
9. Seal the raw candidate output before revealing any historical oracle.
10. Only then load the independently curated oracle and evaluate the candidate output.

The blind runner rejects oracle/ground-truth/known-issue environment variables rather than silently stripping caller-supplied values. This makes accidental oracle injection a hard benchmark failure before CYDRA starts.

The historical checkout may contain report files because the upstream repository is immutable; what matters is that those files never cross the materialization boundary. The staging directory should contain only the selected blind files plus its provenance receipt.

## Canonical finding promotion

The blind reasoning result now has an explicit evaluator-compatible `findings` field and an optional `promotion_attempts` audit section. This closes the representation gap without weakening the blind boundary.

Reasoning-produced finding candidates must enter through `cydra.benchmark_finding_promotion.promote_reasoning_findings()`. That adapter calls the canonical graph-aware `evaluate_finding_graph()` gate and persists a finding only after the gate returns `READY`. It does not inspect historical issue data, infer a finding from a benchmark oracle, manufacture execution evidence, or bypass causal/evidence requirements.

An empty finding-candidate input is intentionally inert: the blind run remains a planning experiment and produces `findings: []`. This is a valid candidate artifact, but it is not evidence of zero vulnerabilities and should not be mistaken for a useful recall measurement until CYDRA's reasoning layer actually emits finding candidates.

## Evaluation

After the blind investigation completes, the evaluator receives the case identity, sealed historical oracle, and CYDRA candidate finding identities/severities. It reports true positives, misses, unexpected findings, recall, precision, and severity agreement.

Historical fingerprints must be unique, as must candidate fingerprints. The evaluator intentionally does not use fuzzy title matching. Semantic equivalence must be established by an explicit, reviewable benchmark annotation rather than a convenient string heuristic.

`tools/evaluate_blind_benchmark.py` is the post-run evaluator. It consumes three separate inputs: a sealed candidate, an evaluator-only oracle, and reviewer annotations. Reviewer annotations may additionally record a failure class, evidence gaps, and reasoning failures for each reviewed correspondence. The evaluator emits SHA-256 digests for all three inputs together with TP/FP/FN, precision, recall, severity agreement, matched/missed issue IDs, unexpected candidate fingerprints, and review diagnostics.

The evaluator must run only after the blind candidate has been sealed. The oracle and annotations must not be mounted into the blind staging directory or made available to the CYDRA process. A committed evaluator implementation is safe because it does not contain historical findings; the actual oracle/annotation payload remains an external evaluator input.

Example post-run invocation:

```bash
python tools/evaluate_blind_benchmark.py \
  --candidate /secure/evaluation/predy/candidate.json \
  --oracle /secure/evaluation/predy/oracle.json \
  --annotations /secure/evaluation/predy/annotations.json \
  --output /secure/evaluation/predy/evaluation.json
```

The current sealed Predy artifact is now structurally compatible with the evaluator and contains `findings: []`. The first run therefore establishes a legitimate **zero-candidate baseline**: if the independently curated Predy oracle is applied post-run, every oracle issue is a miss and there are no candidate false positives. The resulting recall is 0 when the oracle is non-empty, while precision is mathematically vacuous for an empty candidate set. This score must be labeled as a baseline, not as evidence that CYDRA found nothing in the code.

## First Immunefi benchmark

`immunefi-arbitration-boost-2024-03` is the first Immunefi-specific blind corpus entry. It freezes the `immunefi-team/vaults` source revision cited by the historical competition material and exposes only README/configuration/source paths. Historical reports remain evaluator-only and are never part of the blind manifest.

This case is particularly useful for testing bounty-eligibility semantics because the competition rules explicitly treated duplicates and private known issues differently from ordinary Immunefi programs. The benchmark therefore tests whether CYDRA keeps program-specific eligibility rules separate from generic known-issue reasoning.

The historical oracle is intentionally not stored under `data/benchmarks/`; only the blind source manifest is committed there.

## Initial corpus

Use multiple protocol classes rather than one hand-picked contest:

1. Predy — oracle, economic, and cross-contract reasoning
2. Wise Lending — lending, accounting, and invariants
3. BakerFi — leverage, oracle, precision, and economic interactions
4. Blackhole — authorization, accounting, and state interactions
5. Virtuals Protocol — authorization, cross-contract, and cascading effects

A contest is benchmark-ready only after its exact source revision, permitted inputs, scope constraints, and independently curated historical oracle are frozen.

## Run discipline

Record the CYDRA commit SHA, benchmark case fingerprint, materialization receipt fingerprint, repository revision, authority/budget profile, candidate output, evaluator version, and final evaluation result.

The oracle must remain unavailable to the investigation. Learning from historical findings is disabled during the blind run. Any post-evaluation learning experiment is a separate, explicitly labelled run.

Do not use a single benchmark miss to justify a new detector. Three to five diverse contests should be run before clustering failure modes, unless a safety or integrity defect blocks further benchmarking.

## Safety

This is an offline historical-code experiment. It does not require live exploitation or unauthorized transactions. Any future dynamic execution remains subject to CYDRA's existing authorization, gateway, durable-receipt, and evidence boundaries.

## Miss analysis

A missed finding is not automatically evidence for a new vulnerability detector. Classify the failure first: missing system-model information, missing invariant, missing hypothesis, poor competing-hypothesis handling, poor observation selection, authority/scope limitation, causal-verification failure, evidence/provenance failure, finding-promotion failure, or benchmark-annotation mismatch.

Track at least:

- recall and precision
- severity agreement
- root-cause/causal-chain agreement
- evidence completeness and provenance
- PoC/reproducibility quality where applicable
- time and observation/execution cost
- false-positive categories
- exact reason each historical finding was missed

Cluster recurring misses across contests. Only then change the smallest subsystem that the evidence implicates, rerun the affected benchmarks, and preserve the prior results for regression comparison.
