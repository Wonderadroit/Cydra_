import json

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import MaterializedBenchmarkInput
from cydra.blind_reasoning import BlindReasoningResult


def test_sealed_candidate_contains_evaluator_case_and_findings():
    result = BlindReasoningResult(
        case_id="case-1",
        contest_name="contest",
        repository="owner/repo",
        revision="deadbeef" * 5,
        input_manifest=("src/A.sol",),
        materialization_fingerprint="materialized",
        model_fingerprint="model",
        hypothesis_names=("h1",),
        observation_names=("o1",),
        selected_observation="o1",
        rounds_used=1,
        planning_steps_used=1,
        observations_used=0,
        findings=(),
        promotion_attempts=(),
    )

    payload = json.loads(result.to_json())

    assert payload["case"] == {
        "case_id": "case-1",
        "contest_name": "contest",
        "repository": "owner/repo",
        "revision": "deadbeef" * 5,
        "rules": {},
        "input_manifest": ["src/A.sol"],
    }
    assert payload["findings"] == []
    assert payload["promotion_attempts"] == []


def test_benchmark_case_contract_stays_blind():
    case = BenchmarkCorpusEntry(
        case_id="case-1",
        contest_name="contest",
        repository="owner/repo",
        revision="deadbeef" * 5,
        input_paths=("src/",),
    )
    materialized = MaterializedBenchmarkInput(
        case_id="case-1",
        corpus_fingerprint="corpus",
        repository="owner/repo",
        revision="deadbeef" * 5,
        selected_paths=("src/A.sol",),
        file_manifest=(("src/A.sol", "sha256"),),
    )

    assert case.revision == materialized.revision
    assert not hasattr(materialized, "known_issues")
