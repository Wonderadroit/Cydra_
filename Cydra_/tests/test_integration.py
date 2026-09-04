from cydra.planner import Hypothesis, Observation, choose_next_observation
from cydra.updater import update_hypotheses

def test_plan_then_update_loop():
    hs=[
      Hypothesis("A",.5,{"observe":{"x":.9,"y":.1}}),
      Hypothesis("B",.5,{"observe":{"x":.1,"y":.9}}),
    ]
    plan=choose_next_observation(hs,[Observation("observe",["x","y"],1,True)])
    assert plan is not None
    result=update_hypotheses(hs,plan.observation,"x")
    assert result.hypotheses[0].probability != result.hypotheses[1].probability
