from cydra.reasoning_loop import run_reasoning_loop
from cydra.system_model import Node, SystemModel
from cydra.contradiction_re_evaluation import ContradictionDisposition


def test_reasoning_loop_persists_all_stages():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "observed outcome"))

    result = run_reasoning_loop(
        model,
        contradiction_id="c:1",
        evidence_id="e:1",
        belief_id="b:1",
        prior_confidence=0.5,
        supports_hypothesis=True,
        re_evaluation_id="reeval:1",
        belief_update_id="bu:1",
    )

    assert result.re_evaluation.disposition is ContradictionDisposition.SUPPORTED
    assert result.belief_update.posterior_confidence > 0.5
    assert result.current_belief.confidence == result.belief_update.posterior_confidence
    assert "reeval:1" in model.nodes
    assert "bu:1" in model.nodes
    assert "b:1" in model.nodes


def test_inconclusive_outcome_preserves_confidence():
    model = SystemModel()
    model.add_node(Node("c:1", "evidence", "contradiction"))
    model.add_node(Node("e:1", "evidence", "ambiguous outcome"))

    result = run_reasoning_loop(
        model,
        contradiction_id="c:1",
        evidence_id="e:1",
        belief_id="b:1",
        prior_confidence=0.6,
        supports_hypothesis=None,
        re_evaluation_id="reeval:1",
        belief_update_id="bu:1",
    )

    assert result.belief_update.posterior_confidence == 0.6
    assert result.current_belief.confidence == 0.6
