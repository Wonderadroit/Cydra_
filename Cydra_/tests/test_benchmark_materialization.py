from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from cydra.benchmark_corpus import BenchmarkCorpusEntry, BenchmarkCorpusError
from cydra.benchmark_materialization import (
    BenchmarkMaterializationError,
    materialize_blind_input,
    validate_materialized_input,
)


def _git_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "src").mkdir()
    (path / "src" / "Target.sol").write_text("contract Target {}\n", encoding="utf-8")
    (path / "scope.txt").write_text("src/\n", encoding="utf-8")
    (path / "out_of_scope.txt").write_text("test/\n", encoding="utf-8")
    (path / "reports").mkdir()
    (path / "reports" / "historical.md").write_text("oracle\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def _entry(revision: str) -> BenchmarkCorpusEntry:
    return BenchmarkCorpusEntry(
        case_id="fixture",
        contest_name="fixture-contest",
        repository="example/fixture",
        revision=revision,
        input_paths=("src/", "scope.txt", "out_of_scope.txt"),
        excluded_paths=("reports/", "README.md"),
    )


def test_materialization_is_pinned_and_oracle_free(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    revision = _git_repo(source)
    entry = _entry(revision)
    destination = tmp_path / "blind"

    receipt = materialize_blind_input(entry, source, destination)

    assert "src/Target.sol" in receipt.selected_paths
    assert "reports/historical.md" not in receipt.selected_paths
    assert (destination / ".cydra-blind-receipt.json").is_file()
    validate_materialized_input(entry, destination, receipt)


def test_wrong_revision_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    revision = _git_repo(source)
    entry = _entry("0" * 40)

    with pytest.raises(BenchmarkMaterializationError, match="revision mismatch"):
        materialize_blind_input(entry, source, tmp_path / "blind")


def test_dirty_source_checkout_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    revision = _git_repo(source)
    entry = _entry(revision)
    (source / "src" / "Target.sol").write_text("contract Modified {}\n", encoding="utf-8")

    with pytest.raises(BenchmarkMaterializationError, match="dirty"):
        materialize_blind_input(entry, source, tmp_path / "blind")


def test_stale_or_tampered_file_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    revision = _git_repo(source)
    entry = _entry(revision)
    destination = tmp_path / "blind"
    receipt = materialize_blind_input(entry, source, destination)

    (destination / "src" / "Target.sol").write_text("contract Tampered {}\n", encoding="utf-8")
    with pytest.raises(BenchmarkMaterializationError, match="file manifest"):
        validate_materialized_input(entry, destination, receipt)


def test_tampered_receipt_fingerprint_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    revision = _git_repo(source)
    entry = _entry(revision)
    destination = tmp_path / "blind"
    receipt = materialize_blind_input(entry, source, destination)

    receipt_data = json.loads((destination / ".cydra-blind-receipt.json").read_text(encoding="utf-8"))
    receipt_data["snapshot_fingerprint"] = "tampered"
    (destination / ".cydra-blind-receipt.json").write_text(
        json.dumps(receipt_data), encoding="utf-8"
    )

    with pytest.raises(BenchmarkMaterializationError, match="receipt fingerprint"):
        validate_materialized_input(entry, destination, receipt)


def test_oracle_named_input_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    revision = _git_repo(source)
    with pytest.raises(BenchmarkCorpusError, match="historical report/oracle"):
        BenchmarkCorpusEntry(
            case_id="fixture",
            contest_name="fixture-contest",
            repository="example/fixture",
            revision=revision,
            input_paths=("reports/",),
        )
