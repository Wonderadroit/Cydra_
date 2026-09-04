from pathlib import Path

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import MaterializedBenchmarkInput
from cydra.benchmark_replay import BenchmarkReplayAdapter, ReplayAuthorization, ReplayObservationResult
from cydra.blind_reasoning import run_blind_reasoning
from cydra.evidence_reasoning_provider import CanonicalEvidenceReasoningProvider
from cydra.external_execution import ExternalExecutionGateway
from cydra.planner import Hypothesis, Observation
from cydra.reasoning_driver import ReasoningInputs
from cydra.updater import EvidencePolarity


def _case() -> BenchmarkCorpusEntry:
    return BenchmarkCorpusEntry(
        case_id="replay-case",
        contest_name="historical",
        repository="example/repo",
        revision="a" * 40,
        input_paths=("src/",),
    )


def _materialized() -> MaterializedBenchmarkInput:
    return MaterializedBenchmarkInput(
        case_id="replay-case",
        corpus_fingerprint="b" * 64,
        repository="example/repo",
        revision="a" * 40,
        selected_paths=("src/app.sol",),
        file_manifest=(("src/app.sol", "c" * 64),),
    )


def test_replay_adapter_requires_explicit_verifier_and_gateway_capability(tmp_path: Path):
    authorization = ReplayAuthorization("replay-auth")
    calls = []
    observation = Observation(
        "verify:h",
        ["CONFIRMED", "REFUTED"],
        0.5,
        authorized=True,
        domain="target",
        discriminates_hypothesis_ids=("hypothesis:h", "hypothesis:other"),
    )

    def verifier(observation: Observation, root: Path):
        calls.append((observation, root))
        hypothesis_id = f"hypothesis:{observation.name.removeprefix('verify:')}"
        return ReplayObservationResult(
            "CONFIRMED",
            {hypothesis_id: EvidencePolarity.SUPPORTS},
            {"source": "independent-replay"},
        )

    adapter = BenchmarkReplayAdapter(tmp_path, verifier)
    gateway = ExternalExecutionGateway(
        persist_request=lambda request: None,
        set_execution_state=lambda request, state: None,
        persist_result=lambda request, result: None,
    )
    gateway.register("benchmark_replay", adapter)
    request = adapter.build_request(
        observation=observation,
        authorization=authorization,
        command=("cydra-replay", observation.name),
    )

    result = gateway.execute("benchmark_replay", request, authorization=authorization)

    assert result.outcome == "CONFIRMED"
    assert result.execution_id == request.execution_id
    assert result.request_digest == request.digest
    assert result.evidence_polarity["hypothesis:h"] == EvidencePolarity.SUPPORTS
    assert calls[0][0] == observation
    assert calls[0][1] == tmp_path.resolve()


def test_blind_reasoning_replays_only_the_selected_observation(tmp_path: Path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text(
        "contract App { uint256 public value; function set(uint256 x) external { value = x; } }\n",
        encoding="utf-8",
    )
    materialized = _materialized()
    monkeypatch.setattr(
        "cydra.blind_reasoning.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    observation_name = "verify:fixture:selected"
    primary = Hypothesis(
        name="relationship:fixture:write:value",
        probability=0.8,
        predictions={observation_name: {"CONFIRMED": 0.9, "REFUTED": 0.1}},
    )
    alternative = Hypothesis(
        name="relationship:fixture:benign:value",
        probability=0.2,
        predictions={observation_name: {"CONFIRMED": 0.1, "REFUTED": 0.9}},
    )
    observation = Observation(
        observation_name,
        ["CONFIRMED", "REFUTED"],
        1.0,
        authorized=True,
        discriminates_hypothesis_ids=(primary.hypothesis_id, alternative.hypothesis_id),
    )
    monkeypatch.setattr(
        CanonicalEvidenceReasoningProvider,
        "propose",
        lambda self, model: ReasoningInputs.from_sequences([primary, alternative], [observation]),
    )

    calls = []

    def verifier(observation: Observation, replay_root: Path):
        calls.append((observation, replay_root))
        return ReplayObservationResult(
            "CONFIRMED",
            {primary.name: EvidencePolarity.SUPPORTS},
            {"verifier": "test-double"},
        )

    result = run_blind_reasoning(
        _case(),
        materialized,
        root,
        observation_replayer=verifier,
    )

    assert result.selected_observation == observation.name
    assert result.observations_used == 1
    assert len(calls) == 1
    replayed, replay_root = calls[0]
    assert replay_root == root.resolve()
    assert replayed.name == observation.name
    assert replayed.outcomes == observation.outcomes
    assert replayed.cost == observation.cost
    assert replayed.authorized == observation.authorized
    assert replayed.domain == observation.domain
    assert replayed.discriminates_hypothesis_ids == observation.discriminates_hypothesis_ids


def test_replay_receipt_rejects_tampering(tmp_path: Path):
    authorization = ReplayAuthorization("replay-auth")
    observation = Observation("verify:h", [], 1.0, authorized=True)
    adapter = BenchmarkReplayAdapter(
        tmp_path,
        lambda observation, root: ReplayObservationResult(
            "CONFIRMED",
            {f"hypothesis:{observation.name.removeprefix('verify:')}": EvidencePolarity.SUPPORTS},
        ),
    )
    gateway = ExternalExecutionGateway(
        persist_request=lambda request: None,
        set_execution_state=lambda request, state: None,
        persist_result=lambda request, result: None,
    )
    gateway.register("benchmark_replay", adapter)
    request = adapter.build_request(
        observation=observation,
        authorization=authorization,
        command=("cydra-replay", observation.name),
    )
    result = gateway.execute("benchmark_replay", request, authorization=authorization)
    payload = dict(result.canonical_payload())
    payload["outcome"] = "REFUTED"

    try:
        adapter.rehydrate_result(payload=payload, request=request)
    except ValueError as exc:
        assert "canonical digest" in str(exc)
    else:
        raise AssertionError("tampered replay receipt must fail closed")
