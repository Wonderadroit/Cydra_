from pathlib import Path
import json

import pytest

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import MaterializedBenchmarkInput
from cydra.benchmark_replay import ReplayObservationResult
from cydra.blind_reasoning import run_blind_reasoning
from cydra.evidence_reasoning_provider import CanonicalEvidenceReasoningProvider
from cydra.reasoning_driver import ReasoningInputs
from cydra.planner import Hypothesis, Observation
from cydra.updater import EvidencePolarity


def test_blind_reasoning_serializes_selected_replay_receipt(tmp_path: Path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text(
        "contract App { uint256 public value; function set(uint256 x) external { value = x; } }\n",
        encoding="utf-8",
    )
    case = BenchmarkCorpusEntry(
        case_id="receipt-case",
        contest_name="historical",
        repository="example/repo",
        revision="a" * 40,
        input_paths=("src/",),
    )
    materialized = MaterializedBenchmarkInput(
        case_id="receipt-case",
        corpus_fingerprint="b" * 64,
        repository="example/repo",
        revision="a" * 40,
        selected_paths=("src/app.sol",),
        file_manifest=(("src/app.sol", "c" * 64),),
    )
    monkeypatch.setattr(
        "cydra.blind_reasoning.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    observation_name = "verify:fixture:selected"
    hypothesis_name = "relationship:fixture:selected"
    competing_hypothesis_name = "relationship:fixture:alternative"
    hypothesis = Hypothesis(
        name=hypothesis_name,
        probability=0.5,
        predictions={observation_name: {"CONFIRMED": 0.9, "REFUTED": 0.1}},
    )
    competing_hypothesis = Hypothesis(
        name=competing_hypothesis_name,
        probability=0.5,
        predictions={observation_name: {"CONFIRMED": 0.1, "REFUTED": 0.9}},
    )
    observation = Observation(
        observation_name,
        ["CONFIRMED", "REFUTED"],
        1.0,
        authorized=True,
    )
    monkeypatch.setattr(
        CanonicalEvidenceReasoningProvider,
        "propose",
        lambda self, model: ReasoningInputs.from_sequences(
            [hypothesis, competing_hypothesis], [observation]
        ),
    )

    result = run_blind_reasoning(
        case,
        materialized,
        root,
        observation_replayer=lambda selected, replay_root: ReplayObservationResult(
            "CONFIRMED",
            {hypothesis_name: EvidencePolarity.SUPPORTS},
            {"verifier": "test-double", "source": "compiler-ast"},
        ),
    )

    assert result.observations_used == 1
    assert result.replay_result is not None
    assert result.replay_result["outcome"] == "CONFIRMED"
    assert result.replay_result["evidence_polarity"] == {hypothesis_name: EvidencePolarity.SUPPORTS.value}
    assert result.replay_result["verifier_details"]["verifier"] == "test-double"
    assert result.replay_result["verifier_details"]["source"] == "compiler-ast"
    assert result.replay_result["verifier_details"]["observation_name"] == observation_name
    assert len(result.replay_result["receipt_digest"]) == 64

    assert len(result.hypothesis_updates) == 2
    updates = {item["hypothesis_id"]: item for item in result.hypothesis_updates}
    selected_update = updates[f"hypothesis:{hypothesis_name}"]
    competing_update = updates[f"hypothesis:{competing_hypothesis_name}"]
    assert selected_update["prior_probability"] == 0.5
    assert selected_update["posterior_probability"] == pytest.approx(0.9)
    assert selected_update["evidence_polarity"] == EvidencePolarity.SUPPORTS.value
    assert competing_update["prior_probability"] == 0.5
    assert competing_update["posterior_probability"] == pytest.approx(0.1)
    assert competing_update["evidence_polarity"] is None

    payload = result.to_json()
    parsed = json.loads(payload)
    serialized_updates = {
        item["hypothesis_id"]: item for item in parsed["hypothesis_updates"]
    }
    assert serialized_updates[f"hypothesis:{hypothesis_name}"]["posterior_probability"] == pytest.approx(0.9)
    assert serialized_updates[f"hypothesis:{competing_hypothesis_name}"]["posterior_probability"] == pytest.approx(0.1)
    assert '"replay_result"' in payload
    assert '"hypothesis_updates"' in payload
    assert '"outcome": "CONFIRMED"' in payload
    assert f'"{EvidencePolarity.SUPPORTS.value}"' in payload
    assert "historical_finding" not in payload.lower()
    assert "known_issue" not in payload.lower()
