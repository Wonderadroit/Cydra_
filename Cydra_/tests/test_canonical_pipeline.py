from cydra.canonical_pipeline import CanonicalAuditPipeline
from cydra.planner import Hypothesis, Observation
from cydra.scope import ScopePolicy, ScopeRule, ScopeState


def test_run_passive_to_plan_uses_one_canonical_model_and_stops_before_execution():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target"),
        ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE, "tests excluded"),
    ])
    pipeline = CanonicalAuditPipeline(policy.decide)
    hypotheses = [
        Hypothesis("auth-bypass", 0.7, {"role-check": {"allowed": 0.2, "denied": 0.8}}),
        Hypothesis("secure-path", 0.3, {"role-check": {"allowed": 0.9, "denied": 0.1}}),
    ]
    observations = [Observation("role-check", ["allowed", "denied"], 1.0, authorized=True)]

    result = pipeline.run_passive_to_plan(
        ["src/app.py", "tests/test_app.py"],
        {
            "src/app.py": "def run():\n    return 1\n",
            "tests/test_app.py": "def test_only():\n    return 2\n",
        },
        hypotheses,
        observations,
    )

    assert result.plan is not None
    assert result.plan.plan.observation == "role-check"
    assert result.model is result.session.model
    assert result.model is pipeline.model
    assert result.model is pipeline.orchestrator.model
    assert result.model.nodes[result.session.session_id].kind == "audit_session"
    assert result.model.nodes["observation:role-check"].attributes["planned"] is True
    assert result.model.nodes["observation:role-check"].attributes["authorized"] is True
    assert "module:tests/test_app.py" not in result.model.nodes
    assert not any(event["type"] == "OBSERVATION_EXECUTED" for event in pipeline.orchestrator.graph.history)
    assert pipeline.orchestrator.graph.validate() == []


def test_passive_intake_failure_does_not_create_a_reasoning_plan():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target")])
    pipeline = CanonicalAuditPipeline(policy.decide)

    try:
        pipeline.run_passive_to_plan(
            ["src/app.py"],
            {},
            [Hypothesis("h", 1.0, {"probe": {"yes": 1.0}})],
            [Observation("probe", ["yes", "no"], 1.0, authorized=True)],
        )
    except KeyError as exc:
        assert "source missing" in str(exc)
    else:
        raise AssertionError("expected passive intake failure")

    assert pipeline.model.nodes == {}
    assert pipeline.model.edges == []
    assert pipeline.orchestrator.graph.history == []
