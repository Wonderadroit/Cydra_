from cydra.foundry import FoundryAuthorization, FoundryResult
from cydra.reasoning_orchestrator import ReasoningOrchestrator
from cydra.planner import Hypothesis, Observation
from cydra.updater import EvidencePolarity


AUTHORIZATION = FoundryAuthorization("test-authorized-foundry")


def test_ingest_observation_result_updates_existing_plan_without_replanning():
    hypotheses = [
        Hypothesis("auth-bypass", 0.7, {"role-check": {"COUNTEREXAMPLE": 0.9, "NO_COUNTEREXAMPLE": 0.1}}),
        Hypothesis("secure-path", 0.3, {"role-check": {"COUNTEREXAMPLE": 0.1, "NO_COUNTEREXAMPLE": 0.9}}),
    ]
    observation = Observation("role-check", ["COUNTEREXAMPLE", "NO_COUNTEREXAMPLE"], 1.0, authorized=True)
    orchestrator = ReasoningOrchestrator()
    plan_result = orchestrator.plan_next(hypotheses, [observation])
    assert plan_result is not None
    plan_events = [event for event in orchestrator.graph.history if event["type"] == "PLAN_RECORDED"]
    assert len(plan_events) == 1

    external_result = FoundryResult(("forge", "test", "--match-test", "role-check"), 1, "failing assertion", "", authorization_id=AUTHORIZATION.authorization_id, scope_status=AUTHORIZATION.scope_status, execution_id=observation.planned_execution_id)
    update = orchestrator.ingest_observation_result(
        external_result,
        observation,
        hypotheses,
        "foundry:role-check:1",
        evidence_polarity={
            "auth-bypass": EvidencePolarity.SUPPORTS,
            "secure-path": EvidencePolarity.CONTRADICTS,
        },
    )

    assert update.observation_node_id == "observation:role-check"
    assert len(update.belief_node_ids) == 2
    assert "evidence:foundry:role-check:1" in orchestrator.model.nodes
    assert orchestrator.model.nodes["observation:role-check"].attributes["planned"] is True
    assert len([event for event in orchestrator.graph.history if event["type"] == "PLAN_RECORDED"]) == 1
    assert orchestrator.graph.history[-1]["type"] == "OBSERVATION_RESULT_INGESTED"
    assert orchestrator.graph.validate() == []


def test_ingest_observation_result_scopes_updates_to_explicit_competing_pair():
    hypotheses = [
        Hypothesis("primary", 0.5, {"probe": {"CONFIRMED": 0.9, "REFUTED": 0.1}}),
        Hypothesis("alternative", 0.3, {"probe": {"CONFIRMED": 0.1, "REFUTED": 0.9}}),
        Hypothesis("unrelated", 0.2, {"probe": {"CONFIRMED": 0.5, "REFUTED": 0.5}}),
    ]
    observation = Observation(
        "probe",
        ["CONFIRMED", "REFUTED"],
        1.0,
        authorized=True,
        discriminates_hypothesis_ids=(hypotheses[0].hypothesis_id, hypotheses[1].hypothesis_id),
    )
    orchestrator = ReasoningOrchestrator()
    assert orchestrator.plan_next(hypotheses, [observation]) is not None

    external_result = FoundryResult(
        ("forge", "test", "--match-test", "probe"),
        0,
        "confirmed",
        "",
        authorization_id=AUTHORIZATION.authorization_id,
        scope_status=AUTHORIZATION.scope_status,
        execution_id=observation.planned_execution_id,
    )
    update = orchestrator.ingest_observation_result(
        external_result,
        observation,
        hypotheses,
        "foundry:probe:scoped",
        evidence_polarity={
            "primary": EvidencePolarity.SUPPORTS,
            "alternative": EvidencePolarity.CONTRADICTS,
        },
    )

    assert len(update.belief_node_ids) == 2
    updated_hypothesis_ids = {
        orchestrator.model.nodes[node_id].attributes["hypothesis_id"]
        for node_id in update.belief_node_ids
    }
    assert updated_hypothesis_ids == {
        hypotheses[0].hypothesis_id,
        hypotheses[1].hypothesis_id,
    }
    assert not any(
        node.kind == "belief" and node.attributes.get("hypothesis_id") == hypotheses[2].hypothesis_id
        for node in orchestrator.model.nodes.values()
    )
    assert orchestrator.graph.validate() == []


def test_ingest_observation_result_rejects_unplanned_observation():
    observation = Observation("role-check", ["yes", "no"], 1.0, authorized=True)
    hypotheses = [Hypothesis("h1", 0.5, {"role-check": {"yes": 0.5, "no": 0.5}})]
    orchestrator = ReasoningOrchestrator()

    try:
        orchestrator.ingest_observation_result(
            FoundryResult(("forge", "test"), 0, "", ""),
            observation,
            hypotheses,
            "foundry:unplanned",
        )
    except KeyError as exc:
        assert "existing planned observation" in str(exc)
    else:
        raise AssertionError("expected unplanned observation rejection")

    assert orchestrator.graph.history == []
    assert orchestrator.model.nodes == {}


def test_ingest_observation_result_preserves_explicit_polarity():
    hypotheses = [Hypothesis("h1", 0.5, {"probe": {"COUNTEREXAMPLE": 0.8, "NO_COUNTEREXAMPLE": 0.2}})]
    observation = Observation("probe", ["COUNTEREXAMPLE", "NO_COUNTEREXAMPLE"], 1.0, True)
    orchestrator = ReasoningOrchestrator()
    orchestrator.plan_next(hypotheses, [observation])

    orchestrator.ingest_observation_result(
        FoundryResult(("forge", "test"), 1, "counterexample", "", authorization_id=AUTHORIZATION.authorization_id, scope_status=AUTHORIZATION.scope_status, execution_id=observation.planned_execution_id),
        observation,
        hypotheses,
        "foundry:probe:1",
        evidence_polarity={"h1": EvidencePolarity.SUPPORTS},
    )

    assert orchestrator.model.neighbors("evidence:foundry:probe:1", "supports") == ["hypothesis:h1"]
    belief = next(node for node in orchestrator.model.nodes.values() if node.kind == "belief")
    assert belief.attributes["evidence_polarity"] == "supports"
