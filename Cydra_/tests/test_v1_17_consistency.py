import json
from pathlib import Path

from cydra.counterexample import Counterexample
from cydra.poc import Counterexample as POCCounterexample
from cydra.poc import POCArtifact
from cydra.system_model import SystemModel


ROOT = Path(__file__).resolve().parents[1]


def test_system_model_schema_declares_repository_node_kinds():
    schema = json.loads((ROOT / "data" / "system_model.schema.json").read_text())
    model_kinds = set(SystemModel.KINDS)
    assert model_kinds <= set(schema["node_kinds"])
    assert {"contract", "function", "state_variable"} <= set(schema["node_kinds"])


def test_poc_uses_canonical_counterexample_model():
    assert POCCounterexample is Counterexample
    counterexample = Counterexample(
        test_name="invariant_test",
        input_data={"x": 1},
        trace=["call()"],
        invariant="x >= 0",
        expected=True,
        actual=False,
        reproducible=True,
    )
    artifact = POCArtifact(
        hypothesis_id="H1",
        counterexample=counterexample,
        expected_violation="x became negative",
        execution_request_id="execution-request:H1",
    )
    assert artifact.counterexample is counterexample
    assert artifact.is_reproducible()
