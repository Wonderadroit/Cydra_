# CYDRA v1.17.1 — Reasoning Graph Integration

The persistent `SystemModel` is now a first-class state store for the planner/updater loop.

## Trace

`Hypothesis -> Observation Plan -> Observation -> Belief`

Optional provenance paths:

`Evidence -> Hypothesis`
`Evidence -> Observation`
`Causal Chain -> Evidence/Hypothesis`

Planner metadata (expected information gain, utility and rationale) is stored on the observation node.
Updater metadata (observed outcome, evidence strength and status) is stored on belief nodes.

Unknown predictions remain neutral: missing knowledge is not converted into supporting or contradicting evidence.

The integration is persistence-compatible because the underlying `SystemModel` remains the serialization boundary.
