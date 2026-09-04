from cydra.planner import Hypothesis, HypothesisState
from cydra.updater import EvidencePolarity, UpdateResult, update_hypotheses

def hs():
    return [
      Hypothesis("A", .5, {"test":{"x":.9,"y":.1}}),
      Hypothesis("B", .5, {"test":{"x":.1,"y":.9}}),
    ]

def probs(r): return {h.name:h.probability for h in r.hypotheses}

def test_bayesian_update_favors_consistent_hypothesis():
    r=update_hypotheses(hs(),"test","x")
    p=probs(r)
    assert p["A"] > p["B"] and abs(sum(p.values())-1)<1e-9

def test_repeated_update_is_normalized():
    r=update_hypotheses(hs(),"test","x",.5)
    assert abs(sum(h.probability for h in r.hypotheses)-1)<1e-9

def test_unknown_prediction_is_not_invented():
    hypotheses=[
      Hypothesis("A",.5,{"test":{"x":.9}}),
      Hypothesis("B",.5,{}),
    ]
    r=update_hypotheses(hypotheses,"test","x")
    assert r.status=="PARTIAL_UPDATE"
    assert abs(probs(r)["A"]-probs(r)["B"]) < 1e-9

def test_zero_evidence_strength_does_not_change_priors():
    r=update_hypotheses(hs(),"test","x",0)
    p=probs(r)
    assert abs(p["A"]-.5)<1e-9 and abs(p["B"]-.5)<1e-9

def test_empty_hypotheses_is_safe():
    r=update_hypotheses([],"test","x")
    assert r.status=="INSUFFICIENT_EVIDENCE" and r.hypotheses==[]

def test_probability_update_preserves_explicit_hypothesis_state():
    hypotheses=[Hypothesis("A", .8, {"test":{"x":.9}}, HypothesisState.SUPPORTED)]
    r=update_hypotheses(hypotheses, "test", "x")
    assert r.hypotheses[0].state == HypothesisState.SUPPORTED

def test_explicit_polarity_is_preserved_without_inference():
    result = update_hypotheses(
        hs(),
        "test",
        "x",
        evidence_polarity={"A": EvidencePolarity.SUPPORTS, "B": EvidencePolarity.CONTRADICTS},
    )
    assert result.evidence_polarity == {
        "A": EvidencePolarity.SUPPORTS,
        "B": EvidencePolarity.CONTRADICTS,
    }

def test_missing_polarity_is_not_inferred_from_probability_or_state():
    hypotheses = [
        Hypothesis("A", .8, {"test": {"x": .9}}, HypothesisState.SUPPORTED),
        Hypothesis("B", .2, {"test": {"x": .1}}, HypothesisState.CONTRADICTED),
    ]
    result = update_hypotheses(hypotheses, "test", "x")
    assert result.evidence_polarity == {}

def test_neutral_polarity_is_explicit():
    result = update_hypotheses(
        hs(),
        "test",
        "x",
        evidence_polarity={"A": EvidencePolarity.NEUTRAL},
    )
    assert result.evidence_polarity == {"A": EvidencePolarity.NEUTRAL}

def test_polarity_unknown_hypothesis_is_rejected():
    try:
        update_hypotheses(hs(), "test", "x", evidence_polarity={"missing": EvidencePolarity.SUPPORTS})
    except ValueError:
        pass
    else:
        assert False

def test_update_result_rejects_non_enum_polarity():
    try:
        UpdateResult(hs(), "x", 1.0, "UPDATED", "test", {"A": "supports"})
    except ValueError:
        pass
    else:
        assert False
