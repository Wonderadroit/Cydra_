#!/usr/bin/env python3
"""Run a deterministic CYDRA composition smoke test from the command line.

This is intentionally a dogfood harness, not a second reasoning engine. It
exercises the existing passive-intake -> canonical-model -> planning boundary
and asserts that no external observation was executed as a side effect.
"""
from __future__ import annotations

from cydra.canonical_pipeline import CanonicalAuditPipeline
from cydra.planner import Hypothesis, Observation
from cydra.scope import ScopePolicy, ScopeRule, ScopeState


def main() -> int:
    policy = ScopePolicy(
        [
            ScopeRule("src/**", ScopeState.IN_SCOPE, "dogfood target"),
            ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE, "test material excluded"),
        ]
    )
    pipeline = CanonicalAuditPipeline(policy.decide)

    hypotheses = [
        Hypothesis(
            "auth-bypass",
            0.7,
            {"role-check": {"allowed": 0.2, "denied": 0.8}},
        ),
        Hypothesis(
            "secure-path",
            0.3,
            {"role-check": {"allowed": 0.9, "denied": 0.1}},
        ),
    ]
    observations = [
        Observation("role-check", ["allowed", "denied"], 1.0, authorized=True)
    ]

    result = pipeline.run_passive_to_plan(
        ["src/app.py", "tests/test_app.py"],
        {
            "src/app.py": "def run():\n    return 1\n",
            "tests/test_app.py": "def test_only():\n    return 2\n",
        },
        hypotheses,
        observations,
    )

    assert result.plan is not None, "planner produced no plan"
    assert result.plan.plan.observation == "role-check", "unexpected observation"
    assert result.model is result.session.model is pipeline.model
    assert result.model is pipeline.orchestrator.model
    assert result.model.nodes[result.session.session_id].kind == "audit_session"
    assert result.model.nodes["observation:role-check"].attributes["planned"] is True
    assert result.model.nodes["observation:role-check"].attributes["authorized"] is True
    assert "module:tests/test_app.py" not in result.model.nodes
    assert not any(
        event["type"] == "OBSERVATION_EXECUTED"
        for event in pipeline.orchestrator.graph.history
    ), "planning unexpectedly executed an observation"
    assert pipeline.orchestrator.graph.validate() == []

    print("CYDRA DOGFOOD: PASS")
    print("  repository intake        PASS")
    print("  scope filtering          PASS")
    print("  canonical SystemModel   PASS")
    print("  hypothesis/planner       PASS")
    print("  plan persistence         PASS")
    print("  execution side effect    PASS (none occurred)")
    print("  graph validation         PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
