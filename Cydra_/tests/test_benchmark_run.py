from pathlib import Path
import sys

import pytest

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import MaterializedBenchmarkInput
from cydra.benchmark_run import BenchmarkRunError, run_blind_command


def make_case() -> BenchmarkCorpusEntry:
    return BenchmarkCorpusEntry(
        case_id="case-1",
        contest_name="historical",
        repository="example/repo",
        revision="a" * 40,
        input_paths=("src/",),
    )


def make_materialized(root: Path) -> MaterializedBenchmarkInput:
    return MaterializedBenchmarkInput(
        case_id="case-1",
        corpus_fingerprint="b" * 64,
        repository="example/repo",
        revision="a" * 40,
        selected_paths=("src/app.sol",),
        file_manifest=(("src/app.sol", "c" * 64),),
    )


def test_blind_run_rejects_oracle_environment_and_does_not_start_process(tmp_path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text("contract App {}\n", encoding="utf-8")
    output = root / "candidate.json"
    materialized = make_materialized(root)

    monkeypatch.setattr(
        "cydra.benchmark_run.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    with pytest.raises(BenchmarkRunError, match="may not contain oracle/ground-truth variables"):
        run_blind_command(
            make_case(),
            materialized,
            root,
            command=[sys.executable, "-c", "raise SystemExit(99)"],
            runner_revision="runner-test",
            candidate_output=output,
            environment={"CYDRA_TEST_ORACLE": "must-not-cross"},
        )

    assert not output.exists()


def test_blind_run_seals_candidate_output(tmp_path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text("contract App {}\n", encoding="utf-8")
    output = root / "candidate.json"
    materialized = make_materialized(root)

    monkeypatch.setattr(
        "cydra.benchmark_run.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    command = [
        sys.executable,
        "-c",
        "import pathlib,os; pathlib.Path(os.environ['CYDRA_BLIND_CANDIDATE_OUTPUT']).write_text('{\"findings\": []}', encoding='utf-8')",
    ]
    receipt = run_blind_command(
        make_case(),
        materialized,
        root,
        command=command,
        runner_revision="runner-test",
        candidate_output=output,
    )

    assert output.read_text(encoding="utf-8") == '{"findings": []}'
    assert receipt.exit_code == 0
    assert receipt.candidate_output_bytes > 0
    assert len(receipt.candidate_output_sha256) == 64
    assert receipt.fingerprint()


def test_blind_run_rejects_existing_candidate_output(tmp_path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text("contract App {}\n", encoding="utf-8")
    output = root / "candidate.json"
    output.write_text("sealed", encoding="utf-8")
    monkeypatch.setattr(
        "cydra.benchmark_run.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    with pytest.raises(BenchmarkRunError, match="must not already exist"):
        run_blind_command(
            make_case(),
            make_materialized(root),
            root,
            command=[sys.executable, "-c", "pass"],
            runner_revision="runner-test",
            candidate_output=output,
        )


def test_blind_run_rejects_candidate_output_outside_staging(tmp_path, monkeypatch):
    root = tmp_path / "blind"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.sol").write_text("contract App {}\n", encoding="utf-8")
    monkeypatch.setattr(
        "cydra.benchmark_run.validate_materialized_input",
        lambda case, staging, receipt: None,
    )

    with pytest.raises(BenchmarkRunError, match="inside the blind staging directory"):
        run_blind_command(
            make_case(),
            make_materialized(root),
            root,
            command=[sys.executable, "-c", "pass"],
            runner_revision="runner-test",
            candidate_output=tmp_path / "oracle-output.json",
        )
