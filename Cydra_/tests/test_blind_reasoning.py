from pathlib import Path
import json

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import MaterializedBenchmarkInput
from cydra.blind_reasoning import run_blind_reasoning
from tools.run_blind_reasoning import _load_solidity_asts


def make_case() -> BenchmarkCorpusEntry:
    return BenchmarkCorpusEntry(
        case_id="case-1",
        contest_name="historical",
        repository="example/repo",
        revision="a" * 40,
        input_paths=("src/",),
    )


def make_materialized() -> MaterializedBenchmarkInput:
    return MaterializedBenchmarkInput(
        case_id="case-1",
        corpus_fingerprint="b" * 64,
        repository="example/repo",
        revision="a" * 40,
        selected_paths=("src/app.sol",),
        file_manifest=(("src/app.sol", "c" * 64),),
    )


def test_blind_reasoning_stops_at_planning_and_is_deterministic(tmp_path: Path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text(
        "contract App { uint256 public value; function set(uint256 x) external { value = x; } }\n",
        encoding="utf-8",
    )
    materialized = make_materialized()
    monkeypatch.setattr(
        "cydra.blind_reasoning.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    first = run_blind_reasoning(make_case(), materialized, root)
    second = run_blind_reasoning(make_case(), materialized, root)

    assert first.case_id == "case-1"
    assert first.materialization_fingerprint == materialized.fingerprint()
    assert len(first.model_fingerprint) == 64
    assert first.to_json() == second.to_json()
    assert first.rounds_used <= 1
    assert first.planning_steps_used <= 1
    assert first.observations_used <= 1


def test_blind_reasoning_persists_selected_plan_in_canonical_graph(tmp_path: Path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text(
        "contract App { uint256 public value; function set(uint256 x) external { value = x; } }\n",
        encoding="utf-8",
    )
    materialized = make_materialized()
    monkeypatch.setattr(
        "cydra.blind_reasoning.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    # The public result intentionally does not expose the internal graph, so
    # exercise the persistence helper directly against the same canonical graph
    # shape to ensure planning remains distinct from execution authorization.
    from cydra.blind_reasoning import _persist_planned_reasoning
    from cydra.reasoning_graph import ReasoningGraph
    from cydra.planner import Hypothesis, Observation, Plan

    graph = ReasoningGraph()
    hypothesis = Hypothesis("h", 0.8, {"o": {"CONFIRMED": 0.9, "REFUTED": 0.1}})
    observation = Observation("o", ["CONFIRMED", "REFUTED"], 1.0, authorized=True)
    plan = Plan("o", 0.4, 0.4, "high information gain")

    _persist_planned_reasoning(graph, (hypothesis,), (observation,), plan)

    assert graph.model.nodes[hypothesis.hypothesis_id].kind == "hypothesis"
    assert graph.model.nodes["observation:o"].kind == "observation"
    assert graph.model.nodes["observation:o"].attributes["planned"] is True
    assert not graph.model.nodes["observation:o"].attributes.get("execution_request_digest")


def test_blind_reasoning_result_serialization_has_no_historical_oracle_fields():
    from cydra.blind_reasoning import BlindReasoningResult

    result = BlindReasoningResult(
        case_id="case-1",
        materialization_fingerprint="a" * 64,
        model_fingerprint="b" * 64,
        hypothesis_names=("h1",),
        observation_names=("o1",),
        selected_observation="o1",
        rounds_used=1,
        planning_steps_used=1,
        observations_used=0,
    )

    payload = result.to_json()
    assert "oracle" not in payload.lower()
    assert "known_issue" not in payload.lower()
    assert "historical_finding" not in payload.lower()


def test_load_solidity_asts_uses_compiler_source_identity_not_basename(tmp_path: Path):
    source = "pragma solidity ^0.8.17; contract PredyPool {}\n"
    selected = ("src/PredyPool.sol",)
    build_info = tmp_path / "build-info" / "compiler.json"
    build_info.parent.mkdir(parents=True)
    build_info.write_text(json.dumps({
        "input": {"sources": {"src/PredyPool.sol": {"content": source}}},
        "output": {"sources": {
            "src/PredyPool.sol": {"id": 17, "ast": {
                "absolutePath": "/workspace/historical-predy/src/PredyPool.sol",
                "nodeType": "SourceUnit",
                "id": 99,
            }}
        }},
    }), encoding="utf-8")

    result = _load_solidity_asts(tmp_path, selected, {"src/PredyPool.sol": source})
    assert result["src/PredyPool.sol"]["id"] == 99


def test_load_solidity_asts_uses_exact_compiler_input_content_when_source_name_relocated(tmp_path: Path):
    source = "pragma solidity ^0.8.17; contract PredyPool {}\n"
    build_info = tmp_path / "build-info" / "compiler.json"
    build_info.parent.mkdir(parents=True)
    build_info.write_text(json.dumps({
        "input": {"sources": {"/workspace/repo/src/PredyPool.sol": {"content": source}}},
        "output": {"sources": {
            "/workspace/repo/src/PredyPool.sol": {"id": 18, "ast": {
                "absolutePath": "/workspace/repo/src/PredyPool.sol",
                "nodeType": "SourceUnit",
                "id": 100,
            }}
        }},
    }), encoding="utf-8")

    result = _load_solidity_asts(
        tmp_path,
        ("src/PredyPool.sol",),
        {"src/PredyPool.sol": source},
    )
    assert result["src/PredyPool.sol"]["id"] == 100


def test_load_solidity_asts_rejects_conflicting_identity(tmp_path: Path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(json.dumps({"sourceName": "src/PredyPool.sol", "ast": {"id": 1}}), encoding="utf-8")
    second.write_text(json.dumps({"sourceName": "src/PredyPool.sol", "ast": {"id": 2}}), encoding="utf-8")

    try:
        _load_solidity_asts(tmp_path, ("src/PredyPool.sol",))
    except RuntimeError as exc:
        assert "conflicting compiler ASTs" in str(exc)
    else:
        raise AssertionError("conflicting compiler source identities must fail closed")
